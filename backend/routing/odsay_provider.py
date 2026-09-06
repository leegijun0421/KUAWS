"""ODsay 대중교통 길찾기 어댑터 (국내 구간 전용).

ODsay 응답의 필드 구조는 `docs/odsay_sample_response.json` 과
`inspect_odsay.py` 의 체크리스트를 근거로 한다.
"""

from __future__ import annotations

import httpx

from backend.common.config import get_settings
from backend.common.logging import get_logger
from backend.routing.provider import (
    GeoPoint,
    RouteProvider,
    RouteProviderError,
)
from shared.types.models import RouteLeg, RoutePreference, RouteSegment

logger = get_logger(__name__)

_ENDPOINT = "https://api.odsay.com/v1/api/searchPubTransPathT"

#: ODsay trafficType 코드 → 공통 모델의 mode
_TRAFFIC_TYPE_TO_MODE: dict[int, str] = {1: "subway", 2: "bus"}

#: 서비스의 경로 선호도 → ODsay searchPathType
#: ODsay 는 "환승 최소" 옵션이 없어 지하철 우선(1)으로 근사한다.
_PREFERENCE_TO_SEARCH_TYPE: dict[str, int] = {
    "fastest": 0,
    "fewest_transfers": 1,
    "scenic": 0,
}


class OdsayRouteProvider(RouteProvider):
    """ODsay API 로 국내 대중교통 경로를 조회한다."""

    name = "odsay"

    #: ODsay 이용약관 4.5.10 — 사전 동의 없는 결과 데이터의 복제·저장·배포 금지.
    #: 무료 호출 한도(Basic 30회/일)를 넘기지 않기 위한 개발용 로컬 캐시로만 쓰며,
    #: 캐시 파일은 리포에 커밋하지 않는다(data/processed/ 는 .gitignore 대상).
    cacheable = True

    def _request(
        self, origin: GeoPoint, destination: GeoPoint, preference: RoutePreference
    ) -> dict:
        """ODsay 에 실제로 요청한다. 캐시가 없을 때만 호출된다."""
        api_key = get_settings().odsay_api_key
        if not api_key:
            raise RouteProviderError("ODSAY_API_KEY 가 설정되지 않았습니다.")

        params = {
            "apiKey": api_key,
            "SX": origin.lng,
            "SY": origin.lat,
            "EX": destination.lng,
            "EY": destination.lat,
            "SearchPathType": _PREFERENCE_TO_SEARCH_TYPE[preference],
        }
        try:
            response = httpx.get(_ENDPOINT, params=params, timeout=10.0)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise RouteProviderError(f"ODsay 호출 실패: {exc}") from exc

        payload = response.json()
        # ODsay 는 실패 시 result 대신 error 노드를 반환한다.
        if "error" in payload:
            raise RouteProviderError(f"ODsay 오류 응답: {payload['error']}")
        return payload

    def _to_segment(
        self,
        payload: dict,
        origin: GeoPoint,
        destination: GeoPoint,
        preference: RoutePreference,
    ) -> RouteSegment:
        """ODsay 응답을 공통 RouteSegment 로 정규화한다."""
        paths = payload.get("result", {}).get("path", [])
        if not paths:
            raise RouteProviderError("ODsay 가 경로를 반환하지 않았습니다.")

        best = paths[0]
        info = best.get("info", {})
        legs = [
            leg
            for sub in best.get("subPath", [])
            if (leg := self._to_leg(sub)) is not None
        ]
        return RouteSegment(
            from_poi_id=origin.poi_id,
            to_poi_id=destination.poi_id,
            preference=preference,
            total_duration_min=int(info.get("totalTime", 0)),
            total_fare=float(info.get("payment", 0)),
            fare_currency="KRW",  # ODsay 는 국내 전용이라 통화가 고정이다
            legs=legs,
        )

    def _to_leg(self, sub: dict) -> RouteLeg | None:
        """subPath 한 칸을 RouteLeg 로 바꾼다. 길이 0인 도보는 버린다."""
        traffic_type = sub.get("trafficType")
        duration = int(sub.get("sectionTime", 0))

        if traffic_type == 3:  # 도보
            if duration <= 0:
                return None
            return RouteLeg(
                mode="walk",
                from_name=sub.get("startName", "출발"),
                to_name=sub.get("endName", "도착"),
                duration_min=duration,
                description=f"도보 {duration}분 ({sub.get('distance', 0)}m)",
            )

        mode = _TRAFFIC_TYPE_TO_MODE.get(traffic_type, "transfer")
        lane = (sub.get("lane") or [{}])[0]
        line_name = lane.get("name") or lane.get("busNo") or lane.get("subwayCode")
        return RouteLeg(
            mode=mode,
            line_name=str(line_name) if line_name else None,
            from_name=sub.get("startName", ""),
            to_name=sub.get("endName", ""),
            duration_min=duration,
            description=f"{line_name} 탑승 {sub.get('stationCount', 0)}개 정거장",
        )
