"""탐욕 배치 루프 — 후보 목록을 시각이 붙은 스톱으로 바꾼다.

최적해를 찾지 않는다. 조합 최적화로 풀면 NP-hard 이고, 6주 프로젝트에서 그 길로
들어서면 W2 에서 끝난다. 여기서 만드는 건 **"항상 그럴듯한 일정"** 이다.

호출 절감이 이 파일의 두 번째 목표다. 매 스텝마다 후보 전부에 라우팅을 부르면
일정 1개에 수백 번이 나간다. 그래서 두 단계로 나눈다.

1. Haversine 직선거리로 **추정** 이동시간을 구해 후보를 정렬한다(호출 0회).
2. 상위 `MAX_PROBES_PER_STEP` 개만 실제 라우팅을 부른다.

Google 약관상 응답을 디스크에 저장할 수 없으므로(`docs/DECISIONS.md` 2026-08-27)
호출을 줄이는 수단은 사전 필터뿐이다. 캐시 파일을 만들지 말 것.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from pydantic import BaseModel

from backend.common.logging import get_logger
from backend.planner.constraints import (
    DayState,
    adjust_arrival,
    day_warnings,
    record_stop,
    score_bonus,
    to_minutes,
    veto_stop,
)
from backend.planner.schemas import MatchResult, POIVector, ScheduleConstraints, ScheduledStop
from backend.routing.planner import (
    MAX_SEGMENT_KM,
    WALK_ONLY_KM,
    SegmentRoute,
    haversine_km,
    plan_segment,
)
from backend.routing.provider import GeoPoint, RouteProvider

logger = get_logger(__name__)

#: 한 스텝에서 실제 라우팅을 부를 후보 수 상한. 첫 후보가 통과하면 1회로 끝나므로
#: 평소 호출 수는 스텝당 1회이고, 거부가 날 때만 아래로 내려간다.
#: 9/27 실측: 상한이 3이던 때 직선거리 추정이 실제 대중교통보다 짧아 상위 3곳이 모두
#: 거부되고 2일차가 2곳에서 끝났다. 그래서 8로 올렸다.
MAX_PROBES_PER_STEP = 8
#: 하루 총 스톱(관광 + 식사) 안전 상한.
_MAX_TOTAL_STOPS = 10

#: 추정 이동시간용 평균 속도(km/h). 대기·환승을 포함한 체감 속도라 실제보다 느리다.
_ESTIMATE_SPEED_KMH = 18.0
#: 추정에 더하는 고정 오버헤드(분) — 승강장까지 걷고 기다리는 시간.
_ESTIMATE_OVERHEAD_MIN = 5

#: `start_at` 이 없을 때 쓰는 기준 날짜. 결과는 "HH:MM" 만 쓰므로 표시에 영향이 없다.
_PLACEHOLDER_DATE = datetime(2026, 1, 1)


class PlacementOutcome(BaseModel):
    """배치 1회(= 전체 일수)의 결과."""

    stops: list[ScheduledStop] = []
    segments: list[SegmentRoute] = []
    warnings: list[str] = []
    #: 일차 → 그날 배치가 멈춘 이유(마지막 거부 사유). 부족 경고에 붙인다.
    stop_reasons: dict[int, str] = {}
    routing_calls: int = 0
    provider_calls: int = 0

    @property
    def placed_ids(self) -> set[str]:
        """배치에 성공한 poi_id 집합."""
        return {stop.poi_id for stop in self.stops}


@dataclass
class PlacementContext:
    """배치 1회 동안 바뀌지 않는 입력 묶음. 인자 목록이 길어지는 것을 막는다."""

    pois: dict[str, POIVector]
    #: poi_id → 그룹 점수. 배치된 스톱에 점수를 다시 실어 주기 위해 들고 있는다.
    scores: dict[str, float]
    provider: RouteProvider | None
    constraints: ScheduleConstraints
    outcome: PlacementOutcome = field(default_factory=PlacementOutcome)


def place_days(
    candidates: list[MatchResult],
    pois: dict[str, POIVector],
    provider: RouteProvider | None,
    days: int,
    constraints: ScheduleConstraints,
) -> PlacementOutcome:
    """후보 목록을 `days` 일치 일정으로 배치한다. 남은 후보는 다음 날로 넘어간다."""
    remaining = [match for match in candidates if match.poi_id in pois]
    context = PlacementContext(
        pois=pois,
        scores={match.poi_id: match.group_score for match in remaining},
        provider=provider,
        constraints=constraints,
    )
    for day in range(1, days + 1):
        _place_one_day(day, remaining, context)
    return context.outcome


def _place_one_day(day: int, remaining: list[MatchResult], context: PlacementContext) -> None:
    """하루치를 배치한다. `remaining` 에서 쓴 후보를 제거하고 결과를 누적한다."""
    clock, day_end = day_window(day, context.constraints)
    state = DayState(day=day)
    here: POIVector | None = None

    # 관광 스톱 상한은 veto_stop 이 막는다(식사는 상한에 세지 않음). 여기선 총량 안전장치만 둔다.
    while len(state.stops) < _MAX_TOTAL_STOPS and clock < day_end:
        choice = _choose_next(here, clock, remaining, state, context)
        if choice is None:
            context.outcome.stop_reasons[day] = state.last_veto or "갈 수 있는 후보가 남지 않음"
            break
        poi, segment, travel_min, arrive = choice
        if arrive + timedelta(minutes=poi.avg_duration_min) > day_end:
            break  # 오늘 안에 못 들어간다. 남은 후보는 다음 날로 넘긴다.

        _commit_stop(poi, segment, travel_min, arrive, state, context)
        remaining[:] = [match for match in remaining if match.poi_id != poi.poi_id]
        clock = arrive + timedelta(minutes=poi.avg_duration_min)
        here = poi

    context.outcome.warnings.extend(day_warnings(state, context.constraints))


def _commit_stop(
    poi: POIVector,
    segment: SegmentRoute | None,
    travel_min: int,
    arrive: datetime,
    state: DayState,
    context: PlacementContext,
) -> None:
    """확정된 스톱과 이동 구간을 결과에 반영한다."""
    stop = ScheduledStop(
        day=state.day,
        order=len(state.stops) + 1,
        poi_id=poi.poi_id,
        name=poi.name,
        arrive_at=f"{arrive:%H:%M}",
        depart_at=f"{arrive + timedelta(minutes=poi.avg_duration_min):%H:%M}",
        stay_min=poi.avg_duration_min,
        group_score=context.scores.get(poi.poi_id, 0.0),
        travel_min_from_prev=travel_min if segment is not None else None,
    )
    context.outcome.stops.append(stop)
    state.stops.append(stop)
    state.travel_min += travel_min
    record_stop(poi, arrive, state, context.constraints)
    if segment is not None:
        context.outcome.segments.append(segment)
        state.segments.append(segment)


def _choose_next(
    here: POIVector | None,
    clock: datetime,
    remaining: list[MatchResult],
    state: DayState,
    context: PlacementContext,
) -> tuple[POIVector, SegmentRoute | None, int, datetime] | None:
    """다음에 갈 곳을 고른다. 고를 수 없으면 None.

    점수만 보지 않는다. 점수 0.9 인데 1시간 떨어진 곳보다 0.75 인데 10분 거리가 낫다.
    실제 이동시간은 라우팅을 불러야 알지만, 부르기 전에 추정치로 순위를 매겨
    상위 `MAX_PROBES_PER_STEP` 개만 확인한다. 추정치로도 제약(영업시간·식사 시간대 등)에
    걸리는 후보는 순위에서 미리 빼므로, 라우팅 호출은 가망 있는 후보에만 쓰인다.
    """
    ranked = _rank(here, clock, remaining, state, context)
    if here is None:
        return _first_stop(ranked, clock, state, context)

    origin = _geo(here)
    for poi in ranked[:MAX_PROBES_PER_STEP]:
        segment = _fetch_segment(origin, poi, clock, context)
        if segment is None:
            state.last_veto = f"{poi.name}까지 대중교통 경로 없음"
            continue
        travel_min = segment.primary.total_duration_min
        arrive = adjust_arrival(
            poi, clock + timedelta(minutes=travel_min), state, context.constraints
        )
        veto = veto_stop(poi, arrive, travel_min, state, context.constraints)
        if veto is not None:
            logger.info("배치 거부: %s", veto.message)
            state.last_veto = veto.message
            continue
        return poi, segment, travel_min, arrive
    return None


def _first_stop(
    ranked: list[POIVector],
    clock: datetime,
    state: DayState,
    context: PlacementContext,
) -> tuple[POIVector, None, int, datetime] | None:
    """그날 첫 스톱을 고른다. 이동이 없으므로 라우팅을 부르지 않는다."""
    for poi in ranked:
        arrive = adjust_arrival(poi, clock, state, context.constraints)
        if veto_stop(poi, arrive, 0, state, context.constraints) is None:
            return poi, None, 0, arrive
    return None


def _rank(
    here: POIVector | None,
    clock: datetime,
    remaining: list[MatchResult],
    state: DayState,
    context: PlacementContext,
) -> list[POIVector]:
    """실질 점수(그룹 점수 − 이동 비용 + 제약 가산점) 내림차순으로 후보를 정렬한다.

    추정 이동시간으로도 제약에 걸리는 후보(휴무·식사 시간대 밖·이동 상한 등)는 뺀다.
    """
    constraints = context.constraints
    scored: list[tuple[float, POIVector]] = []
    for match in remaining:
        poi = context.pois[match.poi_id]
        travel_min = 0
        if here is not None:
            distance_km = haversine_km(here.lat, here.lng, poi.lat, poi.lng)
            if distance_km > constraints.max_leg_km:
                continue  # 사전 필터 — 라우팅을 부르지도 않는다
            travel_min = estimate_travel_min(distance_km)
        arrive = adjust_arrival(poi, clock + timedelta(minutes=travel_min), state, constraints)
        if veto_stop(poi, arrive, travel_min, state, constraints) is not None:
            continue  # 추정치로도 안 되는 후보 — 라우팅 예산을 쓰지 않는다
        bonus = score_bonus(poi, arrive, constraints, state)
        scored.append((pick_score(match, travel_min, constraints.travel_penalty) + bonus, poi))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [poi for _, poi in scored]


def _fetch_segment(
    origin: GeoPoint,
    poi: POIVector,
    clock: datetime,
    context: PlacementContext,
) -> SegmentRoute | None:
    """구간 1건을 조회하고 호출 횟수를 센다. 경로가 없으면 None."""
    destination = _geo(poi)
    distance_km = haversine_km(origin.lat, origin.lng, destination.lat, destination.lng)
    context.outcome.routing_calls += 1
    if WALK_ONLY_KM <= distance_km <= MAX_SEGMENT_KM:
        # 사전 필터를 통과한 구간만 실제 외부 호출로 이어진다.
        context.outcome.provider_calls += 1
    return plan_segment(
        origin, destination, depart_at=rfc3339_or_none(clock), provider=context.provider
    )


def pick_score(match: MatchResult, travel_min: int, travel_penalty: float) -> float:
    """이동 비용을 반영한 실질 점수."""
    return match.group_score - travel_penalty * (travel_min / 60)


def estimate_travel_min(distance_km: float) -> int:
    """직선거리로 이동시간을 추정한다. 순위 매기기 전용이고 결과에는 쓰지 않는다."""
    return round(distance_km / _ESTIMATE_SPEED_KMH * 60) + _ESTIMATE_OVERHEAD_MIN


def day_window(day: int, constraints: ScheduleConstraints) -> tuple[datetime, datetime]:
    """`day` 일차의 시작·종료 시각을 만든다(1일차 = `start_at` 당일)."""
    base = _parse_start(constraints.start_at)
    day_date = (base + timedelta(days=day - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    start = day_date + timedelta(minutes=to_minutes(constraints.day_start))
    end = day_date + timedelta(minutes=to_minutes(constraints.day_end))
    return start, end


def _parse_start(start_at: str | None) -> datetime:
    """`start_at`(RFC3339)을 datetime 으로. 없으면 기준 날짜를 쓴다."""
    if start_at is None:
        return _PLACEHOLDER_DATE
    return datetime.fromisoformat(start_at.replace("Z", "+00:00"))


def rfc3339_or_none(clock: datetime) -> str | None:
    """라우팅에 넘길 출발 시각. 시간대가 없으면 시간표를 쓸 수 없으므로 None."""
    if clock.tzinfo is None:
        return None
    return clock.isoformat(timespec="seconds")


def _geo(poi: POIVector) -> GeoPoint:
    """배치용 POI 를 라우팅 입력 좌표로 바꾼다."""
    return GeoPoint(poi_id=poi.poi_id, name=poi.name, lat=poi.lat, lng=poi.lng)
