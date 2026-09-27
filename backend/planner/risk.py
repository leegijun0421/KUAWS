"""W3 일정 실패 위험도 — "이 그룹이 이 장소에서 실망할 확률"을 객관 지표로만 산정한다.

배차간격 평균이 아니라 **실제 편성 시각**으로 환승 연결 여유를 직접 계산한다
(Google Routes v2 의 `depart_at` / `arrive_at`). 추정값을 쓰지 않는다 — 편성 시각이 없는
구간은 그 요인을 건너뛴다.

요인(각각 독립 사건으로 보고 1 − Π(1 − pᵢ) 로 합성)
    환승 연결 여유  < 3분 0.2 / < 5분 0.12 / < 10분 0.05 (앞 차 도착 → 다음 차 출발, 사이 도보 제외)
    환승 횟수        회당 0.04
    장거리 이동      60분 초과 0.05
    영업 종료 여유   < 30분 0.15 / < 60분 0.07 (떠나는 시각 → 그날 영업 종료)
    식사 피크 도착   음식점을 12:00~13:00·19:00~20:00 에 도착 0.08 ("웨이팅 가능" 태그)
    취향 불일치      그룹 최저 적합도가 0.5 미만이면 (0.5 − 최저) × 0.4

쓰지 않는 것(설계 원칙): 인기도·혼잡도. 유명하다는 이유로 감점하지 않는다.

화면용으로는 확률 대신 **구간별 문장**(`segment_flags`)과 일정 한 줄 요약(`risk_summary`)을 쓴다.
"""

from __future__ import annotations

from datetime import datetime, tzinfo

from pydantic import BaseModel

from backend.planner.constraints import to_minutes
from backend.planner.schemas import POIVector
from backend.routing.planner import SegmentRoute
from shared.types.models import RiskFlag, RouteLeg

#: 환승 연결 여유 판정(분) — Notion W3 기준표.
#: 10분 이상 안전 / 5~10 주의 / 3~5 위험 / 3 미만 매우 위험.
SLACK_SAFE_MIN = 10
SLACK_CAUTION_MIN = 5
SLACK_DANGER_MIN = 3

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
        slack = connection_slack(legs, previous, following)
        if slack < SLACK_DANGER_MIN:
            reason = f"환승 연결 여유 {slack}분 — 놓칠 수 있음"
            factors.append(RiskFactor(probability=0.2, reason=reason))
        elif slack < SLACK_CAUTION_MIN:
            factors.append(RiskFactor(probability=0.12, reason=f"환승 연결 여유 {slack}분"))
        elif slack < SLACK_SAFE_MIN:
            factors.append(RiskFactor(probability=0.05, reason=f"환승 연결 여유 {slack}분"))
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


def connection_slack(legs: list[RouteLeg], previous: int, following: int) -> int:
    """앞 차 도착 → 다음 차 출발 사이 실제 여유(분). 사이의 도보 시간을 뺀다."""
    walk = sum(leg.duration_min for leg in legs[previous + 1 : following])
    return _minutes_between(legs[previous].arrive_at, legs[following].depart_at) - walk


def segment_flags(segment: SegmentRoute, tz: tzinfo | None) -> list[RiskFlag]:
    """구간 위험 표시. 숫자가 아니라 노선명·시각·여유분이 들어간 문장을 만든다.

    편성 시각이 없는 구간(도보·ODsay)은 환승 여유를 계산하지 않는다 — 추정하지 않는다.
    """
    legs = segment.primary.legs
    boarded = [i for i, leg in enumerate(legs) if leg.depart_at and leg.arrive_at]
    flags: list[RiskFlag] = []
    for previous, following in zip(boarded, boarded[1:], strict=False):
        slack = connection_slack(legs, previous, following)
        if slack >= SLACK_SAFE_MIN:
            continue
        before, after = legs[previous], legs[following]
        reason = (
            f"{before.to_name}에서 {_line(before)} → {_line(after)} 환승 여유 {slack}분 "
            f"({_local(before.arrive_at, tz)} 도착 · {_local(after.depart_at, tz)} 출발)"
        )
        level = "high" if slack < SLACK_CAUTION_MIN else "medium"
        suggestion = "한 대 놓치면 다음 편성을 기다려야 해요 — 환승역에서 서두르세요"
        flags.append(RiskFlag(level=level, reason=reason, suggestion=suggestion))
    if segment.transfer_count >= 3:
        flags.append(RiskFlag(level="medium", reason=f"환승 {segment.transfer_count}회 구간"))
    return flags


def risk_summary(flags_by_day: list[list[RiskFlag]]) -> str:
    """일정 전체 한 줄 요약."""
    flags = [flag for day in flags_by_day for flag in day]
    high = sum(1 for flag in flags if flag.level == "high")
    medium = sum(1 for flag in flags if flag.level == "medium")
    if not flags:
        return f"{len(flags_by_day)}일 일정의 모든 환승 여유가 {SLACK_SAFE_MIN}분 이상이에요"
    return f"{len(flags_by_day)}일 일정 중 주의 구간 {medium}곳, 위험 구간 {high}곳"


def _line(leg: RouteLeg) -> str:
    """노선 표기 — 숫자만 있는 노선명("87")은 뜻이 안 통하므로 수단을 앞에 붙인다."""
    kind = "지하철" if leg.mode == "subway" else "버스"
    if not leg.line_name:
        return kind
    return leg.line_name if not leg.line_name[0].isdigit() else f"{kind} {leg.line_name}"


def _local(rfc3339: str | None, tz: tzinfo | None) -> str:
    """RFC3339 → 현지 HH:MM."""
    if not rfc3339:
        return "?"
    return f"{datetime.fromisoformat(rfc3339.replace('Z', '+00:00')).astimezone(tz):%H:%M}"


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
