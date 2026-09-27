"""일정 생성 파이프라인 — intake 결과(프로필)에서 최종 `Itinerary` 까지.

    프로필 N개 ─▶ 하드 제약 필터 ─▶ maximin 매칭 ─▶ 후보 선별 ─▶ 제약 스케줄러(실경로)
                                                                  │
                  Itinerary ◀─ 위험도·경치 경로·브리핑 ◀───────────┘

런타임 LLM 호출이 없다. LLM 은 (1) 대화 → 선호 벡터 추출, (2) POI 사전 배치 태깅에만 쓰인다.
그래서 일정 생성 요청은 외부 API 로 Google Routes 만 부른다.
"""

from __future__ import annotations

import time
from datetime import date, datetime
from zoneinfo import ZoneInfo

from backend.common.cities import CityProfile, get_city
from backend.common.logging import get_logger
from backend.common.poi_data import load_city
from backend.planner.assemble import assemble_itinerary
from backend.planner.replay import replay_schedule
from backend.planner.scheduler import build_schedule
from backend.planner.schemas import MealWindow, ScheduleConstraints
from backend.routing.provider import RouteProvider
from backend.scoring.candidates import build_candidates, to_poi_vector
from backend.scoring.filters import apply_hard_constraints
from backend.scoring.matcher import score_pois
from shared.types.models import Itinerary, PlanRequest, PreferenceProfile

logger = get_logger(__name__)

DAY_START = "09:30"
DAY_END = "21:00"
MEAL_WINDOWS = [
    MealWindow(label="점심", start_at="11:30", end_at="13:30"),
    MealWindow(label="저녁", start_at="18:00", end_at="20:00"),
]
#: 체력 약한 멤버가 있으면(활동량 최저값 < 이 값) 하루 이동시간 상한을 낮춘다.
LOW_ACTIVITY = 0.35
LAST_TRAIN_MARGIN_MIN = 45


def create_plan(
    request: PlanRequest,
    provider: RouteProvider | None = None,
    day_orders: list[list[str]] | None = None,
) -> Itinerary:
    """일정을 만든다. `day_orders` 가 있으면 그 순서를 그대로 쓴다(공유 링크 열람)."""
    started = time.perf_counter()
    city = get_city(request.city)
    data = load_city(city.key)
    filtered = apply_hard_constraints(data.pois, request.constraints)
    scores = score_pois(filtered.kept, request.members)
    candidates, must_ids = build_candidates(
        scores, {poi.poi_id: poi for poi in filtered.kept}, request.days, request.must_visit
    )
    vectors = {poi.poi_id: to_poi_vector(poi) for poi in data.pois}
    constraints = build_constraints(request, city)

    if day_orders is not None:
        schedule = replay_schedule(day_orders, vectors, constraints, provider)
    else:
        schedule = build_schedule(candidates, vectors, provider, request.days, constraints)
    logger.info(
        "일정 생성: %s %d일 · 멤버 %d명 · 후보 %d개 · 스톱 %d개",
        city.key, request.days, len(request.members), len(candidates), len(schedule.stops),
    )
    return assemble_itinerary(
        request=request,
        city=city,
        data=data,
        scores={score.poi_id: score for score in scores},
        vectors=vectors,
        schedule=schedule,
        excluded_notes=filtered.notes(),
        must_ids=must_ids,
        candidate_count=len(candidates),
        elapsed_ms=round((time.perf_counter() - started) * 1000),
    )


def build_constraints(request: PlanRequest, city: CityProfile) -> ScheduleConstraints:
    """그룹 성향으로 배치 제약을 정한다(pace → 하루 스톱 수, 최저 활동량 → 이동 상한)."""
    pace = _mean_axis(request.members, "pace")
    weakest = _min_axis(request.members, "activity_level")
    # 대화에서 나온 시간 제약("오전 11시 이전 불가")은 하루 시작·종료 시각을 조인다.
    day_start = max(DAY_START, request.constraints.earliest_start or DAY_START)
    day_end = min(DAY_END, request.constraints.latest_end or DAY_END)
    return ScheduleConstraints(
        start_at=local_start(request.start_date, city.timezone, day_start),
        day_start=day_start,
        day_end=day_end,
        max_stops_per_day=6 if pace >= 0.6 else 5 if pace >= 0.35 else 4,
        min_stops_per_day=3,
        meal_windows=MEAL_WINDOWS,
        max_travel_min_per_day=120 if weakest < LOW_ACTIVITY else 180,
        last_train_margin_min=LAST_TRAIN_MARGIN_MIN,
        last_service_at=city.last_service_at,
    )


def local_start(start_date: str, timezone_name: str, day_start: str = DAY_START) -> str:
    """"YYYY-MM-DD" + 도시 시간대 → 첫날 시작 시각 RFC3339(현지 오프셋 포함)."""
    day = date.fromisoformat(start_date)
    hour, minute = (int(part) for part in day_start.split(":"))
    moment = datetime(day.year, day.month, day.day, hour, minute, tzinfo=ZoneInfo(timezone_name))
    return moment.isoformat(timespec="seconds")


def _mean_axis(members: list[PreferenceProfile], axis: str) -> float:
    """멤버들의 축 평균(없으면 0.5)."""
    values = [a.value for m in members for a in m.axes if a.axis == axis]
    return sum(values) / len(values) if values else 0.5


def _min_axis(members: list[PreferenceProfile], axis: str) -> float:
    """멤버들의 축 최저값(없으면 0.5)."""
    values = [a.value for m in members for a in m.axes if a.axis == axis]
    return min(values) if values else 0.5
