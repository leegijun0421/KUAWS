"""Google Maps Directions 어댑터 (해외 구간 전용).

주의 — 대한민국에서는 쓰지 않는다
---------------------------------
Google 공식 커버리지 표 기준으로 대한민국은 Driving / Walking / Biking
Directions 가 모두 미지원(`—`)이다. 국내 구간은 반드시 OdsayRouteProvider 로
가야 하며, 그 분기는 `provider.select_provider()` 가 담당한다.
"""

from __future__ import annotations

import httpx

from backend.common.config import get_settings
from backend.common.logging import get_logger
from backend.routing.provider import GeoPoint, RouteProvider, RouteProviderError
from shared.types.models import RouteLeg, RoutePreference, RouteSegment

logger = get_logger(__name__)

_ENDPOINT = "https://maps.googleapis.com/maps/api/directions/json"

#: Google vehicle type → 공통 모델의 mode. 목록에 없는 수단은 bus 로 묶는다.
_VEHICLE_TO_MODE: dict[str, str] = {
    "SUBWAY": "subway",
    "METRO_RAIL": "subway",
    "HEAVY_RAIL": "subway",
    "COMMUTER_TRAIN": "subway",
    "TRAM": "bus",
    "BUS": "bus",
    "TROLLEYBUS": "bus",
}

#: 서비스의 경로 선호도 → Google transit_routing_preference
#: Google 에는 "경치" 개념이 없어 fewer_transfers 로 근사한다.
_PREFERENCE_TO_ROUTING: dict[str, str] = {
    "fastest": "less_walking",
    "fewest_transfers": "fewer_transfers",
    "scenic": "fewer_transfers",
}


class GoogleRouteProvider(RouteProvider):
    """Google Maps Directions API 로 해외 대중교통 경로를 조회한다."""

    name = "google"

    #: ⚠️ Google Maps Platform 약관은 응답의 사전 페칭·저장·캐싱을 금지한다.
    #: (Place ID 와 위경도만 예외적으로 영구 저장 가능)
    #: 따라서 경로 응답을 절대 디스크에 남기지 않는다. 호출 수 절감은 캐시가 아니라
    #: Haversine 사전 필터로 후보를 줄이는 방식으로 해결한다.
    cacheable = False

    def _request(
        self, origin: GeoPoint, destination: GeoPoint, preference: RoutePreference
    ) -> dict:
        """Google Directions 에 실제로 요청한다. 캐시가 없을 때만 호출된다."""
        api_key = get_settings().google_maps_api_key
        if not api_key:
            raise RouteProviderError("GOOGLE_MAPS_API_KEY 가 설정되지 않았습니다.")

        params = {
            "origin": f"{origin.lat},{origin.lng}",
            "destination": f"{destination.lat},{destination.lng}",
            "mode": "transit",
            "transit_routing_preference": _PREFERENCE_TO_ROUTING[preference],
            "language": "ko",
            "key": api_key,
        }
        try:
            response = httpx.get(_ENDPOINT, params=params, timeout=10.0)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise RouteProviderError(f"Google Directions 호출 실패: {exc}") from exc

        payload = response.json()
        status = payload.get("status")
        if status != "OK":
            # ZERO_RESULTS 는 해당 지역에 대중교통 데이터가 없다는 뜻이다.
            raise RouteProviderError(
                f"Google Directions 오류: {status} / {payload.get('error_message', '')}"
            )
        return payload

    def _to_segment(
        self,
        payload: dict,
        origin: GeoPoint,
        destination: GeoPoint,
        preference: RoutePreference,
    ) -> RouteSegment:
        """Google 응답을 공통 RouteSegment 로 정규화한다."""
        routes = payload.get("routes", [])
        if not routes:
            raise RouteProviderError("Google 이 경로를 반환하지 않았습니다.")

        leg = routes[0]["legs"][0]
        steps = [
            normalized
            for step in leg.get("steps", [])
            if (normalized := self._to_leg(step)) is not None
        ]
        return RouteSegment(
            from_poi_id=origin.poi_id,
            to_poi_id=destination.poi_id,
            preference=preference,
            total_duration_min=round(leg.get("duration", {}).get("value", 0) / 60),
            # Google 은 통화 단위가 지역마다 다르므로 fare 는 최상위 route 에서 읽는다.
            total_fare=int(routes[0].get("fare", {}).get("value", 0)),
            legs=steps,
        )

    def _to_leg(self, step: dict) -> RouteLeg | None:
        """step 하나를 RouteLeg 로 바꾼다. 길이 0인 도보는 버린다."""
        duration = round(step.get("duration", {}).get("value", 0) / 60)

        if step.get("travel_mode") != "TRANSIT":
            if duration <= 0:
                return None
            return RouteLeg(
                mode="walk",
                from_name=step.get("html_instructions", "도보"),
                to_name="",
                duration_min=duration,
                description=f"도보 {duration}분 ({step.get('distance', {}).get('text', '')})",
            )

        detail = step.get("transit_details", {})
        line = detail.get("line", {})
        vehicle = line.get("vehicle", {}).get("type", "BUS")
        line_name = line.get("short_name") or line.get("name")
        stops = detail.get("num_stops", 0)
        return RouteLeg(
            mode=_VEHICLE_TO_MODE.get(vehicle, "bus"),
            line_name=str(line_name) if line_name else None,
            from_name=detail.get("departure_stop", {}).get("name", ""),
            to_name=detail.get("arrival_stop", {}).get("name", ""),
            duration_min=duration,
            description=f"{line_name} 탑승 {stops}개 정거장",
        )
