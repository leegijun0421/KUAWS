"""C1 제약 스케줄러(`backend/planner/`) 검증.

외부 API 는 호출하지 않는다(conventions.md). 라우팅은 거리로 소요시간을 만들어 주는
가짜 프로바이더로 대체한다 — Google 응답을 복사해 두지 않는 것도 같은 이유다(약관).

완료 기준(노션 [W2] 제약 스케줄러 구현)과 1:1로 대응한다.
"""

from datetime import datetime

import pytest

from backend.planner import ScheduleConstraints, build_schedule
from backend.planner.placement import estimate_travel_min, pick_score
from backend.planner.schemas import MatchResult, OpeningHours, POIVector
from backend.routing.planner import haversine_km
from backend.routing.provider import RouteProvider
from shared.types.models import RouteLeg, RouteSegment

# ---------- 가짜 라우팅 ----------


class FakeProvider(RouteProvider):
    """직선거리에 비례한 소요시간을 돌려주는 목. 호출 횟수를 직접 센다."""

    name = "fake"
    cacheable = False

    def __init__(self) -> None:
        self.calls = 0

    def _request(self, origin, destination, preference, depart_at=None) -> dict:
        self.calls += 1
        return {"depart_at": depart_at}

    def _to_segment(self, payload, origin, destination, preference) -> RouteSegment:
        km = haversine_km(origin.lat, origin.lng, destination.lat, destination.lng)
        minutes = max(5, round(km * 4))
        leg = RouteLeg(
            mode="subway",
            line_name="M1",
            from_name=origin.name,
            to_name=destination.name,
            duration_min=minutes,
            description=f"지하철 {minutes}분",
        )
        return RouteSegment(
            from_poi_id=origin.poi_id,
            to_poi_id=destination.poi_id,
            preference=preference,
            total_duration_min=minutes,
            total_fare=2.05,
            fare_currency="EUR",
            legs=[leg],
        )


class NoRouteProvider(FakeProvider):
    """어떤 구간도 경로가 없다고 답하는 목."""

    def _to_segment(self, payload, origin, destination, preference) -> RouteSegment:
        raise AssertionError("경로 없음 목에서는 호출되지 않아야 한다")

    def _request(self, origin, destination, preference, depart_at=None) -> dict:
        from backend.routing.provider import NoRouteError

        self.calls += 1
        raise NoRouteError("이 구간에 대중교통 경로가 없습니다")


# ---------- 픽스처 ----------

PARIS_START = "2026-10-15T09:00:00+02:00"


def make_pois(count: int, *, opening: OpeningHours | None = None) -> dict[str, POIVector]:
    """파리 도심에 1km 남짓 간격으로 흩어진 더미 POI 를 만든다."""
    pois: dict[str, POIVector] = {}
    for index in range(count):
        poi_id = f"p{index}"
        pois[poi_id] = POIVector(
            poi_id=poi_id,
            name=f"장소{index}",
            lat=48.8500 + index * 0.010,
            lng=2.3300 + (index % 4) * 0.012,
            avg_duration_min=90,
            opening=opening or OpeningHours(),
        )
    return pois


def make_candidates(pois: dict[str, POIVector]) -> list[MatchResult]:
    """점수 내림차순 후보 목록. B2 출력 자리를 대신한다."""
    return [
        MatchResult(poi_id=poi_id, group_score=round(0.95 - 0.03 * index, 2))
        for index, poi_id in enumerate(pois)
    ]


@pytest.fixture
def provider() -> FakeProvider:
    return FakeProvider()


# ---------- 완료 기준 1·2 — 시각이 붙은 일정 + 실제 라우팅 결과 ----------


def test_builds_timed_schedule_for_three_days(provider):
    """후보 20개 + 2박 3일 입력 시 시각이 붙은 일정이 나온다."""
    pois = make_pois(20)
    result = build_schedule(
        make_candidates(pois),
        pois,
        provider,
        days=3,
        constraints=ScheduleConstraints(start_at=PARIS_START),
    )

    assert result.succeeded
    assert result.failure_reason is None
    assert {stop.day for stop in result.stops} == {1, 2, 3}
    for stop in result.stops:
        # "HH:MM" 형식이어야 한다 — 파싱이 되면 형식이 맞는 것이다.
        datetime.strptime(stop.arrive_at, "%H:%M")
        datetime.strptime(stop.depart_at, "%H:%M")


