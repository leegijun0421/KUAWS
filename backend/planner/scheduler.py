"""C1 제약 스케줄러 진입점 — 후보 POI 목록을 시각이 붙은 일정표로 만든다.

    탐욕 배치 → 제약 위반/배치 실패 → 점수 최하위 후보 제거 → 재시도(최대 3회)
    → 그래도 안 되면 **사유를 담아** 반환

빈 일정을 돌려주지 않는 것이 이 모듈의 계약이다. 빈 화면보다 "왜 못 만들었는지"가
훨씬 낫고, 데모에서 사고가 나도 방어가 된다.

배치 루프는 `placement.py`, 제약 판정은 `constraints.py` 에 있다.
이 파일은 **재시도 전략과 실패 설명**만 담당한다.
"""

from __future__ import annotations

from pydantic import BaseModel

from backend.common.logging import get_logger
from backend.planner.placement import (
    PlacementOutcome,
    estimate_travel_min,
    place_days,
)
from backend.planner.schemas import (
    MatchResult,
    POIVector,
    ScheduleConstraints,
    ScheduleResult,
)
from backend.routing.planner import haversine_km
from backend.routing.provider import RouteProvider

logger = get_logger(__name__)

#: 후보를 줄여가며 시도할 최대 횟수.
MAX_ATTEMPTS = 3
#: 재시도할 때 잘라내는 하위 후보 비율. 점수 낮은 POI 는 대개 외곽에 있어
#: 이동시간만 잡아먹는다. 빼면 나머지가 잘 붙는다.
DROP_RATIO = 0.2
#: 실패 설명에서 "서로 멀다"고 판정하는 기준(분).
FAR_APART_MIN = 60
#: 호출 횟수가 이 값을 넘으면 응답이 느려지고 예산도 문제가 된다(W2 기준).
ROUTING_CALL_BUDGET = 30


def build_schedule(
    candidates: list[MatchResult],
    pois: dict[str, POIVector],
    provider: RouteProvider | None = None,
    days: int = 1,
    constraints: ScheduleConstraints | None = None,
) -> ScheduleResult:
    """탐욕 배치 + 실패 시 후보 제거 재시도로 일정을 만든다.

    `candidates` 는 B2 매칭 출력(점수 내림차순), `pois` 는 poi_id → 상세,
    `provider` 는 D1 라우팅 프로바이더(None 이면 좌표로 자동 선택)다.
    """
    settings = constraints or ScheduleConstraints()
    pool = sorted(
        (match for match in candidates if match.poi_id in pois),
        key=lambda match: match.group_score,
        reverse=True,
    )
    best, attempts, calls = _try_until_acceptable(pool, pois, provider, days, settings)
    if best is None:
        return _failure(candidates, pois, attempts, calls)

    logger.info(
        "일정 생성 완료: 스톱 %d개 · 라우팅 호출 %d회(외부 %d회) · 시도 %d회",
        len(best.stops),
        calls.routing,
        calls.provider,
        attempts,
    )
    return _success(best, candidates, days, settings, attempts, calls)


class CallTally(BaseModel):
    """이번 생성에서 나간 라우팅 호출 수. **재시도분을 모두 합산한다.**

    재시도마다 배치를 처음부터 다시 하므로, 마지막 시도의 숫자만 보면 실제 호출을
    과소 집계한다. 예산(`ROUTING_CALL_BUDGET`) 판단은 합산값으로 해야 한다.
    """

    routing: int = 0
    provider: int = 0


def _try_until_acceptable(
    pool: list[MatchResult],
    pois: dict[str, POIVector],
    provider: RouteProvider | None,
    days: int,
    constraints: ScheduleConstraints,
) -> tuple[PlacementOutcome | None, int, CallTally]:
    """조건을 만족할 때까지 후보를 줄여가며 배치한다. 가장 좋은 결과를 돌려준다."""
    best: PlacementOutcome | None = None
    calls = CallTally()
    attempt = 0
    while attempt < MAX_ATTEMPTS and pool:
        attempt += 1
        outcome = place_days(pool, pois, provider, days, constraints)
        calls.routing += outcome.routing_calls
        calls.provider += outcome.provider_calls
        if best is None or len(outcome.stops) > len(best.stops):
            best = outcome
        if _is_acceptable(outcome, days, constraints):
            return outcome, attempt, calls
        pool = _drop_lowest(pool)
        logger.info("재시도 %d회차 — 하위 후보 제거 후 %d개로 재배치", attempt, len(pool))
    if best is not None and not best.stops:
        return None, attempt, calls
    return best, attempt, calls


