"""스케줄러 결과 → 공용 계약 `Itinerary` 조립.

스케줄러 출력(`ScheduleResult`)은 내부 모델이다. 여기서 프론트가 그리는 형태로 바꾸면서
설명에 필요한 값을 붙인다: 스톱별 실패 위험도(W3), 구간별 경치 대안(W3), 약관 표기용
운영기관, 그룹 최저 만족도, 코스 브리핑.
"""

from __future__ import annotations

from datetime import date, timedelta

from backend.common.cities import CityProfile
from backend.common.poi_data import MEAL_CATEGORIES, CityData
from backend.planner.briefing import BriefingFacts, build_briefing
from backend.planner.risk import stop_risk
from backend.planner.schemas import POIVector, ScheduledStop, ScheduleResult
from backend.routing.planner import SegmentRoute
from backend.routing.scenic import ScenicPoi, pick_scenic, recommend
from shared.types.models import (
    Itinerary,
    ItineraryDay,
    ItineraryStop,
    Member,
    MemberFit,
    PlanRequest,
    PlanStats,
    PoiScore,
    RouteSegment,
)

_NATURE_AXIS = 2  # PreferenceAxis 순서상 nature_vs_urban 의 위치


def assemble_itinerary(
    *,
    request: PlanRequest,
    city: CityProfile,
    data: CityData,
    scores: dict[str, PoiScore],
    vectors: dict[str, POIVector],
    schedule: ScheduleResult,
    excluded_notes: list[str],
    must_ids: list[str],
    candidate_count: int,
    elapsed_ms: int,
) -> Itinerary:
    """일정 응답을 조립한다."""
    by_id = data.by_id()
    segments = {(s.primary.from_poi_id, s.primary.to_poi_id): s for s in schedule.segments}
    scenic_pois = [
        ScenicPoi(name=p.name, lat=p.lat, lng=p.lng, category=p.category,
                  nature_vs_urban=p.axis_features[_NATURE_AXIS])
        for p in data.pois
    ]
    group_nature = _group_axis_mean(request, "nature_vs_urban")
    days: list[ItineraryDay] = []
    for day in range(1, request.days + 1):
        stops = sorted((s for s in schedule.stops if s.day == day), key=lambda s: s.order)
        weekday = (date.fromisoformat(request.start_date) + timedelta(days=day - 1)).weekday()
        items, day_segments, previous = [], [], None
        for stop in stops:
            inbound = segments.get((previous, stop.poi_id)) if previous else None
            score = _with_risk(stop, scores, vectors[stop.poi_id], weekday, inbound, request)
            items.append(ItineraryStop(order=stop.order, poi=by_id[stop.poi_id].to_poi(),
                                       score=score, arrive_at=stop.arrive_at,
                                       stay_min=stop.stay_min, depart_at=stop.depart_at))
            if inbound is not None:
                day_segments.append(_segment_view(inbound, scenic_pois, group_nature))
            previous = stop.poi_id
        days.append(ItineraryDay(day_number=day, stops=items, segments=day_segments))

    satisfaction = member_satisfaction(days, request, scores)
    worst = min(satisfaction, key=lambda item: item.fit, default=None)
    names = {m.member_id: m.member_name for m in request.members}
    worst_name = names.get(worst.member_id) if worst else None
    worst_value = worst.fit if worst else 0.0
    warnings = list(schedule.warnings)
    if not schedule.succeeded and schedule.failure_reason:
        warnings.insert(0, schedule.failure_reason)
    placed = [stop for day in days for stop in day.stops]
    facts = BriefingFacts(
        city_label=city.label, days=request.days,
        member_names=[m.member_name for m in request.members],
        categories=[s.poi.category for s in placed], stop_count=len(placed),
        meal_names=[s.poi.name for s in placed if s.poi.category in MEAL_CATEGORIES],
        min_satisfaction=worst_value, worst_member=worst_name,
        avg_travel_min_per_day=round(sum(seg.total_duration_min for d in days for seg in d.segments)
                                     / max(request.days, 1)),
        scenic_count=sum(1 for d in days for seg in d.segments if seg.scenic),
        warning_count=len(warnings),
    )
    return Itinerary(
        plan_id=f"{city.key}-{request.start_date}",
        city=city.key,
        days=days,
        members=[Member(member_id=m.member_id, member_name=m.member_name) for m in request.members],
        min_member_satisfaction=worst_value,
        member_satisfaction=satisfaction,
        briefing=build_briefing(facts) if placed else "조건에 맞는 일정을 만들지 못했어요.",
        warnings=warnings,
        excluded_notes=excluded_notes + _must_visit_notes(request, must_ids),
        data_source=data.source,
        start_date=request.start_date,
        stats=PlanStats(candidate_count=candidate_count, routing_calls=schedule.routing_calls,
                        provider_calls=schedule.provider_calls, attempts=schedule.attempts,
                        elapsed_ms=elapsed_ms),
    )


