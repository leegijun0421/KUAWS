"""planner — 식사·막차 제약, 실패 위험도, 경치 경로, 브리핑, 일정/공유 API(모의 경로)."""

from datetime import datetime

from fastapi.testclient import TestClient

from backend.common.config import get_settings
from backend.main import app
from backend.planner.briefing import BriefingFacts, build_briefing
from backend.planner.constraints import DayState, adjust_arrival, day_warnings, veto_stop
from backend.planner.risk import stop_risk
from backend.planner.schemas import (
    MealWindow,
    OpeningHours,
    POIVector,
    ScheduleConstraints,
    ScheduledStop,
)
from backend.routing.planner import SegmentRoute
from backend.routing.provider import AlternativeRoute
from backend.routing.scenic import ScenicPoi, pick_scenic
from shared.types.models import RouteLeg, RouteSegment

MEALS = [MealWindow(label="점심", start_at="11:30", end_at="13:30"),
         MealWindow(label="저녁", start_at="18:00", end_at="20:00")]
WED = datetime(2026, 10, 14, 10, 0)  # 수요일


def vec(poi_id="p", meal=False, weekly=None, stay=60) -> POIVector:
    return POIVector(poi_id=poi_id, name=poi_id, lat=0, lng=0, is_meal=meal,
                     avg_duration_min=stay, opening=OpeningHours(weekly=weekly))


def stop(depart="17:00") -> ScheduledStop:
    return ScheduledStop(day=1, order=1, poi_id="x", name="x", arrive_at="16:00",
                         depart_at=depart, stay_min=60, group_score=0.5)


def segment(minutes: int, legs: list[RouteLeg] | None = None, path=None, alts=None) -> SegmentRoute:
    primary = RouteSegment(from_poi_id="a", to_poi_id="b", preference="fastest",
                           total_duration_min=minutes, total_fare=0, legs=legs or [])
    return SegmentRoute(primary=primary, transfer_count=0, path=path or [],
                        transit_alternatives=alts or [])


def test_meal_outside_window_is_vetoed_but_waiting_is_allowed():
    constraints = ScheduleConstraints(meal_windows=MEALS)
    state = DayState(day=1)
    assert veto_stop(vec(meal=True), WED, 0, state, constraints).code == "meal_outside_window"
    early = WED.replace(hour=17, minute=30)
    adjusted = adjust_arrival(vec(meal=True), early, state, constraints)
    assert adjusted.hour == 18 and adjusted.minute == 0  # 저녁 시작까지 30분 대기
    assert veto_stop(vec(meal=True), adjusted, 0, state, constraints) is None


def test_weekly_closed_day_is_vetoed():
    closed_wed = vec(weekly={2: []})
    assert veto_stop(closed_wed, WED, 0, DayState(day=1), ScheduleConstraints()).code == "closed"


def test_meals_do_not_count_toward_daily_sight_cap():
    constraints = ScheduleConstraints(meal_windows=MEALS, max_stops_per_day=1)
    state = DayState(day=1, stops=[stop()])
    assert veto_stop(vec(), WED, 0, state, constraints).code == "day_full"
    lunch = WED.replace(hour=12)
    assert veto_stop(vec(meal=True), lunch, 0, state, constraints) is None


def test_missing_meal_and_last_train_warnings():
    constraints = ScheduleConstraints(meal_windows=MEALS, last_train_margin_min=45,
                                      last_service_at="23:45", start_at="2026-10-14T09:30:00+08:00")
    late_leg = RouteLeg(mode="subway", from_name="a", to_name="b", duration_min=10,
                        depart_at="2026-10-14T15:20:00Z", arrive_at="2026-10-14T15:30:00Z",
                        description="")  # 현지 23:20 출발
    state = DayState(day=1, stops=[stop()], segments=[segment(10, [late_leg])])
    warnings = day_warnings(state, constraints)
    assert any("점심" in w for w in warnings) and any("저녁" in w for w in warnings)
    assert any("막차(23:45)까지 여유 25분" in w for w in warnings)


def test_risk_uses_real_timetable_connection_slack():
    legs = [
        RouteLeg(mode="subway", from_name="a", to_name="b", duration_min=10,
                 depart_at="2026-10-14T01:00:00Z", arrive_at="2026-10-14T01:10:00Z", description=""),
        RouteLeg(mode="walk", from_name="", to_name="", duration_min=2, description=""),
        RouteLeg(mode="bus", from_name="c", to_name="d", duration_min=10,
                 depart_at="2026-10-14T01:13:00Z", arrive_at="2026-10-14T01:23:00Z", description=""),
    ]
    inbound = segment(23, legs)
    inbound.transfer_count = 1
    probability, reasons = stop_risk(vec(), "10:00", "11:00", 2, inbound, 0.9)
    assert any("환승 연결 여유 1분" in r for r in reasons)
    assert 0.15 < probability < 0.95
    calm, calm_reasons = stop_risk(vec(), "10:00", "11:00", 2, None, 0.9)
    assert calm == 0.03 and calm_reasons == []


