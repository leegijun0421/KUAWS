"""C1 스케줄러 입출력 계약.

`shared/types/models.py` 는 PM 소유라 임의로 못 고친다(`.kiro/steering/structure.md`).
그래서 스케줄러가 쓰는 중간 모델은 여기에 둔다. 프론트로 나가는 최종 응답은
`Itinerary` 로 변환해서 내보내며, 그 변환은 W2 통합(9/20)에서 붙인다.

역할 경계 — 9/18 홍성민 작업(식사 배치·이동시간 상한·막차 경고)은
`ScheduleConstraints` 의 "제약 필드" 구역과 `backend/planner/constraints.py` 안에서만
이뤄진다. 배치 루프(`placement.py`)와 재시도(`scheduler.py`)는 건드리지 않는다.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from backend.routing.planner import SegmentRoute

# ---------- 입력 ----------


class OpeningHours(BaseModel):
    """영업시간.

    `weekly` 가 있으면 요일별 구간(0=월, "HH:MM" 쌍 목록, 빈 목록 = 휴무)을 쓰고,
    없거나 그 요일 정보가 없으면 `open_at`~`close_at` 을 매일 적용한다.
    `weekly` 는 `backend.common.opening_hours.parse_weekly_hours()` 가 만든다.
    """

    open_at: str = "09:00"
    close_at: str = "21:00"
    weekly: dict[int, list[tuple[str, str]]] | None = None

    def ranges_for(self, weekday: int) -> list[tuple[str, str]]:
        """그 요일의 영업 구간. 빈 목록이면 휴무."""
        if self.weekly is not None and weekday in self.weekly:
            return self.weekly[weekday]
        return [(self.open_at, self.close_at)]


class POIVector(BaseModel):
    """스케줄러가 배치에 필요로 하는 POI 상세.

    B1 태깅 결과 중 **배치에 쓰이는 필드만** 추린 형태다. 성향 벡터 자체는
    B2 매칭에서 이미 소비되므로 여기까지 내려오지 않는다.
    """

    poi_id: str
    name: str
    lat: float
    lng: float
    category: str = "attraction"
    #: 평균 체류 시간(분). 태깅 단계에서 채우고, 없으면 90분으로 둔다.
    avg_duration_min: int = Field(default=90, ge=15, le=480)
    opening: OpeningHours = OpeningHours()
    #: 식사로 쓸 수 있는 장소인가. 9/18 식사 배치 제약이 이 값을 본다.
    is_meal: bool = False


class MatchResult(BaseModel):
    """B2 매칭 출력 1건. 점수 내림차순 목록으로 넘어온다."""

    poi_id: str
    #: maximin 그룹 점수(0~1). 클수록 "아무도 소외되지 않는" 선택이다.
    group_score: float = Field(ge=0.0, le=1.0)
    #: 그룹 최저 만족도. 결과 화면 설명에 쓰며 배치 판단에는 쓰지 않는다.
    min_member_fit: float | None = None
    reasons: list[str] = []


class MealWindow(BaseModel):
    """식사를 넣어야 하는 시간대. 9/18 홍성민 작업에서 채운다."""

    label: str
    start_at: str  # "12:00"
    end_at: str  # "13:30"
    #: 이 시간대에 넣을 POI 의 category 화이트리스트. 비면 `is_meal` 만 본다.
    categories: list[str] = []


class ScheduleConstraints(BaseModel):
    """배치 제약. 기본값만으로도 일정이 나와야 한다 — 전부 선택 입력이다."""

    # --- 기본 골격 (이기준 / 9/17) ---
    #: 첫날 시작 시각(RFC3339, 현지 시간대). 없으면 시간표 없는 경로로 배치한다.
    start_at: str | None = None
    day_start: str = "09:00"
    day_end: str = "21:00"
    max_stops_per_day: int = Field(default=4, ge=1, le=10)
    #: 이 거리를 넘는 후보는 라우팅을 부르지 않는다(호출 절감의 핵심).
    max_leg_km: float = Field(default=15.0, gt=0)
    #: 이동 1시간당 깎는 점수. W3 사용자 테스트에서 조정한다.
    travel_penalty: float = Field(default=0.25, ge=0.0)
    #: 하루에 이 개수도 못 넣으면 실패로 보고 후보를 줄여 재시도한다.
    min_stops_per_day: int = Field(default=2, ge=1)

    # --- 제약 필드 (홍성민 / 9/18) ---
    # 아래 세 필드는 `constraints.py` 의 훅에서만 읽는다. 값이 비어 있으면
    # 해당 제약은 꺼진 것으로 간주하고 배치 결과가 달라지지 않는다.
    #: 식사 배치 — 이 시간대에는 식사 가능한 POI 를 우선한다.
    meal_windows: list[MealWindow] = []
    #: 하루 총 이동시간 상한(분). None 이면 제한 없음.
    max_travel_min_per_day: int | None = None
    #: 막차 경고 기준(분). 마지막 탑승 여유가 이보다 적으면 경고를 단다.
    last_train_margin_min: int | None = None
    #: 도시 지하철 막차 시각(현지 "HH:MM", 자정 이후면 "00:30" 처럼). `backend.common.cities`.
    last_service_at: str | None = None


# ---------- 출력 ----------


class ScheduledStop(BaseModel):
    """배치된 스톱 1개. 시각이 붙어 있다는 점이 후보 목록과의 차이다."""

    day: int = Field(ge=1)
    order: int = Field(ge=1, description="그날 안에서의 순번")
    poi_id: str
    name: str
    arrive_at: str  # "HH:MM"
    depart_at: str  # "HH:MM"
    stay_min: int
    group_score: float
    #: 직전 스톱에서 여기까지 걸린 이동시간(분). 그날 첫 스톱은 None.
    travel_min_from_prev: int | None = None


class ScheduleResult(BaseModel):
    """스케줄러 출력.

    `dropped` 와 `warnings` 는 **비어 있더라도 항상 채워 보낸다.**
    "왜 이 일정이 됐는가"를 설명하지 못하면 결과 화면도 발표도 약해진다.
    """

    stops: list[ScheduledStop] = []
    #: 스톱 사이 이동. D1 `plan_segment()` 결과를 그대로 싣는다.
    segments: list[SegmentRoute] = []
    #: 배치하지 못한 poi_id.
    dropped: list[str] = []
    #: 사용자에게 보여줄 주의 문구("3일차 막차 여유 8분" 등).
    warnings: list[str] = []
    succeeded: bool = True
    #: 완전 실패 시 사용자에게 그대로 보여줄 사유. 성공이면 None.
    failure_reason: str | None = None
    #: 이번 생성에서 `plan_segment()` 를 부른 횟수.
    routing_calls: int = 0
    #: 그중 사전 필터를 통과해 실제 외부 API 로 나간 횟수.
    provider_calls: int = 0
    #: 후보를 줄여가며 시도한 횟수(1 = 첫 시도에 성공).
    attempts: int = 1
