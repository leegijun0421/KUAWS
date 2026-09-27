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
from backend.routing.scenic import ScenicPoi, recommend_route
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


def _pois_around(lat: float, nature: float, category: str) -> list[ScenicPoi]:
    return [ScenicPoi(name=f"{category}{i}", lat=lat + i * 0.0005, lng=lat, category=category,
                      features=[0.5, 0.5, nature, 0.2, 0.5]) for i in range(3)]


def _two_routes(primary_min: int = 20, alt_min: int = 26) -> SegmentRoute:
    alt_segment = RouteSegment(from_poi_id="a", to_poi_id="b", preference="fastest",
                               total_duration_min=alt_min, total_fare=0, legs=[])
    alt = AlternativeRoute(segment=alt_segment, path=[(1.0, 1.0)])
    return segment(primary_min, path=[(5.0, 5.0)], alts=[alt])


def test_scenic_route_recommended_for_nature_loving_group():
    pois = _pois_around(1.0, 0.05, "nature") + _pois_around(5.0, 0.95, "attraction")
    option, recommended = recommend_route(_two_routes(), pois, [0.5, 0.5, 0.1, 0.5, 0.5])
    assert option is not None and option.extra_min == 6
    assert recommended == "scenic" and "6분 더 걸리지만" in option.reason
    assert option.segment.preference == "scenic"
    _, urban_pick = recommend_route(_two_routes(), pois, [0.5, 0.5, 0.95, 0.5, 0.5])
    assert urban_pick == "fastest"  # 도심 선호 그룹에는 최단을 권한다(대안은 계속 병기)


def test_scenic_skipped_for_short_segments_and_sparse_areas():
    pois = _pois_around(1.0, 0.05, "nature") + _pois_around(5.0, 0.95, "attraction")
    assert recommend_route(_two_routes(primary_min=10), pois, [0.5] * 5) == (None, "fastest")
    assert recommend_route(_two_routes(), pois[:2] + pois[3:], [0.5] * 5) == (None, "fastest")
    assert recommend_route(_two_routes(alt_min=60), pois, [0.5] * 5) == (None, "fastest")


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


def test_segment_risk_flags_use_real_timetable_sentences():
    from zoneinfo import ZoneInfo

    from backend.planner.risk import risk_summary, segment_flags

    legs = [
        RouteLeg(mode="bus", line_name="87", from_name="a", to_name="Bastille", duration_min=10,
                 depart_at="2026-10-14T08:00:00Z", arrive_at="2026-10-14T08:10:00Z", description=""),
        RouteLeg(mode="walk", from_name="", to_name="", duration_min=2, description=""),
        RouteLeg(mode="subway", line_name="RER A", from_name="c", to_name="d", duration_min=10,
                 depart_at="2026-10-14T08:16:00Z", arrive_at="2026-10-14T08:26:00Z", description=""),
    ]
    flags = segment_flags(segment(26, legs), ZoneInfo("Europe/Paris"))
    assert len(flags) == 1 and flags[0].level == "high"
    assert flags[0].reason == "Bastille에서 버스 87 → RER A 환승 여유 4분 (10:10 도착 · 10:16 출발)"
    assert risk_summary([flags, []]) == "2일 일정 중 주의 구간 0곳, 위험 구간 1곳"
    assert "모든 환승 여유" in risk_summary([[]])


def test_time_constraint_narrows_day_window(monkeypatch):
    client = _mock_client(monkeypatch)
    late = {**PLAN, "constraints": {**PLAN["constraints"], "earliestStart": "11:00"}}
    body = client.post("/api/planner/plan", json=late).json()
    assert body["days"][0]["stops"][0]["arriveAt"] >= "11:00"


def test_empty_candidates_return_reason_not_crash(monkeypatch):
    client = _mock_client(monkeypatch)
    everything = ["cafe", "restaurant", "culture", "nature", "attraction"]
    blocked = {**PLAN, "constraints": {**PLAN["constraints"], "excludeCategories": everything}}
    res = client.post("/api/planner/plan", json=blocked)
    assert res.status_code == 200
    assert res.json()["days"][0]["stops"] == [] and res.json()["warnings"]


def test_placement_probes_past_vetoed_top_candidates(monkeypatch):
    """상위 후보가 실제 경로로 모두 거부돼도 아래 후보로 그날을 이어 간다(9/27 실측 회귀)."""
    from backend.planner import placement
    from backend.planner.schemas import MatchResult

    def fake_segment(origin, destination, depart_at=None, provider=None):  # noqa: ANN001
        # 앞의 세 후보만 실제 이동이 매우 길다 — 직선거리 추정과 실제가 어긋난 상황.
        return segment(200 if destination.poi_id.startswith("far") else 10)

    monkeypatch.setattr(placement, "plan_segment", fake_segment)
    pois = {pid: POIVector(poi_id=pid, name=pid, lat=48.85 + i * 0.001, lng=2.35,
                           avg_duration_min=60, opening=OpeningHours())
            for i, pid in enumerate(["start", "far1", "far2", "far3", "near"])}
    matches = [MatchResult(poi_id=pid, group_score=score, member_scores={})
               for pid, score in [("start", 0.9), ("far1", 0.8), ("far2", 0.8),
                                  ("far3", 0.8), ("near", 0.5)]]
    outcome = placement.place_days(matches, pois, None, 1,
                                   ScheduleConstraints(max_travel_min_per_day=120))
    assert [stop.poi_id for stop in outcome.stops][:2] == ["start", "near"]
