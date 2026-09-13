"""2지점 실경로 모듈(`backend/routing/planner.py`) 검증.

외부 API 는 호출하지 않는다 (conventions.md: 외부 API 는 반드시 목으로 대체).
Google 응답 목은 실제 응답을 복사한 것이 아니라 **구조만 흉내 낸 것**이다
(Google 약관: 응답 저장·커밋 금지). 필드 경로는 9/6 필드 확인 결과를 따랐다.
"""

from unittest.mock import patch

import pytest

from backend.routing.google_provider import GoogleRouteProvider
from backend.routing.planner import (
    WARN_DURATION_MIN,
    WARN_TRANSFER_COUNT,
    SegmentRoute,
    build_advisories,
    count_transfers,
    merge_walk_legs,
    plan_segment,
)
from backend.routing.provider import GeoPoint, NoRouteError, RouteProviderError
from shared.types.models import RouteLeg

# ---------- 픽스처 ----------

# 파리 — 지원 도시(데모). 도쿄·오사카는 TRANSIT 미반환으로 화이트리스트에서 제외됐다.
CHATELET = GeoPoint(poi_id="p1", name="샤틀레", lat=48.8586, lng=2.3470)
MONTMARTRE = GeoPoint(poi_id="p2", name="몽마르트", lat=48.8867, lng=2.3431)
LOUVRE = GeoPoint(poi_id="p3", name="루브르 박물관", lat=48.8606, lng=2.3376)
# 루브르에서 직선 약 335m — 사전 필터(800m)에 걸려 외부 호출이 일어나지 않는 구간
PALAIS_ROYAL = GeoPoint(poi_id="p4", name="팔레 루아얄", lat=48.8636, lng=2.3372)
VERSAILLES = GeoPoint(poi_id="p5", name="베르사유 궁전", lat=48.8049, lng=2.1204)
FAR_AWAY = GeoPoint(poi_id="p9", name="타이베이101", lat=25.0339, lng=121.5645)


def _transit_step(duration_s: str, line: str, agency: str) -> dict:
    """TRANSIT step 하나. 구조만 흉내 낸 목이다."""
    return {
        "travelMode": "TRANSIT",
        "staticDuration": duration_s,
        "transitDetails": {
            "stopCount": 4,
            "stopDetails": {
                "departureStop": {"name": f"{line} 승차"},
                "arrivalStop": {"name": f"{line} 하차"},
                "departureTime": "2026-10-15T07:05:00Z",
                "arrivalTime": "2026-10-15T07:26:00Z",
            },
            "transitLine": {
                "nameShort": line,
                "vehicle": {"type": "SUBWAY"},
                "agencies": [{"name": agency, "uri": "https://www.ratp.fr/"}],
            },
        },
    }


def _payload(total_duration_s: str, lines: list[str]) -> dict:
    """지정한 노선 수만큼 탑승하는 응답 목."""
    return {
        "routes": [
            {
                "duration": total_duration_s,
                "travelAdvisory": {
                    "transitFare": {"currencyCode": "EUR", "units": "2", "nanos": 550000000}
                },
                "legs": [{"steps": [_transit_step("600s", line, "RATP") for line in lines]}],
            }
        ]
    }


SHORT_PAYLOAD = _payload("1500s", ["4"])  # 25분 · 직통
LONG_PAYLOAD = _payload("4920s", ["4", "12", "RER C", "B"])  # 82분 · 환승 3회


# ---------- 정상 구간 ----------

def test_returns_segment_route():
    """임의 두 지점 입력 시 SegmentRoute 가 반환된다."""
    with patch.object(GoogleRouteProvider, "_request", return_value=SHORT_PAYLOAD):
        result = plan_segment(CHATELET, MONTMARTRE, depart_at="2026-10-15T09:00:00+02:00")

    assert isinstance(result, SegmentRoute)
    assert result.primary.total_duration_min == 25
    assert result.transfer_count == 0
    assert result.advisories == []
    # 절단 2 — 예선에서는 택시 대안을 만들지 않는다.
    assert result.alternative is None


