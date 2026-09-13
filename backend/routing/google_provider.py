"""Google Routes API v2 어댑터 (해외 구간 전용).

주의 — 대한민국에서는 쓰지 않는다
---------------------------------
Google 공식 커버리지 표 기준으로 대한민국은 Driving / Walking / Biking
경로가 모두 미지원(`—`)이다. 국내 구간은 반드시 OdsayRouteProvider 로
가야 하며, 그 분기는 `provider.select_provider()` 가 담당한다.

왜 Directions API 가 아니라 Routes API v2 인가
----------------------------------------------
구버전 Directions API(`maps.googleapis.com/maps/api/directions/json`)는
응답 필드가 고정이라 필요 없는 데이터까지 받고, 대중교통 편성 시각을
`transit_details` 안에서만 얕게 준다. Routes API v2 는

- `X-Goog-FieldMask` 로 필요한 필드만 받아 비용·지연을 줄이고,
- `transitDetails.stopDetails` 에서 **실제 편성의 출발·도착 시각**을 준다.

이 편성 시각이 C1 막차 경고와 W3 실패 위험도의 입력이다. 그래서 v2 로 간다.
"""

from __future__ import annotations

import httpx

from backend.common.config import get_settings
from backend.common.logging import get_logger
from backend.routing.provider import (
    GeoPoint,
    NoRouteError,
    Operator,
    RouteProvider,
    RouteProviderError,
)
from shared.types.models import RouteLeg, RoutePreference, RouteSegment

logger = get_logger(__name__)

_ENDPOINT = "https://routes.googleapis.com/directions/v2:computeRoutes"

#: Routes API 는 fieldMask 가 필수다. 빠뜨리면 빈 응답이 온다.
#: 개발 중 탐색은 scripts/probe_routes.py 가 넓은 마스크로 하고,
#: 운영 코드인 여기서는 정규화에 실제로 쓰는 필드만 좁게 요청한다.
#: ('*' 는 비용이 오르고 신규 필드까지 딸려오므로 금지)
_FIELD_MASK = ",".join(
    [
        "routes.duration",
        "routes.travelAdvisory.transitFare",
        "routes.legs.steps.travelMode",
        "routes.legs.steps.staticDuration",
        "routes.legs.steps.distanceMeters",
        "routes.legs.steps.navigationInstruction.instructions",
        "routes.legs.steps.transitDetails",
    ]
)