def _is_acceptable(
    outcome: PlacementOutcome,
    days: int,
    constraints: ScheduleConstraints,
) -> bool:
    """모든 날에 최소 개수 이상 배치됐는지 본다."""
    if not outcome.stops:
        return False
    for day in range(1, days + 1):
        placed = sum(1 for stop in outcome.stops if stop.day == day)
        if placed < constraints.min_stops_per_day:
            return False
    return True


def _success(
    outcome: PlacementOutcome,
    candidates: list[MatchResult],
    days: int,
    constraints: ScheduleConstraints,
    attempts: int,
    calls: CallTally,
) -> ScheduleResult:
    """배치 결과를 사용자에게 나갈 형태로 정리한다."""
    placed = outcome.placed_ids
    warnings = list(outcome.warnings)
    warnings.extend(_shortfall_warnings(outcome, days, constraints))
    if constraints.start_at is None:
        warnings.append("출발 시각이 없어 시간표가 반영되지 않았습니다 — 편성 시각은 참고용입니다")
    if calls.routing > ROUTING_CALL_BUDGET:
        logger.warning("라우팅 호출 %d회 — 예산(%d회) 초과", calls.routing, ROUTING_CALL_BUDGET)
    return ScheduleResult(
        stops=outcome.stops,
        segments=outcome.segments,
        dropped=[match.poi_id for match in candidates if match.poi_id not in placed],
        warnings=warnings,
        succeeded=True,
        routing_calls=calls.routing,
        provider_calls=calls.provider,
        attempts=attempts,
    )


def _shortfall_warnings(
    outcome: PlacementOutcome,
    days: int,
    constraints: ScheduleConstraints,
) -> list[str]:
    """최소 개수를 못 채운 날에 대한 설명을 만든다."""
    warnings: list[str] = []
    for day in range(1, days + 1):
        placed = sum(1 for stop in outcome.stops if stop.day == day)
        if placed < constraints.min_stops_per_day:
            warnings.append(
                f"{day}일차는 {placed}곳만 배치됐습니다 — 후보가 부족하거나 서로 멀리 있습니다"
            )
    return warnings


def _failure(
    candidates: list[MatchResult],
    pois: dict[str, POIVector],
    attempts: int,
    calls: CallTally,
) -> ScheduleResult:
    """완전 실패. 빈 일정 대신 사유를 담아 돌려준다."""
    reason = _failure_reason(candidates, pois)
    logger.info("일정 생성 실패(시도 %d회): 후보 %d개", attempts, len(candidates))
    return ScheduleResult(
        stops=[],
        segments=[],
        dropped=[match.poi_id for match in candidates],
        warnings=[],
        succeeded=False,
        failure_reason=reason,
        routing_calls=calls.routing,
        provider_calls=calls.provider,
        attempts=attempts,
    )


def _failure_reason(candidates: list[MatchResult], pois: dict[str, POIVector]) -> str:
    """사용자에게 그대로 보여줄 실패 사유. 숫자를 넣어야 다음 행동이 나온다."""
    usable = [pois[match.poi_id] for match in candidates if match.poi_id in pois]
    return (
        "선택하신 조건으로는 일정을 만들지 못했습니다.\n"
        f" - 하드 제약 필터 후 남은 장소가 {len(usable)}개입니다\n"
        f" - 그중 {_isolated_count(usable)}개가 서로 1시간 이상 떨어져 있습니다\n"
        " 제약을 완화하거나 일수를 늘려보세요."
    )


def _isolated_count(pois: list[POIVector]) -> int:
    """가장 가까운 이웃까지도 1시간 넘게 걸리는 POI 수. 추정 이동시간을 쓴다."""
    if len(pois) < 2:
        return len(pois)
    isolated = 0
    for poi in pois:
        nearest = min(
            estimate_travel_min(haversine_km(poi.lat, poi.lng, other.lat, other.lng))
            for other in pois
            if other.poi_id != poi.poi_id
        )
        if nearest > FAR_APART_MIN:
            isolated += 1
    return isolated


def _drop_lowest(pool: list[MatchResult]) -> list[MatchResult]:
    """점수 최하위 `DROP_RATIO` 만큼을 잘라낸다. 최소 1개는 반드시 줄인다."""
    if len(pool) <= 1:
        return []
    drop_count = max(1, round(len(pool) * DROP_RATIO))
    return pool[: len(pool) - drop_count]