def _with_risk(
    stop: ScheduledStop,
    scores: dict[str, PoiScore],
    poi: POIVector,
    weekday: int,
    inbound: SegmentRoute | None,
    request: PlanRequest,
) -> PoiScore:
    """매칭 점수에 실패 위험도를 채운다. 점수가 없는 장소(공유 재현 시 제외된 곳)는 중립."""
    score = scores.get(stop.poi_id) or PoiScore(
        poi_id=stop.poi_id, fit_score=0.5, failure_probability=0.0, reasons=[], per_member_fit=[]
    )
    worst = min((item.fit for item in score.per_member_fit), default=None)
    probability, reasons = stop_risk(poi, stop.arrive_at, stop.depart_at, weekday, inbound, worst)
    return score.model_copy(
        update={
            "failure_probability": probability,
            "reasons": score.reasons + [f"위험 요인: {reason}" for reason in reasons],
        }
    )


def _segment_view(
    segment: SegmentRoute, pois: list[ScenicPoi], group_nature: float
) -> RouteSegment:
    """구간 → 화면용 RouteSegment(운영기관·경고·경치 대안 포함)."""
    scenic = pick_scenic(segment, pois)
    return segment.primary.model_copy(
        update={
            "transfer_count": segment.transfer_count,
            "operators": segment.operators,
            "advisories": segment.advisories,
            "scenic": scenic,
            "recommended": recommend(group_nature, scenic is not None),
        }
    )


def member_satisfaction(
    days: list[ItineraryDay], request: PlanRequest, scores: dict[str, PoiScore]
) -> list[MemberFit]:
    """멤버별 만족도. 최저값이 그룹 최저 만족도(maximin 지표)다.

    멤버 만족도 = 이 일정에서 그 사람의 평균 적합도 ÷ **그 사람만을 위해 같은 개수를 골랐을 때**
    의 평균 적합도. 즉 "혼자 여행했다면 받았을 일정 대비 몇 %"다. 그룹 여행에서 100% 는
    불가능하므로, 이 값의 최저치를 끌어올리는 것이 maximin 의 목표다.
    """
    placed: dict[str, list[float]] = {m.member_id: [] for m in request.members}
    for day in days:
        for stop in day.stops:
            for item in stop.score.per_member_fit:
                placed.setdefault(item.member_id, []).append(item.fit)
    ratios = {}
    for member_id, fits in placed.items():
        if not fits:
            continue
        personal = sorted(
            (f.fit for s in scores.values() for f in s.per_member_fit if f.member_id == member_id),
            reverse=True,
        )[: len(fits)]
        ideal = sum(personal) / len(personal) if personal else 1.0
        ratios[member_id] = min(sum(fits) / len(fits) / ideal, 1.0) if ideal else 0.0
    return [MemberFit(member_id=mid, fit=round(value, 3)) for mid, value in ratios.items()]


def _group_axis_mean(request: PlanRequest, axis: str) -> float:
    """그룹의 축 평균."""
    values = [a.value for m in request.members for a in m.axes if a.axis == axis]
    return sum(values) / len(values) if values else 0.5


def _must_visit_notes(request: PlanRequest, must_ids: list[str]) -> list[str]:
    """꼭 가고 싶은 곳 중 데이터에서 못 찾은 이름을 알려준다."""
    if len(must_ids) >= len(request.must_visit):
        return []
    found = len(must_ids)
    return [
        f"꼭 가고 싶은 곳 {len(request.must_visit)}곳 중 {len(request.must_visit) - found}곳"
        f"({', '.join(request.must_visit)} 중)은 지원 장소 목록에서 찾지 못했어요"
    ]
