"""배치 제약 훅.

⚠️ **이 파일이 9/18 홍성민 작업의 소유 경로다.** 식사 배치·이동시간 상한·막차 경고는
전부 여기 세 함수 안에서 끝난다. 배치 루프(`placement.py`)와 재시도(`scheduler.py`)는
아래 함수만 호출하므로, 두 사람이 같은 파일을 동시에 고칠 일이 없다.

훅은 세 종류다.

* `veto_stop()`   — 이 POI 를 이 시각에 넣어도 되는가. 안 되면 사유를 돌려준다.
* `score_bonus()` — 후보 선택 점수에 더할 가산점. 기본 0.0.
* `day_warnings()` — 하루 배치가 끝난 뒤 붙일 경고 문구.

세 함수 모두 **제약 값이 비어 있으면 아무 일도 하지 않는다.** 기본 설정만으로도
일정이 나와야 한다는 원칙(`schemas.ScheduleConstraints`)을 여기서 지킨다.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from backend.planner.schemas import POIVector, ScheduleConstraints, ScheduledStop


class DayState(BaseModel):
    """하루치 배치 진행 상황. 훅이 판단에 쓰는 유일한 문맥이다."""

    day: int
    stops: list[ScheduledStop] = []
    #: 그날 누적 이동시간(분).
    travel_min: int = 0


class StopVeto(BaseModel):
    """배치 거부 사유. 이유 없는 거부는 설명할 수 없으므로 문구를 함께 만든다."""

    code: str
    message: str


def veto_stop(
    poi: POIVector,
    arrive_at: datetime,
    travel_min: int,
    state: DayState,
    constraints: ScheduleConstraints,
) -> StopVeto | None:
    """이 POI 를 `arrive_at` 에 넣어도 되는지 검사한다. 문제가 없으면 None."""
    if not _is_open(poi, arrive_at):
        return StopVeto(
            code="closed",
            message=f"{poi.name}: {arrive_at:%H:%M} 도착이면 영업시간({poi.opening.open_at}"
            f"~{poi.opening.close_at}) 밖입니다",
        )

    cap = constraints.max_travel_min_per_day
    if cap is not None and state.travel_min + travel_min > cap:
        return StopVeto(
            code="travel_cap",
            message=f"{state.day}일차 이동시간이 상한({cap}분)을 넘습니다",
        )

    # TODO(홍성민 · 9/18): 식사 시간대에 식사 아닌 POI 를 막을지 여부.
    #   지금은 `score_bonus()` 의 가산점으로만 유도하고 거부하지는 않는다 —
    #   거부로 만들면 식사 후보가 없는 도시에서 일정이 통째로 실패한다.
    return None


def score_bonus(
    poi: POIVector,
    arrive_at: datetime,
    constraints: ScheduleConstraints,
) -> float:
    """후보 선택 점수에 더할 가산점. 제약이 꺼져 있으면 0.0."""
    if not constraints.meal_windows or not poi.is_meal:
        return 0.0
    for window in constraints.meal_windows:
        if not _in_window(arrive_at, window.start_at, window.end_at):
            continue
        if window.categories and poi.category not in window.categories:
            continue
        # 식사 시간대에 식사 가능한 장소면 점수를 올려 사실상 먼저 뽑히게 한다.
        return 0.5
    return 0.0


def day_warnings(state: DayState, constraints: ScheduleConstraints) -> list[str]:
    """하루 배치가 끝난 뒤 붙일 경고 문구를 만든다."""
    warnings: list[str] = []
    cap = constraints.max_travel_min_per_day
    if cap is not None and state.travel_min > cap * 0.8:
        warnings.append(f"{state.day}일차 이동시간 {state.travel_min}분 — 상한 {cap}분에 근접")

    # TODO(홍성민 · 9/18): 막차 경고.
    #   `constraints.last_train_margin_min` 과 각 구간 마지막 탑승 leg 의
    #   `depart_at` 을 비교해 "N일차 막차 여유 8분" 형태의 문구를 만든다.
    #   `SegmentRoute.primary.legs[*].depart_at` 은 Google Routes 에서만 채워지고
    #   도보 구간은 항상 None 이므로, None 이면 경고를 만들지 말 것(추정 금지).
    return warnings


def _is_open(poi: POIVector, moment: datetime) -> bool:
    """도착 시각이 영업시간 안인지 본다. 자정을 넘는 영업시간은 다루지 않는다."""
    return _in_window(moment, poi.opening.open_at, poi.opening.close_at)


def _in_window(moment: datetime, start_at: str, end_at: str) -> bool:
    """`moment` 의 시:분이 "HH:MM"~"HH:MM" 구간 안에 있는지 판정한다."""
    minutes = moment.hour * 60 + moment.minute
    return to_minutes(start_at) <= minutes <= to_minutes(end_at)


def to_minutes(hhmm: str) -> int:
    """"HH:MM" 을 자정 기준 분으로 바꾼다. 형식이 틀리면 즉시 알려준다."""
    try:
        hour, minute = (int(part) for part in hhmm.split(":"))
    except ValueError as exc:
        raise ValueError(f"시각 형식이 'HH:MM' 이 아닙니다: {hhmm!r}") from exc
    return hour * 60 + minute