#: Routes API vehicle type → 공통 모델의 mode. 목록에 없는 수단은 bus 로 묶는다.
_VEHICLE_TO_MODE: dict[str, str] = {
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
_PREFERENCE_TO_ROUTING: dict[str, str] = {
    "fastest": "LESS_WALKING",
    "fewest_transfers": "FEWER_TRANSFERS",
    "scenic": "FEWER_TRANSFERS",
}


def _seconds(value: str | None) -> int:
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


class GoogleRouteProvider(RouteProvider):
    """Google Routes API v2 로 해외 대중교통 경로를 조회한다."""

    name = "google"

    #: ⚠️ Google Maps Platform 약관은 응답의 사전 페칭·저장·캐싱을 금지한다.
    #: (Place ID 와 위경도만 예외적으로 영구 저장 가능)
    #: 따라서 경로 응답을 절대 디스크에 남기지 않는다. 호출 수 절감은 캐시가 아니라
    #: Haversine 사전 필터로 후보를 줄이는 방식으로 해결한다.
    cacheable = False

    def _request(
        self,
        origin: GeoPoint,
        destination: GeoPoint,
        preference: RoutePreference,
        depart_at: str | None = None,
    ) -> dict:
        """Routes API v2 computeRoutes 에 실제로 요청한다.

        `depart_at`(RFC3339)을 넘기면 `departureTime` 으로 실어 보낸다. 생략하면
        요청 시각 기준 시간표가 적용된다 — 일정표를 만들 때는 반드시 넘길 것.
        허용 범위는 과거 7일 ~ 미래 100일이며, 벗어나면 INVALID_ARGUMENT 가 온다.
        """
        api_key = get_settings().google_backend_api_key
        if not api_key:
            raise RouteProviderError("GOOGLE_BACKEND_API_KEY 가 설정되지 않았습니다.")

        body = {
            "origin": {
                "location": {"latLng": {"latitude": origin.lat, "longitude": origin.lng}}
            },
            "destination": {
                "location": {
                    "latLng": {"latitude": destination.lat, "longitude": destination.lng}
                }
            },
            "travelMode": "TRANSIT",
            "transitPreferences": {
                "routingPreference": _PREFERENCE_TO_ROUTING[preference]
            },
            "languageCode": "ko",
            "units": "METRIC",
        }
        if depart_at:
            body["departureTime"] = depart_at
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": _FIELD_MASK,
        }

        try:
            response = httpx.post(_ENDPOINT, json=body, headers=headers, timeout=10.0)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            # Routes API 는 오류 사유를 본문에 담아준다. 앞부분만 로그에 남긴다.
            raise RouteProviderError(
                f"Google Routes 호출 실패: HTTP {exc.response.status_code} / "
                f"{exc.response.text[:200]}"
            ) from exc
        except httpx.HTTPError as exc:
            raise RouteProviderError(f"Google Routes 호출 실패: {exc}") from exc

        payload = response.json()
        if not payload.get("routes"):
            # 경로가 없으면 v2 는 200 + 빈 객체를 준다. 대중교통 데이터가 없는
            # 지역이거나 좌표가 잘못됐을 때다. (Google 은 latitude 가 먼저다)
            raise NoRouteError(
                "Google Routes 가 경로를 반환하지 않았습니다 "
                "(대중교통 미지원 지역이거나 좌표 오류)."
            )
        return payload

    def _to_segment(
        self,
        payload: dict,
        origin: GeoPoint,
        destination: GeoPoint,
        preference: RoutePreference,
    ) -> RouteSegment:
        """Routes API v2 응답을 공통 RouteSegment 로 정규화한다."""
        routes = payload.get("routes", [])
        if not routes:
            raise NoRouteError("Google 이 경로를 반환하지 않았습니다.")

        route = routes[0]
        # TRANSIT 은 경유지를 지정할 수 없으므로 leg 는 항상 1개다.
        leg = route.get("legs", [{}])[0]
        steps = [
            normalized
            for step in leg.get("steps", [])
            if (normalized := self._to_leg(step)) is not None
        ]

        # 요금은 통화가 지역마다 다르다. Routes API 는 {units, nanos} 로 쪼개 주는데
        # units 는 주 단위 문자열, nanos 는 10억분의 1 단위다.
        # 파리 2.55 EUR = {"units": "2", "nanos": 550000000} → units 만 읽으면 2 로 깎인다.
        fare = route.get("travelAdvisory", {}).get("transitFare", {})
        try:
            total_fare = int(fare.get("units", 0) or 0) + int(fare.get("nanos", 0) or 0) / 1e9
        except (TypeError, ValueError):
            logger.warning("요금 형식을 해석하지 못했습니다: %r", fare)
            total_fare = 0.0

        return RouteSegment(
            from_poi_id=origin.poi_id,
            to_poi_id=destination.poi_id,
            preference=preference,
            total_duration_min=round(_seconds(route.get("duration")) / 60),
            total_fare=round(total_fare, 2),
            fare_currency=fare.get("currencyCode"),
            legs=steps,
        )

    def _extract_operators(self, payload: dict) -> list[Operator]:
        """응답에서 운영기관(이름·URL)을 중복 없이 모은다.

        Google Maps 약관은 경로를 화면에 표시할 때 운영기관 표기를 요구한다.
        URL 은 하드코딩하지 말고 응답이 준 값을 그대로 렌더링해야 한다.
        `agencies` 는 배열이다 — 한 노선에 공동 운영기관이 여럿일 수 있다.
        """
        seen: dict[tuple[str, str | None], Operator] = {}
        route = (payload.get("routes") or [{}])[0]
        for leg in route.get("legs", []):
            for step in leg.get("steps", []):
                line = step.get("transitDetails", {}).get("transitLine", {})
                for agency in line.get("agencies", []):
                    name = agency.get("name")
                    if not name:
                        continue
                    uri = agency.get("uri")
                    seen.setdefault((name, uri), Operator(name=name, url=uri))
        return list(seen.values())

    def _to_leg(self, step: dict) -> RouteLeg | None:
        """step 하나를 RouteLeg 로 바꾼다. 길이 0인 도보는 버린다."""
        duration = round(_seconds(step.get("staticDuration")) / 60)

        if step.get("travelMode") != "TRANSIT":
            if duration <= 0:
                return None
            distance_m = step.get("distanceMeters", 0)
            instruction = step.get("navigationInstruction", {}).get("instructions", "도보")
            return RouteLeg(
                mode="walk",
                from_name=instruction,
                to_name="",
                duration_min=duration,
                description=f"도보 {duration}분 ({distance_m}m)",
            )

        detail = step.get("transitDetails", {})
        stop = detail.get("stopDetails", {})
        line = detail.get("transitLine", {})
        vehicle = line.get("vehicle", {}).get("type", "BUS")
        line_name = line.get("nameShort") or line.get("name")
        stops = detail.get("stopCount", 0)

        return RouteLeg(
            mode=_VEHICLE_TO_MODE.get(vehicle, "bus"),
            line_name=str(line_name) if line_name else None,
            from_name=stop.get("departureStop", {}).get("name", ""),
            to_name=stop.get("arrivalStop", {}).get("name", ""),
            duration_min=duration,
            # ★ Routes API v2 로 오면서 새로 얻은 값. 추정이 아니라 실제 편성 시각이다.
            depart_at=stop.get("departureTime"),
            arrive_at=stop.get("arrivalTime"),
            description=f"{line_name} 탑승 {stops}개 정거장",
        )
