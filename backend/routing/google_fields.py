"""Google Routes API v2 요청 필드·응답 해석 헬퍼 (`google_provider.py` 에서 분리).

파일 300줄 규칙(`.kiro/steering/conventions.md`)에 맞추려고 상수표와 순수 함수만 옮겼다.
"""

from __future__ import annotations

from backend.common.logging import get_logger
from backend.routing.provider import PathPoint

logger = get_logger(__name__)

ENDPOINT = "https://routes.googleapis.com/directions/v2:computeRoutes"

#: Routes API 는 fieldMask 가 필수다. 빠뜨리면 빈 응답이 온다.
#: 개발 중 탐색은 scripts/probe_routes.py 가 넓은 마스크로 하고,
#: 운영 코드인 여기서는 정규화에 실제로 쓰는 필드만 좁게 요청한다.
#: ('*' 는 비용이 오르고 신규 필드까지 딸려오므로 금지)
FIELD_MASK = ",".join(
    [
        "routes.duration",
        "routes.travelAdvisory.transitFare",
        "routes.legs.steps.travelMode",
        "routes.legs.steps.staticDuration",
        "routes.legs.steps.distanceMeters",
        "routes.legs.steps.navigationInstruction.instructions",
        "routes.legs.steps.transitDetails",
        # 성향별(경치) 경로 추천용 — 정류장·꺾임점 좌표만 받는다(폴리라인보다 가볍다).
        "routes.legs.steps.startLocation",
        "routes.legs.steps.endLocation",
    ]
)

#: Routes API vehicle type → 공통 모델의 mode. 목록에 없는 수단은 bus 로 묶는다.
VEHICLE_TO_MODE: dict[str, str] = {
    "SUBWAY": "subway",
    "METRO_RAIL": "subway",
    "HEAVY_RAIL": "subway",
    "COMMUTER_TRAIN": "subway",
    "HIGH_SPEED_TRAIN": "subway",
    "LONG_DISTANCE_TRAIN": "subway",
    "MONORAIL": "subway",
    "RAIL": "subway",
    "TRAM": "bus",
    "BUS": "bus",
    "INTERCITY_BUS": "bus",
    "TROLLEYBUS": "bus",
}

#: 서비스의 경로 선호도 → Routes API transitPreferences.routingPreference
#: Google 에는 "경치" 개념이 없어 fewer_transfers 로 근사한다.
PREFERENCE_TO_ROUTING: dict[str, str] = {
    "fastest": "LESS_WALKING",
    "fewest_transfers": "FEWER_TRANSFERS",
    "scenic": "FEWER_TRANSFERS",
}


def seconds(value: str | None) -> int:
    """Routes API 의 duration 문자열('1500s')을 초로 바꾼다.

    형식이 예상과 다르면 0 을 돌려준다 — 시간 정보 하나 때문에 경로 전체를
    버리지 않기 위해서다. 호출부는 0 을 '알 수 없음'으로 다룬다.
    """
    if not value:
        return 0
    try:
        return int(float(value.rstrip("s")))
    except ValueError:
        logger.warning("duration 형식을 해석하지 못했습니다: %r", value)
        return 0


def route_path(route: dict) -> list[PathPoint]:
    """route 의 모든 step 시작·끝 좌표를 순서대로 모은다."""
    points: list[PathPoint] = []
    for leg in route.get("legs", []):
        for step in leg.get("steps", []):
            for key in ("startLocation", "endLocation"):
                lat_lng = (step.get(key) or {}).get("latLng") or {}
                if "latitude" in lat_lng and "longitude" in lat_lng:
                    points.append((lat_lng["latitude"], lat_lng["longitude"]))
    return points