def test_scenic_alternative_is_chosen_only_when_clearly_better():
    park = ScenicPoi(name="강변 공원", lat=1.0, lng=1.0, category="nature", nature_vs_urban=0.0)
    alt_segment = RouteSegment(from_poi_id="a", to_poi_id="b", preference="fastest",
                               total_duration_min=18, total_fare=0, legs=[])
    alt = AlternativeRoute(segment=alt_segment, path=[(1.0, 1.0)])
    route = segment(12, path=[(5.0, 5.0)], alts=[alt])
    option = pick_scenic(route, [park])
    assert option is not None and option.extra_min == 6 and option.highlights == ["강변 공원"]
    assert option.segment.preference == "scenic"
    far = AlternativeRoute(segment=alt_segment.model_copy(update={"total_duration_min": 60}),
                           path=[(1.0, 1.0)])
    assert pick_scenic(segment(12, path=[(5.0, 5.0)], alts=[far]), [park]) is None


def test_briefing_is_3_to_4_template_sentences():
    facts = BriefingFacts(city_label="파리", days=2, member_names=["민지", "서연"],
                          categories=["culture", "culture", "nature"], stop_count=3,
                          meal_names=["A", "B", "C"], min_satisfaction=0.62, worst_member="서연",
                          avg_travel_min_per_day=40, scenic_count=1, warning_count=0)
    text = build_briefing(facts)
    assert "서연님도 62%" in text and "파리 2일" in text
    assert 3 <= text.count("요.") <= 5


PLAN = {
    "city": "paris", "days": 1, "startDate": "2026-10-14",
    "members": [
        {"memberId": "a", "memberName": "민지", "rawText": "", "updatedAt": "",
         "axes": [{"axis": x, "value": v, "confidence": 0.9} for x, v in
                  zip(["activity_level", "crowd_tolerance", "nature_vs_urban", "food_priority",
                       "pace"], [0.3, 0.4, 0.9, 0.6, 0.4])]},
    ],
    "constraints": {"excludeCategories": [], "avoidKeywords": ["fruits de mer"], "notes": []},
    "mustVisit": ["Musée du Louvre"],
}


def _mock_client(monkeypatch) -> TestClient:
    monkeypatch.setenv("ROUTING_MOCK", "1")
    get_settings.cache_clear()
    return TestClient(app)


def test_plan_api_end_to_end_with_mock_routes(monkeypatch):
    client = _mock_client(monkeypatch)
    res = client.post("/api/planner/plan", json=PLAN)
    assert res.status_code == 200, res.text
    body = res.json()
    stops = body["days"][0]["stops"]
    assert stops[0]["poi"]["name"] == "Musée du Louvre"  # must_visit 가 첫 스톱
    assert any(s["poi"]["category"] == "restaurant" for s in stops)  # 식사 배치
    assert all("Fruits de Mer" not in s["poi"]["name"] for s in stops)  # 알레르기 필터
    assert body["dataSource"] == "seed" and body["briefing"]
    seg = body["days"][0]["segments"][0]
    assert seg["operators"][0]["name"].startswith("모의 경로")  # 약관 표기 자리 채워짐
    assert 0 < body["minMemberSatisfaction"] <= 1


def test_share_roundtrip_replays_same_order(monkeypatch):
    client = _mock_client(monkeypatch)
    plan = client.post("/api/planner/plan", json=PLAN).json()
    order = [[s["poi"]["poiId"] for s in plan["days"][0]["stops"]]]
    link = client.post("/api/share", json={"request": PLAN, "dayOrders": order}).json()
    assert link["url"].endswith(f"/s/{link['planId']}")
    shared = client.get(f"/api/share/{link['planId']}").json()
    assert [s["poi"]["poiId"] for s in shared["days"][0]["stops"]] == order[0]
    assert client.get("/api/share/nope").status_code == 404


def test_cities_endpoint_lists_whitelist(monkeypatch):
    body = _mock_client(monkeypatch).get("/api/planner/cities").json()
    assert {c["key"] for c in body} == {"paris", "taipei"}
    assert all(c["poiCount"] > 0 for c in body)


def test_unknown_city_is_422(monkeypatch):
    res = _mock_client(monkeypatch).post("/api/planner/plan", json={**PLAN, "city": "tokyo"})
    assert res.status_code == 422


def test_cafes_limited_and_not_consecutive():
    constraints = ScheduleConstraints()
    cafe = POIVector(poi_id="c", name="c", lat=0, lng=0, category="cafe")
    state = DayState(day=1, last_category="cafe", cafes=1)
    assert veto_stop(cafe, WED, 0, state, constraints).code == "cafe_limit"
    assert veto_stop(cafe, WED, 0, DayState(day=1, cafes=2), constraints).code == "cafe_limit"
    assert veto_stop(cafe, WED, 0, DayState(day=1, cafes=1, last_category="culture"),
                     constraints) is None


def test_free_time_before_dinner_when_day_is_full():
    constraints = ScheduleConstraints(meal_windows=MEALS, max_stops_per_day=1)
    full = DayState(day=1, stops=[stop()])
    arrive = adjust_arrival(vec(meal=True), WED.replace(hour=16, minute=10), full, constraints)
    assert (arrive.hour, arrive.minute) == (18, 0)
    not_full = DayState(day=1)
    same = adjust_arrival(vec(meal=True), WED.replace(hour=16, minute=10), not_full, constraints)
    assert same.hour == 16