def test_keeps_scheduled_times():
    """편성 출발·도착 시각이 구간 결과까지 살아서 온다 (C1 막차 경고의 입력)."""
    with patch.object(GoogleRouteProvider, "_request", return_value=SHORT_PAYLOAD):
        result = plan_segment(CHATELET, MONTMARTRE, depart_at="2026-10-15T09:00:00+02:00")

    assert result.primary.legs[0].depart_at == "2026-10-15T07:05:00Z"
    assert result.primary.legs[0].arrive_at == "2026-10-15T07:26:00Z"


def test_maps_operators_for_attribution():
    """운영기관 이름·URL 이 transitLine.agencies[] 에서 매핑된다 (약관 표기 의무)."""
    with patch.object(GoogleRouteProvider, "_request", return_value=SHORT_PAYLOAD):
        result = plan_segment(CHATELET, MONTMARTRE)

    assert [op.name for op in result.operators] == ["RATP"]
    assert result.operators[0].url == "https://www.ratp.fr/"


def test_operators_are_deduplicated():
    """같은 운영기관이 여러 leg 에 나와도 한 번만 표기한다."""
    with patch.object(GoogleRouteProvider, "_request", return_value=LONG_PAYLOAD):
        result = plan_segment(CHATELET, VERSAILLES)

    assert len(result.operators) == 1


# ---------- 긴 구간 — 경고 배지 ----------

def test_long_segment_gets_advisories():
    """60분 초과·환승 3회 이상이면 경고 배지가 붙는다 (대안은 제시하지 않는다)."""
    with patch.object(GoogleRouteProvider, "_request", return_value=LONG_PAYLOAD):
        result = plan_segment(CHATELET, VERSAILLES, depart_at="2026-10-15T09:00:00+02:00")

    assert result.transfer_count == 3
    assert {a.code for a in result.advisories} == {"long_duration", "many_transfers"}
    assert result.alternative is None  # 절단 2 — DRIVING 재호출이 없어야 한다


def test_advisory_thresholds_are_exclusive_and_inclusive():
    """기준선 자체에서 오작동하지 않는지 확인한다."""
    assert build_advisories(WARN_DURATION_MIN, 0) == []            # 60분 '초과'만 발동
    assert build_advisories(WARN_DURATION_MIN + 1, 0)[0].code == "long_duration"
    assert build_advisories(10, WARN_TRANSFER_COUNT - 1) == []     # 3회 '이상' 발동
    assert build_advisories(10, WARN_TRANSFER_COUNT)[0].code == "many_transfers"


def test_consecutive_walk_legs_are_merged():
    """Routes v2 는 도보를 회전 안내 단위로 쪼개 준다 — 탑승 사이 도보는 하나로 합친다."""
    legs = [
        RouteLeg(mode="walk", from_name="북서쪽으로 걷기", to_name="",
                 duration_min=1, description=""),
        RouteLeg(mode="walk", from_name="우회전", to_name="", duration_min=3, description=""),
        RouteLeg(mode="walk", from_name="램프로 우회전", to_name="",
                 duration_min=1, description=""),
        RouteLeg(mode="bus", from_name="Pont d'Iéna", to_name="Quai François Mitterrand",
                 duration_min=15, description=""),
        RouteLeg(mode="walk", from_name="우회전", to_name="", duration_min=2, description=""),
    ]
    merged = merge_walk_legs(legs)

    assert [leg.mode for leg in merged] == ["walk", "bus", "walk"]
    assert merged[0].duration_min == 5  # 1 + 3 + 1
    assert merged[0].description == "도보 5분"
    assert merged[1].duration_min == 15  # 탑승 구간은 건드리지 않는다


def test_merge_keeps_boarding_times():
    """합치기가 편성 시각을 건드리지 않는다 (도보에는 애초에 시각이 없다)."""
    with patch.object(GoogleRouteProvider, "_request", return_value=SHORT_PAYLOAD):
        result = plan_segment(CHATELET, MONTMARTRE, depart_at="2026-10-15T09:00:00+02:00")

    boarding = [leg for leg in result.primary.legs if leg.mode != "walk"]
    assert boarding[0].depart_at == "2026-10-15T07:05:00Z"


