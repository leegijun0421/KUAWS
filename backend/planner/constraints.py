"""배치 제약 훅 — 영업시간·식사 배치·하루 이동시간 상한·막차 경고.

배치 루프(`placement.py`)와 재시도(`scheduler.py`)는 아래 네 함수만 호출한다.
제약을 바꿀 때 이 파일 밖을 고칠 일이 없게 하는 것이 목적이다.

* `veto_stop()`    — 이 POI 를 이 시각에 넣어도 되는가. 안 되면 사유를 돌려준다.
* `score_bonus()`  — 후보 선택 점수에 더할 가산점. 식사 시간대의 식사 장소를 끌어올린다.
* `record_stop()`  — 확정된 스톱을 하루 상태에 기록한다(식사 충족 여부 등).
* `day_warnings()` — 하루 배치가 끝난 뒤 붙일 경고 문구.

모든 훅은 **제약 값이 비어 있으면 아무 일도 하지 않는다.** 기본 설정만으로도 일정이
나와야 한다는 원칙(`schemas.ScheduleConstraints`)을 여기서 지킨다.

식사 배치 방식(12시·18시 음식 POI 강제)
    식사 시간대 안에 도착하는 식사 장소에 가산점 +1.0 을 준다. 그룹 점수가 0~1 이므로
    사실상 '식사 장소가 있으면 무조건 먼저'가 된다. 반대로 식사 장소는 식사 시간대 밖에는
    넣지 않는다(오전 10시 레스토랑 방지). 비식사 장소를 거부(veto)하는 방식은 쓰지 않는다 —
    근처에 식사 후보가 없는 날 일정이 통째로 비기 때문이다. 대신 못 채운 끼니는 경고로 알린다.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone, tzinfo

from pydantic import BaseModel

from backend.planner.schemas import MealWindow, POIVector, ScheduleConstraints, ScheduledStop
from backend.routing.planner import SegmentRoute

#: 도착 후 최소 이만큼은 머물 수 있어야 '열려 있다'고 본다(분).
MIN_VISIT_MIN = 30
#: 식사 시간대의 식사 장소 가산점. 그룹 점수(0~1)보다 커서 사실상 우선 배치된다.
MEAL_BONUS = 1.0
#: 식사 시간대 시작 전 이 시간(분) 안에 도착하면 시작까지 기다렸다가 식사한다.
MAX_MEAL_WAIT_MIN = 45
#: 관광 스톱이 이미 가득 찬 날에는 저녁까지 이만큼(분) 자유 시간을 두고 기다린다.
MAX_FREE_TIME_MIN = 180
#: 이동 상한을 다 쓴 뒤에도 식사 장소만은 이만큼(분) 더 가서 넣는다. 끼니를 거르는 것보다
#: 조금 더 걷는 편이 낫다 — 9/27 실측에서 상한 도달 후 저녁이 통째로 빠지는 일이 있었다.
MEAL_TRAVEL_GRACE_MIN = 20
#: 아직 남은 끼니가 있으면 관광·카페 이동은 상한에서 이만큼 남겨 두고 멈춘다(식사용 예약).
#: 9/27 2차 실측: 유예만으로는 부족 — 관광이 상한을 117~119분까지 다 써서 저녁이 또 빠졌다.
MEAL_TRAVEL_RESERVE_MIN = 20
#: 하루 카페 상한. 실데이터에서 카페 4곳이 연달아 배치되는 문제가 있었다(9/27).
MAX_CAFES_PER_DAY = 2


class DayState(BaseModel):
    """하루치 배치 진행 상황. 훅이 판단에 쓰는 유일한 문맥이다."""

    day: int
    stops: list[ScheduledStop] = []
    #: 그날 누적 이동시간(분).
    travel_min: int = 0
    #: 그날 이동 구간(막차 경고가 편성 시각을 본다).
    segments: list[SegmentRoute] = []
    #: 이미 채운 식사 시간대 라벨.
    meals_done: list[str] = []
    #: 그날 넣은 카페 수와 직전 스톱 유형(카페 연속 방지).
    cafes: int = 0
    last_category: str | None = None
    #: 가장 최근 배치 거부 사유(그날 배치가 일찍 끝났을 때 설명용).
    last_veto: str | None = None


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
    is_sight = not poi.is_meal and poi.category != "cafe"
    if is_sight and sight_count(state) >= constraints.max_stops_per_day:
        return StopVeto(code="day_full", message=f"{state.day}일차 관광 스톱이 가득 찼습니다")
    if poi.category == "cafe" and not _cafe_allowed(state):
        return StopVeto(code="cafe_limit", message="카페는 하루 2곳, 연달아 넣지 않습니다")
    if not is_open(poi, arrive_at, min(MIN_VISIT_MIN, poi.avg_duration_min)):
        message = f"{poi.name}: {arrive_at:%a %H:%M} 도착이면 영업시간 밖입니다"
        return StopVeto(code="closed", message=message)

    cap = constraints.max_travel_min_per_day
    if cap is not None and poi.is_meal:
        cap += MEAL_TRAVEL_GRACE_MIN
    elif cap is not None and _meal_still_ahead(arrive_at, state, constraints):
        cap -= MEAL_TRAVEL_RESERVE_MIN
    if cap is not None and state.travel_min + travel_min > cap:
        message = f"{state.day}일차 이동시간이 상한({cap}분)을 넘습니다"
        return StopVeto(code="travel_cap", message=message)

    if poi.is_meal and constraints.meal_windows:
        window = _window_at(arrive_at, constraints.meal_windows)
        if window is None:
            message = f"{poi.name}: 식사 시간대가 아닙니다"
            return StopVeto(code="meal_outside_window", message=message)
        if window.label in state.meals_done:
            return StopVeto(code="meal_duplicate", message=f"{window.label}은 이미 배치했습니다")
    return None


def score_bonus(
    poi: POIVector,
    arrive_at: datetime,
    constraints: ScheduleConstraints,
    state: DayState | None = None,
) -> float:
    """후보 선택 점수에 더할 가산점. 제약이 꺼져 있거나 이미 채운 끼니면 0.0."""
    if not constraints.meal_windows or not poi.is_meal:
        return 0.0
    window = _window_at(arrive_at, constraints.meal_windows)
    if window is None or (window.categories and poi.category not in window.categories):
        return 0.0
    if state is not None and window.label in state.meals_done:
        return 0.0
    return MEAL_BONUS


def adjust_arrival(
    poi: POIVector, arrive_at: datetime, state: DayState, constraints: ScheduleConstraints
) -> datetime:
    """식사 장소에 끼니 시작 직전 도착하면 시작 시각까지 기다린 것으로 본다.

    17:40 에 식당 앞에 도착했는데 저녁 시간대가 18:00 부터라 "식사 시간대 밖"으로 거부되면
    저녁을 통째로 놓친다. 45분 이내 대기는 자연스러우므로 도착 시각을 시작으로 민다.
    """
    if not poi.is_meal:
        return arrive_at
    minutes = arrive_at.hour * 60 + arrive_at.minute
    day_full = sight_count(state) >= constraints.max_stops_per_day
    limit = MAX_FREE_TIME_MIN if day_full else MAX_MEAL_WAIT_MIN
    for window in constraints.meal_windows:
        start = to_minutes(window.start_at)
        if window.label not in state.meals_done and 0 < start - minutes <= limit:
            return arrive_at + timedelta(minutes=start - minutes)
    return arrive_at


def record_stop(
    poi: POIVector, arrive_at: datetime, state: DayState, constraints: ScheduleConstraints
) -> None:
    """확정된 스톱이 식사 시간대를 채웠는지 기록한다."""
    if poi.is_meal and (window := _window_at(arrive_at, constraints.meal_windows)):
        state.meals_done.append(window.label)
    if poi.category == "cafe":
        state.cafes += 1
    state.last_category = poi.category


def day_warnings(state: DayState, constraints: ScheduleConstraints) -> list[str]:
    """하루 배치가 끝난 뒤 붙일 경고 문구를 만든다."""
    warnings: list[str] = []
    cap = constraints.max_travel_min_per_day
    if cap is not None and state.travel_min > cap * 0.8:
        warnings.append(f"{state.day}일차 이동시간 {state.travel_min}분 — 상한 {cap}분에 근접")
    if state.stops:
        for window in constraints.meal_windows:
            if window.label not in state.meals_done:
                warnings.append(
                    f"{state.day}일차 {window.label}({window.start_at}~{window.end_at})에 "
                    "넣을 식사 장소를 찾지 못했습니다 — 근처에서 자유롭게 드세요"
                )
    warnings.extend(_last_train_warnings(state, constraints))
    return warnings


def sight_count(state: DayState) -> int:
    """그날 배치된 관광 스톱 수. 식사·카페(쉬어 가는 곳)는 하루 상한에 세지 않는다."""
    return len(state.stops) - len(state.meals_done) - state.cafes


def _cafe_allowed(state: DayState) -> bool:
    """카페는 하루 최대 `MAX_CAFES_PER_DAY` 곳, 직전 스톱이 카페면 또 넣지 않는다."""
    return state.cafes < MAX_CAFES_PER_DAY and state.last_category != "cafe"


def is_open(poi: POIVector, moment: datetime, stay_min: int = 0) -> bool:
    """`moment` 에 도착해 `stay_min` 분 머무는 동안 영업 중인지. 요일별 영업시간을 쓴다."""
    start = moment.hour * 60 + moment.minute
    for open_at, close_at in poi.opening.ranges_for(moment.weekday()):
        if to_minutes(open_at) <= start and start + stay_min <= to_minutes(close_at):
            return True
    return False


def to_minutes(hhmm: str) -> int:
    """"HH:MM" 을 자정 기준 분으로 바꾼다("24:00" 허용). 형식이 틀리면 즉시 알려준다."""
    try:
        hour, minute = (int(part) for part in hhmm.split(":"))
    except ValueError as exc:
        raise ValueError(f"시각 형식이 'HH:MM' 이 아닙니다: {hhmm!r}") from exc
    return hour * 60 + minute


def _meal_still_ahead(
    moment: datetime, state: DayState, constraints: ScheduleConstraints
) -> bool:
    """`moment` 이후에 아직 채우지 않은 식사 시간대가 남아 있는가."""
    minutes = moment.hour * 60 + moment.minute
    return any(
        window.label not in state.meals_done and minutes < to_minutes(window.end_at)
        for window in constraints.meal_windows
    )


def _window_at(moment: datetime, windows: list[MealWindow]) -> MealWindow | None:
    """`moment` 가 속한 식사 시간대."""
    minutes = moment.hour * 60 + moment.minute
    for window in windows:
        if to_minutes(window.start_at) <= minutes <= to_minutes(window.end_at):
            return window
    return None


def _last_train_warnings(state: DayState, constraints: ScheduleConstraints) -> list[str]:
    """막차 경고. 편성 시각(Google 실제 시간표)이 있는 탑승 leg 와 그날 종료 시각을 본다.

    편성 시각이 없는 구간(도보·ODsay)은 추정으로 채우지 않고 건너뛴다.
    막차 시각이 "00:30" 처럼 자정 이후면 다음 날로 넘겨 계산한다.
    """
    margin = constraints.last_train_margin_min
    if margin is None or constraints.last_service_at is None or not state.stops:
        return []
    last_service = to_minutes(constraints.last_service_at)
    if last_service < 12 * 60:
        last_service += 24 * 60
    latest = to_minutes(state.stops[-1].depart_at)
    label = f"마지막 일정 종료 {state.stops[-1].depart_at}"
    tz = _tz(constraints.start_at)
    for segment in state.segments:
        for leg in segment.primary.legs:
            if leg.depart_at and tz is not None:
                local = datetime.fromisoformat(leg.depart_at.replace("Z", "+00:00")).astimezone(tz)
                if local.hour * 60 + local.minute >= latest:
                    latest = local.hour * 60 + local.minute
                    label = f"마지막 탑승 {leg.line_name or '대중교통'} {local:%H:%M} 출발"
    slack = last_service - latest
    if slack >= margin:
        return []
    last = constraints.last_service_at
    return [f"{state.day}일차 {label} — 도심 지하철 막차({last})까지 여유 {slack}분"]


def _tz(start_at: str | None) -> tzinfo | None:
    """출발 시각의 UTC 오프셋(편성 시각을 현지로 옮기는 데 쓴다)."""
    if not start_at:
        return None
    parsed = datetime.fromisoformat(start_at.replace("Z", "+00:00"))
    return parsed.tzinfo or timezone(timedelta(0))
