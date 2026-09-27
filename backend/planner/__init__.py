"""planner 모듈. 소유권은 .kiro/steering/structure.md 참조.

C1 제약 스케줄러의 공개 진입점은 `build_schedule()` 하나다. 호출부(W2 통합·API)는
내부 구조(배치 루프·재시도·제약 훅)를 몰라도 된다.

    from backend.planner import build_schedule, ScheduleConstraints

파일 경계 — 9/18 식사·이동상한·막차 작업은 `constraints.py` 안에서만 이뤄진다.
"""

from backend.planner.constraints import (
    DayState,
    StopVeto,
    adjust_arrival,
    day_warnings,
    record_stop,
    score_bonus,
    veto_stop,
)
from backend.planner.placement import PlacementOutcome, pick_score, place_days
from backend.planner.scheduler import build_schedule
from backend.planner.schemas import (
    MatchResult,
    MealWindow,
    OpeningHours,
    POIVector,
    ScheduleConstraints,
    ScheduledStop,
    ScheduleResult,
)

__all__ = [
    "adjust_arrival",
    "DayState",
    "MatchResult",
    "MealWindow",
    "OpeningHours",
    "POIVector",
    "PlacementOutcome",
    "ScheduleConstraints",
    "ScheduleResult",
    "ScheduledStop",
    "StopVeto",
    "build_schedule",
    "day_warnings",
    "pick_score",
    "place_days",
    "record_stop",
    "score_bonus",
    "veto_stop",
]