def test_count_transfers_ignores_walking():
    """도보는 환승 횟수에 들어가지 않는다."""
    legs = [
        RouteLeg(mode="walk", from_name="a", to_name="b", duration_min=5, description=""),
        RouteLeg(mode="subway", from_name="b", to_name="c", duration_min=10, description=""),
        RouteLeg(mode="walk", from_name="c", to_name="d", duration_min=3, description=""),
        RouteLeg(mode="bus", from_name="d", to_name="e", duration_min=8, description=""),
    ]
    assert count_transfers(legs) == 1


# ---------- 경로 없음 ----------

def test_no_route_returns_none_not_exception():
    """경로가 없으면 예외가 아니라 None. 스케줄러가 다른 후보로 넘어간다."""
    with patch.object(GoogleRouteProvider, "_request", side_effect=NoRouteError("없음")):
        assert plan_segment(CHATELET, MONTMARTRE) is None


def test_api_failure_still_raises():
    """키 미설정·API 오류는 삼키지 않는다 — 우리가 고쳐야 할 버그다."""
    with patch.object(
        GoogleRouteProvider, "_request", side_effect=RouteProviderError("키 없음")
    ), pytest.raises(RouteProviderError):
        plan_segment(CHATELET, MONTMARTRE)


# ---------- 사전 필터 — 호출 절감 ----------

def test_short_segment_skips_external_call():
    """직선거리 800m 미만이면 외부 호출 없이 도보 구간을 만든다."""
    with patch.object(GoogleRouteProvider, "_request") as request:
        result = plan_segment(LOUVRE, PALAIS_ROYAL)

    assert request.call_count == 0
    assert [leg.mode for leg in result.primary.legs] == ["walk"]
    assert result.primary.total_duration_min > 0
    # 도보에는 편성 시각이 없다 — 추정으로 채우지 않는다.
    assert result.primary.legs[0].depart_at is None


def test_too_far_segment_returns_none_without_call():
    """도시 내 이동이 아닌 구간은 호출하지 않고 None."""
    with patch.object(GoogleRouteProvider, "_request") as request:
        assert plan_segment(CHATELET, FAR_AWAY) is None
    assert request.call_count == 0


# ---------- 출발 시각 전달 ----------

def test_departure_time_is_sent_to_routes_api():
    """depart_at 이 요청 본문의 departureTime 으로 실려야 한다.

    빠뜨리면 시간표 기반 결과가 오지 않아 depart_at / arrive_at 이 '지금 출발' 기준이 된다.
    """
    captured: dict = {}

    class _Response:
        def json(self) -> dict:
            return SHORT_PAYLOAD

        def raise_for_status(self) -> None:
            return None

    def _fake_post(url, json, headers, timeout):  # noqa: ANN001, ANN202, A002
        captured.update(json)
        return _Response()

    with patch("backend.routing.google_provider.httpx.post", side_effect=_fake_post), \
         patch("backend.routing.google_provider.get_settings") as settings:
        settings.return_value.google_backend_api_key = "test-key"
        plan_segment(CHATELET, MONTMARTRE, depart_at="2026-10-15T09:00:00+02:00")

    assert captured["travelMode"] == "TRANSIT"
    assert captured["departureTime"] == "2026-10-15T09:00:00+02:00"


def test_no_departure_time_key_when_omitted():
    """출발 시각을 안 주면 키 자체를 보내지 않는다 (빈 문자열은 INVALID_ARGUMENT)."""
    captured: dict = {}

    class _Response:
        def json(self) -> dict:
            return SHORT_PAYLOAD

        def raise_for_status(self) -> None:
            return None

    def _fake_post(url, json, headers, timeout):  # noqa: ANN001, ANN202, A002
        captured.update(json)
        return _Response()

    with patch("backend.routing.google_provider.httpx.post", side_effect=_fake_post), \
         patch("backend.routing.google_provider.get_settings") as settings:
        settings.return_value.google_backend_api_key = "test-key"
        plan_segment(CHATELET, MONTMARTRE)

    assert "departureTime" not in captured
