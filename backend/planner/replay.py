"""고정된 장소 순서로 일정을 다시 계산한다 — 공유 링크 열람용.

공유 링크에는 경로가 아니라 **장소 순서(Place ID)** 만 저장한다. Google 약관상 경로 응답은
저장할 수 없지만 Place ID 는 영구 저장이 허용되기 때문이다. 링크를 열면 이 모듈이 같은
순서로 경로만 다시 조회해 시각을 채운다(`docs/DECISIONS.md` 2026-09-27).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from backend.planner.constraints import DayState, day_warnings, record_stop
from backend.planner.placement import day_window, rfc3339_or_none
from backend.planner.schemas import POIVector, ScheduleConstraints, ScheduledStop, ScheduleResult
from backend.routing.planner import plan_segment
from backend.routing.provider import GeoPoint, RouteProvider


def replay_schedule(
    day_orders: list[list[str]],
    pois: dict[str, POIVector],
    constraints: ScheduleConstraints,
    provider: RouteProvider | None = None,
) -> ScheduleResult:
    """일차별 poi_id 순서를 그대로 따라 시각과 경로를 채운다. 사라진 장소는 건너뛴다."""
    result = ScheduleResult()
    for day, order in enumerate(day_orders, start=1):
        clock, _ = day_window(day, constraints)
        state = DayState(day=day)
        previous: POIVector | None = None
        for poi_id in order:
            poi = pois.get(poi_id)
            if poi is None:
                result.dropped.append(poi_id)
                continue
            travel = 0
            if previous is not None:
                segment = plan_segment(
                    _geo(previous), _geo(poi), depart_at=rfc3339_or_none(clock), provider=provider
                )
                result.routing_calls += 1
                if segment is not None:
                    travel = segment.primary.total_duration_min
                    result.segments.append(segment)
                    state.segments.append(segment)
            arrive = clock + timedelta(minutes=travel)
            stop = _stop(day, len(state.stops) + 1, poi, arrive, travel if previous else None)
            state.stops.append(stop)
            state.travel_min += travel
            record_stop(poi, arrive, state, constraints)
            result.stops.append(stop)
            clock, previous = arrive + timedelta(minutes=poi.avg_duration_min), poi
        result.warnings.extend(day_warnings(state, constraints))
    return result


def _stop(
    day: int, order: int, poi: POIVector, arrive: datetime, travel: int | None
) -> ScheduledStop:
    """스톱 1개."""
    return ScheduledStop(
        day=day,
        order=order,
        poi_id=poi.poi_id,
        name=poi.name,
        arrive_at=f"{arrive:%H:%M}",
        depart_at=f"{arrive + timedelta(minutes=poi.avg_duration_min):%H:%M}",
        stay_min=poi.avg_duration_min,
        group_score=0.0,
        travel_min_from_prev=travel,
    )


def _geo(poi: POIVector) -> GeoPoint:
    """라우팅 입력 좌표."""
    return GeoPoint(poi_id=poi.poi_id, name=poi.name, lat=poi.lat, lng=poi.lng)
