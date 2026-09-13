"""2지점 실경로 모듈 — 두 지점 사이 대중교통 경로 1건을 구간 결과로 만든다.

W0 의 `RouteProvider` 어댑터 **위에** 올라가는 얇은 층이다. 여기에는 Google 관련 코드가
한 줄도 없다 — 제공자 교체 시 이 파일은 건드리지 않는다.

이 층이 하는 일은 세 가지다.

1. **호출할 가치가 있는지 먼저 판단한다.** 직선거리가 아주 가까우면 도보로 만들어 버리고
   외부 호출을 아예 하지 않는다. Google 응답은 약관상 캐싱이 금지라, 호출 수를 줄이는
   수단이 사전 필터밖에 없다(`docs/DECISIONS.md` 2026-08-27).
2. **경로 없음을 예외가 아니라 ``None`` 으로 바꾼다.** 스케줄러(C1)는 후보를 바꿔가며
   여러 번 물어보므로, 매번 try/except 를 쓰게 하면 안 된다. 반면 키 미설정·API 오류는
   우리가 고쳐야 할 버그이므로 그대로 전파한다(`NoRouteError` 만 삼킨다).
3. **경고 배지 근거를 계산한다.** 오래 걸리거나 환승이 많은 구간을 표시만 한다.

⚠️ 택시 대안(`travelMode: DRIVING` 병기)은 9/4 절단 2 로 예선 범위에서 빠졌다.
   `SegmentRoute.alternative` 자리는 본선(10/3~) 재투입을 위해 비워 둔다.
   예선에서는 경고 배지만 붙이고 대안은 제시하지 않는다.
"""

from __future__ import annotations

from math import asin, cos, radians, sin, sqrt
from typing import Literal

from pydantic import BaseModel

from backend.common.logging import get_logger
from backend.routing.provider import (
    GeoPoint,
    NoRouteError,
    Operator,
    RouteProvider,
    select_provider,
)
from shared.types.models import RouteLeg, RoutePreference, RouteSegment

logger = get_logger(__name__)

#: 경고 배지 발동 기준. W3 사용자 테스트에서 조정될 가능성이 높아 상수로 뺀다.
WARN_DURATION_MIN = 60
WARN_TRANSFER_COUNT = 3

#: 직선거리가 이보다 가까우면 외부 호출 없이 도보 구간으로 만든다.
WALK_ONLY_KM = 0.8
#: 직선거리가 이보다 멀면 도시 내 이동이 아니다. 호출하지 않고 None.
#: 도시 반경이 다르므로(파리 < 타이베이 광역) 값은 도시별 조정 여지를 남긴다.
MAX_SEGMENT_KM = 40.0

#: 도보 속도(km/h)와 우회 계수. 직선거리에 1.3 을 곱해 실제 도보 거리를 근사한다.
_WALK_SPEED_KMH = 4.5
_WALK_DETOUR_FACTOR = 1.3

#: 환승 횟수를 셀 때 "탈것"으로 보는 mode. 도보와 ODsay 의 transfer 는 제외한다.
_TRANSIT_MODES = frozenset({"subway", "bus"})


class RouteAdvisory(BaseModel):
    """구간에 붙는 경고 배지 하나. 이유 없는 경고는 설득력이 없어 문구를 함께 준다."""

    code: Literal["long_duration", "many_transfers"]
    message: str


class SegmentRoute(BaseModel):
    """한 구간의 이동 결과. C1 스케줄러가 소비한다."""

    #: 항상 대중교통(또는 짧은 구간의 도보). 각 leg 에 depart_at / arrive_at 이 들어 있다.
    primary: RouteSegment
    #: 탑승 횟수 − 1. 도보 구간은 세지 않는다.
    transfer_count: int
    #: 약관 표기용 운영기관. 프론트가 응답 값 그대로 렌더링한다(하드코딩 금지).
    operators: list[Operator] = []
    #: 경고 배지. 비어 있으면 표시할 것이 없다는 뜻이다.
    advisories: list[RouteAdvisory] = []
    #: ⚠️ 9/4 절단 2 — 택시 대안은 예선 범위 밖이다. 본선 재투입 전까지 항상 None.
    alternative: None = None


