"""경로 프로바이더 선택 로직과 두 어댑터의 응답 정규화를 검증한다.

외부 API 는 호출하지 않는다 (conventions.md: 외부 API 는 반드시 목으로 대체).
"""

import json
from unittest.mock import patch

import pytest

from backend.routing import GeoPoint, is_in_korea, select_provider
from backend.routing.google_provider import GoogleRouteProvider
from backend.routing.odsay_provider import OdsayRouteProvider
from backend.routing.provider import RouteProviderError

# ---------- 픽스처 ----------

BUSAN_STATION = GeoPoint(poi_id="p1", name="부산역", lat=35.1151, lng=129.0415)
HAEUNDAE = GeoPoint(poi_id="p2", name="해운대해수욕장", lat=35.1587, lng=129.1604)
TOKYO_STATION = GeoPoint(poi_id="p3", name="도쿄역", lat=35.6812, lng=139.7671)
SHIBUYA = GeoPoint(poi_id="p4", name="시부야역", lat=35.6580, lng=139.7016)


# ---------- 국가 판정 ----------

@pytest.mark.parametrize(
    ("point", "expected"),
    [(BUSAN_STATION, True), (HAEUNDAE, True), (TOKYO_STATION, False), (SHIBUYA, False)],
)
def test_is_in_korea(point, expected):
    """좌표가 국내인지 판정한다."""
    assert is_in_korea(point.lat, point.lng) is expected


# ---------- 프로바이더 선택 ----------

def test_domestic_route_uses_odsay():
    """국내 구간은 ODsay 프로바이더를 고른다."""
    assert isinstance(select_provider(BUSAN_STATION, HAEUNDAE), OdsayRouteProvider)


def test_overseas_route_uses_google():
    """해외 구간은 Google 프로바이더를 고른다."""
    assert isinstance(select_provider(TOKYO_STATION, SHIBUYA), GoogleRouteProvider)


def test_cross_border_route_uses_google():
    """ODsay 는 국가 간 이동을 처리하지 못하므로 Google 로 넘겨야 한다."""
    assert isinstance(select_provider(BUSAN_STATION, TOKYO_STATION), GoogleRouteProvider)


# ---------- 캐시 키 ----------

def test_cache_key_varies_by_preference():
    """같은 요청은 같은 키, 선호도가 다르면 다른 키를 만든다."""
    provider = OdsayRouteProvider()
    same = provider.cache_key(BUSAN_STATION, HAEUNDAE, "fastest")
    assert same == provider.cache_key(BUSAN_STATION, HAEUNDAE, "fastest")
    assert same != provider.cache_key(BUSAN_STATION, HAEUNDAE, "fewest_transfers")


# ---------- ODsay 정규화 ----------

ODSAY_PAYLOAD = {
    "result": {
        "path": [
            {
                "info": {"totalTime": 40, "payment": 2100},
                "subPath": [
                    {"trafficType": 3, "sectionTime": 5, "distance": 350,
                     "startName": "부산역", "endName": "부산역 정류장"},
                    {"trafficType": 1, "sectionTime": 30, "stationCount": 12,
                     "startName": "부산역", "endName": "해운대역",
                     "lane": [{"name": "수도권 1호선"}]},
                    {"trafficType": 3, "sectionTime": 0, "distance": 0,
                     "startName": "해운대역", "endName": "해운대해수욕장"},
                ],
            }
        ]
    }
}


def test_odsay_normalizes_to_common_model():
    """ODsay 응답을 공통 RouteSegment 로 정규화한다."""
    segment = OdsayRouteProvider()._to_segment(
        ODSAY_PAYLOAD, BUSAN_STATION, HAEUNDAE, "fastest"
    )
    assert segment.total_duration_min == 40
    assert segment.total_fare == 2100
    assert segment.fare_currency == "KRW"
    # 길이 0인 마지막 도보는 버려지므로 2개만 남는다.
    assert [leg.mode for leg in segment.legs] == ["walk", "subway"]
    assert segment.legs[1].line_name == "수도권 1호선"


def test_odsay_raises_when_no_path():
    """경로가 비면 예외를 던진다."""
    with pytest.raises(RouteProviderError):
        OdsayRouteProvider()._to_segment({"result": {"path": []}},
                                         BUSAN_STATION, HAEUNDAE, "fastest")


# ---------- Google 정규화 ----------

