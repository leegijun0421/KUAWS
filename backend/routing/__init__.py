"""routing 모듈. 소유권은 .kiro/steering/structure.md 참조.

경로 조회는 프로바이더 뒤에 숨어 있다. 호출부는 `fetch_route()` 만 쓰면 되고,
국내(ODsay) / 해외(Google Maps) 분기는 이 모듈이 알아서 처리한다.
"""

from backend.routing.provider import (
    GeoPoint,
    RouteProvider,
    RouteProviderError,
    is_in_korea,
    select_provider,
)
from shared.types.models import RoutePreference, RouteSegment

__all__ = [
    "GeoPoint",
    "RouteProvider",
    "RouteProviderError",
    "fetch_route",
    "is_in_korea",
    "select_provider",
]


def fetch_route(
    origin: GeoPoint, destination: GeoPoint, preference: RoutePreference = "fastest"
) -> RouteSegment:
    """두 지점 사이의 대중교통 경로를 조회한다. 프로바이더는 좌표로 자동 선택된다."""
    return select_provider(origin, destination).fetch_route(origin, destination, preference)
