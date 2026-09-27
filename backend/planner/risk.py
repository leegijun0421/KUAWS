"""W3 일정 실패 위험도 — "이 그룹이 이 장소에서 실망할 확률"을 객관 지표로만 산정한다.

배차간격 평균이 아니라 **실제 편성 시각**으로 환승 연결 여유를 직접 계산한다
(Google Routes v2 의 `depart_at` / `arrive_at`). 추정값을 쓰지 않는다 — 편성 시각이 없는
구간은 그 요인을 건너뛴다.

요인(각각 독립 사건으로 보고 1 − Π(1 − pᵢ) 로 합성)
    환승 연결 여유  < 3분 0.15 / < 6분 0.07   (앞 차 도착 → 다음 차 출발, 사이 도보 포함)
    환승 횟수        회당 0.04
    장거리 이동      60분 초과 0.05
    영업 종료 여유   < 30분 0.15 / < 60분 0.07 (떠나는 시각 → 그날 영업 종료)
    식사 피크 도착   음식점을 12:00~13:00·19:00~20:00 에 도착 0.08 ("웨이팅 가능" 태그)
    취향 불일치      그룹 최저 적합도가 0.5 미만이면 (0.5 − 최저) × 0.4

쓰지 않는 것(설계 원칙): 인기도·혼잡도. 유명하다는 이유로 감점하지 않는다.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from backend.planner.constraints import to_minutes
from backend.planner.schemas import POIVector
from backend.routing.planner import SegmentRoute

BASE_RISK = 0.03
MAX_RISK = 0.95
_PEAKS = (("12:00", "13:00"), ("19:00", "20:00"))


class RiskFactor(BaseModel):
    """위험 요인 1개 — 확률과 사람이 읽는 근거."""

    probability: float
    reason: str


def stop_risk(
    poi: POIVector,
    arrive_hhmm: str,
    depart_hhmm: str,
    weekday: int,
    inbound: SegmentRoute | None,
    min_member_fit: float | None,
) -> tuple[float, list[str]]:
    """스톱 1개의 실패 확률과 근거 목록."""
    factors = [
        *connection_factors(inbound),
        *_closing_factor(poi, depart_hhmm, weekday),
        *_peak_factor(poi, arrive_hhmm),
        *_fit_factor(min_member_fit),
    ]
    survive = 1.0 - BASE_RISK
    for factor in factors:
        survive *= 1.0 - factor.probability
    probability = round(min(1.0 - survive, MAX_RISK), 2)
    return probability, [factor.reason for factor in factors]


def connection_factors(segment: SegmentRoute | None) -> list[RiskFactor]:
    """들어오는 구간의 환승 연결 여유·환승 횟수·장거리 요인."""
    if segment is None:
        return []
    factors = []
    legs = segment.primary.legs
    boarded = [index for index, leg in enumerate(legs) if leg.depart_at and leg.arrive_at]
    for previous, following in zip(boarded, boarded[1:], strict=False):
        walk = sum(leg.duration_min for leg in legs[previous + 1 : following])
        slack = _minutes_between(legs[previous].arrive_at, legs[following].depart_at) - walk
        if slack < 3:
            reason = f"환승 연결 여유 {slack}분 — 놓칠 수 있음"
            factors.append(RiskFactor(probability=0.15, reason=reason))
        elif slack < 6:
            factors.append(RiskFactor(probability=0.07, reason=f"환승 연결 여유 {slack}분"))
    if segment.transfer_count:
        factors.append(
            RiskFactor(
                probability=0.04 * segment.transfer_count,
                reason=f"환승 {segment.transfer_count}회",
            )
        )
    if segment.primary.total_duration_min > 60:
        factors.append(RiskFactor(probability=0.05, reason="이동 60분 초과"))
    return factors


def _closing_factor(poi: POIVector, depart_hhmm: str, weekday: int) -> list[RiskFactor]:
    """떠나는 시각과 그날 영업 종료 사이 여유."""
    depart = to_minutes(depart_hhmm)
    closes = [to_minutes(close) for open_, close in poi.opening.ranges_for(weekday)
              if to_minutes(open_) <= depart <= to_minutes(close)]
    if not closes:
        return []
    margin = min(closes) - depart
    if margin < 30:
        return [RiskFactor(probability=0.15, reason=f"영업 종료 {margin}분 전까지 머묾")]
    if margin < 60:
        return [RiskFactor(probability=0.07, reason=f"영업 종료까지 여유 {margin}분")]
    return []


def _peak_factor(poi: POIVector, arrive_hhmm: str) -> list[RiskFactor]:
    """식사 피크 시간 도착(웨이팅 태그). 혼잡도 데이터가 아니라 시각만 본다."""
    if not poi.is_meal:
        return []
    arrive = to_minutes(arrive_hhmm)
    for start, end in _PEAKS:
        if to_minutes(start) <= arrive <= to_minutes(end):
            return [RiskFactor(probability=0.08, reason="식사 피크 시간 도착 — 대기 가능")]
    return []


def _fit_factor(min_member_fit: float | None) -> list[RiskFactor]:
    """그룹 중 누군가에게 확실히 안 맞는 장소."""
    if min_member_fit is None or min_member_fit >= 0.5:
        return []
    return [
        RiskFactor(
            probability=round((0.5 - min_member_fit) * 0.4, 3),
            reason=f"취향이 덜 맞는 멤버 있음(최저 {min_member_fit:.0%})",
        )
    ]


def _minutes_between(start: str | None, end: str | None) -> int:
    """RFC3339 두 시각 사이 분."""
    if not start or not end:
        return 0
    first = datetime.fromisoformat(start.replace("Z", "+00:00"))
    second = datetime.fromisoformat(end.replace("Z", "+00:00"))
    return round((second - first).total_seconds() / 60)