def test_stops_are_chronological_within_a_day(provider):
    """하루 안에서 도착 시각이 순서대로 증가한다."""
    pois = make_pois(20)
    result = build_schedule(
        make_candidates(pois),
        pois,
        provider,
        days=2,
        constraints=ScheduleConstraints(start_at=PARIS_START),
    )

    for day in (1, 2):
        times = [stop.arrive_at for stop in result.stops if stop.day == day]
        assert times == sorted(times)


def test_segments_come_from_the_router_not_hardcoded(provider):
    """스톱 사이 이동이 실제 라우팅 결과(목 프로바이더 응답)로 채워진다."""
    pois = make_pois(12)
    result = build_schedule(
        make_candidates(pois),
        pois,
        provider,
        days=2,
        constraints=ScheduleConstraints(start_at=PARIS_START),
    )

    # 그날 첫 스톱을 뺀 나머지 수 = 이동 구간 수
    moves = sum(1 for stop in result.stops if stop.order > 1)
    assert len(result.segments) == moves
    assert moves > 0
    moved = [s for s in result.stops if s.order > 1]
    for segment, stop in zip(result.segments, moved, strict=True):
        assert segment.primary.total_duration_min == stop.travel_min_from_prev
        assert segment.primary.legs  # 하드코딩이 아니라 프로바이더가 만든 leg


def test_depart_at_is_passed_to_provider(provider):
    """출발 시각이 프로바이더까지 전달된다 — 시간표 기반 경로의 전제다."""
    pois = make_pois(6)
    build_schedule(
        make_candidates(pois),
        pois,
        provider,
        days=1,
        constraints=ScheduleConstraints(start_at=PARIS_START),
    )
    assert provider.calls > 0


# ---------- 완료 기준 3 — 실패 시 dropped 와 사유 ----------


def test_returns_reason_when_nothing_can_be_placed(provider):
    """전부 영업시간 밖이면 빈 일정이 아니라 사유를 돌려준다."""
    pois = make_pois(8, opening=OpeningHours(open_at="22:00", close_at="23:30"))
    candidates = make_candidates(pois)
    result = build_schedule(
        candidates,
        pois,
        provider,
        days=2,
        constraints=ScheduleConstraints(start_at=PARIS_START),
    )

    assert result.succeeded is False
    assert result.stops == []
    assert result.dropped == [match.poi_id for match in candidates]
    assert "일정을 만들지 못했습니다" in result.failure_reason
    assert "제약을 완화하거나" in result.failure_reason


def test_dropped_lists_unplaced_candidates(provider):
    """배치되지 못한 후보는 dropped 에 남는다."""
    pois = make_pois(20)
    result = build_schedule(
        make_candidates(pois),
        pois,
        provider,
        days=1,
        constraints=ScheduleConstraints(start_at=PARIS_START, max_stops_per_day=3),
    )

    assert len(result.stops) == 3
    assert len(result.dropped) == 17
    assert set(result.dropped).isdisjoint({stop.poi_id for stop in result.stops})


def test_no_route_anywhere_still_returns_a_result(provider):
    """모든 구간에 경로가 없어도 예외 없이 결과가 나온다(첫 스톱만 배치)."""
    pois = make_pois(6)
    result = build_schedule(
        make_candidates(pois),
        pois,
        NoRouteProvider(),
        days=1,
        constraints=ScheduleConstraints(start_at=PARIS_START),
    )

    assert len(result.stops) == 1
    assert result.warnings  # 왜 1곳뿐인지 설명이 붙는다


# ---------- 완료 기준 4 — 후보를 극단적으로 줄여도 예외 없음 ----------


@pytest.mark.parametrize("count", [1, 2, 5])
def test_survives_tiny_candidate_lists(provider, count):
    """후보가 1·2·5개여도 결과 또는 실패 사유를 반환한다."""
    pois = make_pois(count)
    result = build_schedule(
        make_candidates(pois),
        pois,
        provider,
        days=2,
        constraints=ScheduleConstraints(start_at=PARIS_START),
    )

    assert result.succeeded or result.failure_reason
    assert len(result.stops) <= count


