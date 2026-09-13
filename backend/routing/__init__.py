"""routing 모듈. 소유권은 .kiro/steering/structure.md 참조.

경로 조회는 프로바이더 뒤에 숨어 있다. 호출부는 `fetch_route()` 만 쓰면 되고,
국내(ODsay) / 해외(Google Maps) 분기는 이 모듈이 알아서 처리한다.
"""

from backend.routing.planner import SegmentRoute, plan_segment
from backend.routing.provider import (
    GeoPoint,
    NoRouteError,
    Operator,
    RouteProvider,
    RouteProviderError,
    is_in_korea,
    select_provider,
)
from shared.types.models import RoutePreference, RouteSegment

__all__ = [
    "GeoPoint",
    "NoRouteError",
    "Operator",
    "RouteProvider",
    "RouteProviderError",
    "SegmentRoute",
    "fetch_route",
    "is_in_korea",
    "plan_segment",
    "select_provider",
]


def fetch_route(
    origin: GeoPoint,
    destination: GeoPoint,
    preference: RoutePreference = "fastest",
    depart_at: str | None = None,
) -> RouteSegment:
    """두 지점 사이의 대중교통 경로를 조회한다. 프로바이더는 좌표로 자동 선택된다.

    구간 결과(경고 배지·운영기관 포함)가 필요하면 `plan_segment()` 를 쓴다.
    """
    return select_provider(origin, destination).fetch_route(
        origin, destination, preference, depart_at
    )
