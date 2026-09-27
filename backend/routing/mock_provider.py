"""모의 경로 프로바이더 — `ROUTING_MOCK=1` 일 때만 쓰인다.

Google 키가 없는 환경(CI, 팀원 PC, 프론트 개발)에서도 화면 전체를 끝까지 돌려 보기 위한
도구다. 실제 노선·시간표가 **아니다.** 직선거리로 소요 시간을 만들고, 운영기관 칸에
"모의 경로"라고 표시한다. 데모·심사 화면에서는 켜지 않는다(README 참고).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from backend.routing.planner import haversine_km
from backend.routing.provider import (
    AlternativeRoute,
    GeoPoint,
    Operator,
    PathPoint,
    RouteProvider,
)
from shared.types.models import RouteLeg, RoutePreference, RouteSegment

MOCK_OPERATOR = Operator(name="모의 경로(실제 운행 정보 아님)", url=None)
_SPEED_KMH = 22.0
_WALK_IN, _WALK_OUT, _TRANSFER_WALK = 4, 3, 4


class MockRouteProvider(RouteProvider):
    """직선거리 기반 가짜 대중교통 경로. 조금 돌아가는 대안 경로 1개를 함께 준다."""

    name = "mock"
    cacheable = False

    def _request(
        self,
        origin: GeoPoint,
        destination: GeoPoint,
        preference: RoutePreference,
        depart_at: str | None = None,
    ) -> dict:
        """외부 호출 없이 응답 흉내를 만든다."""
        km = haversine_km(origin.lat, origin.lng, destination.lat, destination.lng)
        ride = max(round(km / _SPEED_KMH * 60), 3)
        ends = [(origin.lat, origin.lng), (destination.lat, destination.lng)]
        detour = ((origin.lat + destination.lat) / 2 + 0.004, (origin.lng + destination.lng) / 2)
        return {
            "depart_at": depart_at,
            "routes": [
                {"ride": ride, "rides": 1, "path": ends},
                {"ride": ride + 8, "rides": 2, "path": [ends[0], detour, ends[1]]},
            ],
        }

    def _to_segment(
        self,
        payload: dict,
        origin: GeoPoint,
        destination: GeoPoint,
        preference: RoutePreference,
    ) -> RouteSegment:
        """첫 번째 모의 경로."""
        return _segment(payload, payload["routes"][0], origin, destination, preference)

    def _extract_operators(self, payload: dict) -> list[Operator]:
        """모의 운영기관 표기."""
        return [MOCK_OPERATOR]

    def _extract_path(self, payload: dict) -> list[PathPoint]:
        """모의 경로 좌표."""
        return payload["routes"][0]["path"]

    def _extract_alternatives(
        self,
        payload: dict,
        origin: GeoPoint,
        destination: GeoPoint,
        preference: RoutePreference,
    ) -> list[AlternativeRoute]:
        """두 번째 모의 경로를 대안으로."""
        route = payload["routes"][1]
        return [
            AlternativeRoute(
                segment=_segment(payload, route, origin, destination, preference),
                operators=[MOCK_OPERATOR],
                path=route["path"],
            )
        ]


def _segment(
    payload: dict,
    route: dict,
    origin: GeoPoint,
    destination: GeoPoint,
    preference: RoutePreference,
) -> RouteSegment:
    """모의 route → RouteSegment (도보 → 탑승 N회 → 도보)."""
    start = payload.get("depart_at")
    clock = datetime.fromisoformat(start) + timedelta(minutes=_WALK_IN) if start else None
    legs = [_walk(origin.name, "", _WALK_IN)]
    per_ride = max(route["ride"] // route["rides"], 2)
    for index in range(route["rides"]):
        if index:
            legs.append(_walk("환승", "", _TRANSFER_WALK))
        legs.append(
            RouteLeg(
                mode="subway",
                line_name=f"M{index + 1}",
                from_name=f"모의 정류장 {index + 1}",
                to_name=f"모의 정류장 {index + 2}",
                duration_min=per_ride,
                depart_at=clock.isoformat() if clock else None,
                arrive_at=(clock + timedelta(minutes=per_ride)).isoformat() if clock else None,
                description="모의 노선",
            )
        )
        if clock:
            clock += timedelta(minutes=per_ride + _TRANSFER_WALK)
    legs.append(_walk("", destination.name, _WALK_OUT))
    return RouteSegment(
        from_poi_id=origin.poi_id,
        to_poi_id=destination.poi_id,
        preference=preference,
        total_duration_min=sum(leg.duration_min for leg in legs),
        total_fare=2.0,
        fare_currency=None,
        legs=legs,
    )


def _walk(from_name: str, to_name: str, minutes: int) -> RouteLeg:
    """모의 도보 leg."""
    return RouteLeg(
        mode="walk",
        from_name=from_name,
        to_name=to_name,
        duration_min=minutes,
        description=f"도보 {minutes}분 (모의)",
    )