# Routes API v2 (computeRoutes) 응답 형태.
# ⚠️ 실제 응답을 복사한 것이 아니라 구조만 흉내 낸 목이다 (Google 약관: 응답 저장 금지).
GOOGLE_PAYLOAD = {
    "routes": [
        {
            "duration": "1500s",
            "travelAdvisory": {"transitFare": {"currencyCode": "EUR", "units": "2",
                                              "nanos": 550000000}},
            "legs": [
                {
                    "steps": [
                        {"travelMode": "WALK", "staticDuration": "240s",
                         "distanceMeters": 300,
                         "navigationInstruction": {"instructions": "도쿄역까지 도보"}},
                        {"travelMode": "TRANSIT", "staticDuration": "1260s",
                         "transitDetails": {
                             "stopCount": 5,
                             "stopDetails": {
                                 "departureStop": {"name": "도쿄역"},
                                 "arrivalStop": {"name": "시부야역"},
                                 "departureTime": "2026-09-08T01:05:00Z",
                                 "arrivalTime": "2026-09-08T01:26:00Z",
                             },
                             "transitLine": {
                                 "nameShort": "JY", "name": "야마노테선",
                                 "vehicle": {"type": "HEAVY_RAIL"},
                                 "agencies": [{"name": "JR East",
                                               "uri": "https://www.jreast.co.jp/"}],
                             },
                         }},
                    ],
                }
            ],
        }
    ],
}


def test_google_normalizes_to_common_model():
    """Routes API v2 응답을 공통 RouteSegment 로 정규화한다."""
    segment = GoogleRouteProvider()._to_segment(
        GOOGLE_PAYLOAD, TOKYO_STATION, SHIBUYA, "fastest"
    )
    assert segment.total_duration_min == 25  # "1500s" → 25분
    # 2.55 EUR — units 만 읽으면 2 로 깎인다. nanos 를 더해야 맞다.
    assert segment.total_fare == 2.55
    assert segment.fare_currency == "EUR"
    assert [leg.mode for leg in segment.legs] == ["walk", "subway"]
    assert segment.legs[1].from_name == "도쿄역"


def test_google_keeps_scheduled_times():
    """편성 출발·도착 시각을 버리지 않는다 — C1 막차 경고와 W3 위험도의 입력이다."""
    segment = GoogleRouteProvider()._to_segment(
        GOOGLE_PAYLOAD, TOKYO_STATION, SHIBUYA, "fastest"
    )
    transit = segment.legs[1]
    assert transit.depart_at == "2026-09-08T01:05:00Z"
    assert transit.arrive_at == "2026-09-08T01:26:00Z"
    # 도보 구간에는 편성 시각이 없다.
    assert segment.legs[0].depart_at is None


def test_odsay_has_no_scheduled_times():
    """ODsay 는 배차간격만 주므로 편성 시각이 비어 있어야 한다 (추정을 넣지 말 것)."""
    segment = OdsayRouteProvider()._to_segment(
        ODSAY_PAYLOAD, BUSAN_STATION, HAEUNDAE, "fastest"
    )
    assert all(leg.depart_at is None for leg in segment.legs)


def test_both_providers_share_schema():
    """어댑터가 달라도 호출부는 동일한 RouteSegment 만 본다 — 추상화의 핵심."""
    odsay = OdsayRouteProvider()._to_segment(
        ODSAY_PAYLOAD, BUSAN_STATION, HAEUNDAE, "fastest")
    google = GoogleRouteProvider()._to_segment(
        GOOGLE_PAYLOAD, TOKYO_STATION, SHIBUYA, "fastest")
    assert set(json.loads(odsay.model_dump_json())) == set(
        json.loads(google.model_dump_json()))


# ---------- 캐싱 정책 (약관 준수) ----------

def test_google_never_writes_cache():
    """Google 약관은 응답 저장·캐싱을 금지한다 — 디스크에 아무것도 남기면 안 된다."""
    provider = GoogleRouteProvider()
    assert provider.cacheable is False
    with patch.object(GoogleRouteProvider, "_request", return_value=GOOGLE_PAYLOAD), \
         patch("backend.routing.provider.save_cache") as saver, \
         patch("backend.routing.provider.load_cached") as loader:
        provider.fetch_route(TOKYO_STATION, SHIBUYA, "fastest")
    assert saver.call_count == 0
    assert loader.call_count == 0


def test_odsay_uses_cache():
    """ODsay 는 무료 호출 한도(Basic 30회/일)가 빡빡하므로 로컬 캐시를 쓴다."""
    provider = OdsayRouteProvider()
    assert provider.cacheable is True
    with patch.object(OdsayRouteProvider, "_request", return_value=ODSAY_PAYLOAD), \
         patch("backend.routing.provider.save_cache") as saver, \
         patch("backend.routing.provider.load_cached", return_value=None):
        provider.fetch_route(BUSAN_STATION, HAEUNDAE, "fastest")
    assert saver.call_count == 1