def plan_segment(
    origin: GeoPoint,
    destination: GeoPoint,
    depart_at: str | None = None,
    preference: RoutePreference = "fastest",
    provider: RouteProvider | None = None,
) -> SegmentRoute | None:
    """두 지점 사이 경로 1건을 구한다. 경로가 없으면 예외가 아니라 None.

    `depart_at` 은 RFC3339 출발 시각이다. 넣지 않으면 시간표 기반 결과가 나오지 않아
    `RouteLeg.depart_at` / `arrive_at` 이 "지금 출발" 기준이 된다 — 일정표에는 반드시 넣는다.
    """
    distance_km = haversine_km(origin.lat, origin.lng, destination.lat, destination.lng)

    # 사전 필터 — 여기서 걸리면 외부 호출이 일어나지 않는다. 호출 수 절감의 유일한 수단이다.
    if distance_km > MAX_SEGMENT_KM or distance_km < WALK_ONLY_KM:
        logger.info("사전 필터(직선 %.2fkm): %s → %s", distance_km, origin.name, destination.name)
        if distance_km > MAX_SEGMENT_KM:
            return None  # 도시 내 이동이 아니다
        return _walk_only(origin, destination, preference, distance_km)

    provider = provider or select_provider(origin, destination)
    try:
        detail = provider.fetch_route_detail(origin, destination, preference, depart_at)
    except NoRouteError as exc:
        # 정상적인 결과다. 호출자가 다른 후보로 넘어가면 된다.
        # 키 미설정·API 오류(RouteProviderError)는 여기서 잡지 않고 그대로 전파한다.
        logger.info("경로 없음: %s → %s (%s)", origin.name, destination.name, exc)
        return None

    legs = merge_walk_legs(detail.segment.legs)
    transfer_count = count_transfers(legs)
    return SegmentRoute(
        primary=detail.segment.model_copy(update={"legs": legs}),
        transfer_count=transfer_count,
        operators=detail.operators,
        advisories=build_advisories(detail.segment.total_duration_min, transfer_count),
    )


def merge_walk_legs(legs: list[RouteLeg]) -> list[RouteLeg]:
    """연속된 도보 leg 를 하나로 합친다.

    Routes v2 는 도보를 **회전 안내 단위로** 쪼개 준다("우회전", "램프로 우회전" …).
    9/13 실호출에서 한 구간에 도보 step 이 9개 나왔다. 그대로 두면 화면이 길 안내처럼
    되고 "몇 분 걷는지"가 안 보인다. 탑승 구간 사이의 도보는 합쳐서 총 시간만 보여준다.

    편성 시각은 탑승 leg 에만 있으므로 합치면서 잃는 정보가 없다.
    """
    merged: list[RouteLeg] = []
    for leg in legs:
        previous = merged[-1] if merged else None
        if leg.mode != "walk" or previous is None or previous.mode != "walk":
            merged.append(leg)
            continue
        total = previous.duration_min + leg.duration_min
        merged[-1] = previous.model_copy(
            update={
                "to_name": leg.to_name,
                "duration_min": total,
                "description": f"도보 {total}분",
            }
        )
    return merged


def count_transfers(legs: list[RouteLeg]) -> int:
    """환승 횟수 = 탑승한 노선 수 − 1. 도보만으로 이뤄진 구간은 0."""
    boarded = sum(1 for leg in legs if leg.mode in _TRANSIT_MODES)
    return max(boarded - 1, 0)


def build_advisories(duration_min: int, transfer_count: int) -> list[RouteAdvisory]:
    """경고 배지를 만든다. 기준을 넘지 않으면 빈 목록."""
    advisories: list[RouteAdvisory] = []
    if duration_min > WARN_DURATION_MIN:
        advisories.append(
            RouteAdvisory(
                code="long_duration",
                message=f"이동에만 {duration_min}분이 걸립니다",
            )
        )
    if transfer_count >= WARN_TRANSFER_COUNT:
        advisories.append(
            RouteAdvisory(
                code="many_transfers",
                message=f"환승 {transfer_count}회 구간입니다",
            )
        )
    return advisories


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """두 좌표 사이 직선거리(km)."""
    earth_radius_km = 6371
    dlat, dlng = radians(lat2 - lat1), radians(lng2 - lng1)
    a = (
        sin(dlat / 2) ** 2
        + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2
    )
    return 2 * earth_radius_km * asin(sqrt(a))


def _walk_only(
    origin: GeoPoint,
    destination: GeoPoint,
    preference: RoutePreference,
    distance_km: float,
) -> SegmentRoute:
    """아주 가까운 구간을 도보 1 leg 로 직접 만든다. 외부 호출 없음.

    편성 시각이 없는 구간이므로 `depart_at` / `arrive_at` 은 비워 둔다 —
    없는 값을 추정으로 채우지 않는다(`docs/DECISIONS.md` 2026-09-06).
    """
    walk_km = distance_km * _WALK_DETOUR_FACTOR
    duration_min = max(round(walk_km / _WALK_SPEED_KMH * 60), 1)
    leg = RouteLeg(
        mode="walk",
        from_name=origin.name,
        to_name=destination.name,
        duration_min=duration_min,
        description=f"도보 {duration_min}분 (약 {round(walk_km * 1000)}m)",
    )
    segment = RouteSegment(
        from_poi_id=origin.poi_id,
        to_poi_id=destination.poi_id,
        preference=preference,
        total_duration_min=duration_min,
        total_fare=0.0,
        fare_currency=None,
        legs=[leg],
    )
    return SegmentRoute(primary=segment, transfer_count=0)