def test_empty_candidates_returns_failure(provider):
    """후보가 아예 없으면 실패 사유를 돌려준다."""
    result = build_schedule([], {}, provider, days=1)

    assert result.succeeded is False
    assert "0개입니다" in result.failure_reason


# ---------- 완료 기준 5 — 호출 횟수 ----------


def test_counts_routing_calls(provider):
    """라우팅 호출 횟수가 결과에 기록된다."""
    pois = make_pois(20)
    result = build_schedule(
        make_candidates(pois),
        pois,
        provider,
        days=3,
        constraints=ScheduleConstraints(start_at=PARIS_START),
    )

    assert result.routing_calls > 0
    assert result.provider_calls <= result.routing_calls
    # 목 프로바이더가 실제로 받은 호출 수와 일치해야 한다(사전 필터 집계 검증).
    assert provider.calls == result.provider_calls


def test_haversine_prefilter_skips_far_candidates(provider):
    """max_leg_km 밖의 후보에는 라우팅을 부르지 않는다."""
    pois = make_pois(20)
    result = build_schedule(
        make_candidates(pois),
        pois,
        provider,
        days=1,
        constraints=ScheduleConstraints(start_at=PARIS_START, max_leg_km=1.5),
    )

    assert result.routing_calls <= 3 * ScheduleConstraints().max_stops_per_day


# ---------- 완료 기준 6 — 디스크에 응답을 쓰지 않는다 ----------


def test_writes_nothing_to_disk(provider, tmp_path, monkeypatch):
    """일정 생성이 파일을 만들지 않는다(Google 약관: 응답 저장 금지)."""
    monkeypatch.chdir(tmp_path)
    pois = make_pois(12)
    build_schedule(
        make_candidates(pois),
        pois,
        provider,
        days=2,
        constraints=ScheduleConstraints(start_at=PARIS_START),
    )

    assert list(tmp_path.iterdir()) == []


# ---------- 점수·추정 헬퍼 ----------


def test_pick_score_prefers_near_over_slightly_higher_score():
    """점수 0.9 · 60분보다 점수 0.75 · 10분이 낫다."""
    far = pick_score(MatchResult(poi_id="a", group_score=0.90), 60, 0.25)
    near = pick_score(MatchResult(poi_id="b", group_score=0.75), 10, 0.25)
    assert near > far


def test_estimate_travel_min_grows_with_distance():
    """추정 이동시간은 거리에 따라 증가한다."""
    assert estimate_travel_min(1.0) < estimate_travel_min(10.0)


# ---------- 제약 훅(9/18 홍성민 작업의 진입점) ----------


def test_travel_cap_limits_the_day(provider):
    """하루 이동시간 상한을 걸면 스톱 수가 줄어든다."""
    pois = make_pois(20)
    capped = build_schedule(
        make_candidates(pois),
        pois,
        provider,
        days=1,
        constraints=ScheduleConstraints(
            start_at=PARIS_START, max_travel_min_per_day=1, min_stops_per_day=1
        ),
    )

    assert len(capped.stops) == 1  # 이동이 필요한 두 번째 스톱부터 막힌다


def test_meal_window_pulls_a_meal_poi_forward(provider):
    """식사 시간대에는 식사 가능한 POI 가 먼저 뽑힌다."""
    pois = make_pois(8)
    pois["p7"] = pois["p7"].model_copy(update={"is_meal": True, "category": "restaurant"})
    candidates = make_candidates(pois)  # p7 은 최하위 점수

    result = build_schedule(
        candidates,
        pois,
        provider,
        days=1,
        constraints=ScheduleConstraints(
            start_at=PARIS_START,
            meal_windows=[
                {
                    "label": "점심",
                    "start_at": "10:00",
                    "end_at": "14:00",
                    "categories": ["restaurant"],
                }
            ],
        ),
    )

    assert "p7" in {stop.poi_id for stop in result.stops}


def test_routing_calls_include_retries(provider):
    """재시도하면 그만큼 호출이 더 나간다 — 합산값이 기록돼야 한다."""
    pois = make_pois(5)
    result = build_schedule(
        make_candidates(pois),
        pois,
        provider,
        days=2,
        constraints=ScheduleConstraints(start_at=PARIS_START, min_stops_per_day=3),
    )

    assert result.attempts > 1
    assert result.routing_calls == provider.calls
