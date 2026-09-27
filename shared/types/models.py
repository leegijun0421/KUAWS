"""백엔드·프론트엔드 공통 API 계약 (Python 측).

shared/types/api.ts 와 항상 동일한 구조를 유지한다. 수정은 PM만 한다.
백엔드 각 모듈은 자체 스키마를 새로 정의하지 말고 이 모델을 import 한다.
"""

from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class ApiModel(BaseModel):
    """모든 API 계약 모델의 기반.

    Python 쪽은 snake_case, api.ts 는 camelCase 다. FastAPI 가 응답을 alias(camelCase)로
    직렬화하고, 요청은 두 형식을 모두 받는다(`populate_by_name`). 백엔드 코드는
    지금처럼 snake_case 로 생성·접근하면 된다.
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

# ---------- 공통 ----------

# 취향 축: 5개로 확정·동결 (절단 3, 2026-09-04). 이후 변경 금지.
# 스키마 변경 시 태깅 전량 재실행이 발생하므로 배치 전에 반드시 확정한다.
PreferenceAxis = Literal[
    "activity_level",   # 정적 ↔ 활동적
    "crowd_tolerance",  # 한적함 ↔ 북적임 선호
    "nature_vs_urban",  # 자연 ↔ 도심
    "food_priority",    # 식사 비중 낮음 ↔ 높음
    "pace",             # 여유 ↔ 빡빡
]

RoutePreference = Literal["fastest", "fewest_transfers", "scenic"]


# ---------- 취향 입력 ----------

class AxisValue(ApiModel):
    axis: PreferenceAxis
    value: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0, description="임계값 미만이면 후속 질문 대상")


class PreferenceProfile(ApiModel):
    member_id: str
    member_name: str  # 익명 기능 없음 — 이름은 항상 존재한다
    axes: list[AxisValue]
    raw_text: str
    updated_at: str


class FollowUpQuestion(ApiModel):
    """신뢰도가 낮은 축을 보강하기 위한 정량 질문."""

    question_id: str
    axis: PreferenceAxis
    prompt: str
    kind: Literal["slider", "choice"]
    choices: list[dict] | None = None


class HardConstraints(ApiModel):
    """대화에서 뽑은 하드 제약. 점수가 아니라 **제외** 규칙이다(알레르기·기피 장소 등)."""

    #: 제외할 내부 category 키(cafe / restaurant / culture / nature / attraction).
    exclude_categories: list[str] = []
    #: 장소 이름에 들어 있으면 제외할 키워드(예: "seafood", "海鮮"). 알레르기 대응.
    avoid_keywords: list[str] = []
    #: 사람이 읽는 원문 근거("민지: 갑각류 알레르기"). 결과 화면에 그대로 보여준다.
    notes: list[str] = []


class IntakeMessageRequest(ApiModel):
    """참가자 1명의 자유 텍스트 입력."""

    member_id: str | None = None
    member_name: str
    text: str = Field(min_length=1)


class IntakeAnswerRequest(ApiModel):
    """후속 질문(슬라이더/선택지)에 대한 정량 응답."""

    member_id: str
    axis: PreferenceAxis
    value: float = Field(ge=0.0, le=1.0)


class IntakeMessageResponse(ApiModel):
    profile: PreferenceProfile
    follow_ups: list[FollowUpQuestion]
    assistant_message: str
    #: 이 참가자의 말에서 나온 하드 제약. 없으면 빈 값.
    constraints: HardConstraints = HardConstraints()
    #: "루브르는 꼭" 처럼 확정된 방문 희망 장소(이름 그대로).
    must_visit: list[str] = []


class ChatIntakeRequest(ApiModel):
    """단톡방 대화(카카오톡 내보내기 텍스트 등) 한 덩어리."""

    chat_text: str = Field(min_length=10)


class ChatIntakeResponse(ApiModel):
    """대화 속 화자별 프로필 + 그룹 공통 제약."""

    members: list[IntakeMessageResponse]
    constraints: HardConstraints
    must_visit: list[str] = []
    assistant_message: str


# ---------- 장소 ----------

class Poi(ApiModel):
    poi_id: str
    name: str
    category: str
    lat: float
    lng: float
    address: str


class MemberFit(ApiModel):
    member_id: str
    fit: float = Field(ge=0.0, le=1.0)


class PoiScore(ApiModel):
    """실패 확률은 객관 지표만으로 산정한다. 인기도를 페널티로 쓰지 않는다."""

    poi_id: str
    fit_score: float = Field(ge=0.0, le=1.0)
    failure_probability: float = Field(ge=0.0, le=1.0)
    reasons: list[str]
    per_member_fit: list[MemberFit]


# ---------- 일정 ----------

class Operator(ApiModel):
    """대중교통 운영기관. Google Maps 약관상 경로를 보여줄 때 이름·URL 표기 의무가 있다."""

    name: str
    url: str | None = None


class RouteAdvisory(ApiModel):
    """구간 경고 배지. 이유 없는 경고는 설득력이 없어 문구를 함께 준다."""

    code: Literal["long_duration", "many_transfers"]
    message: str


class RouteLeg(ApiModel):
    mode: Literal["walk", "bus", "subway", "transfer"]
    line_name: str | None = None
    from_name: str
    to_name: str
    duration_min: int
    #: 실제 편성의 출발·도착 시각(RFC3339). 제공자가 주는 경우에만 채워진다.
    #: Google Routes v2 = 있음 / ODsay = 없음(배차간격만 제공) / 도보 구간 = 없음.
    #: C1 막차 경고와 W3 위험도가 이 값을 쓴다. None 이면 추정으로 대체할 것.
    depart_at: str | None = None
    arrive_at: str | None = None
    description: str


class RouteSegment(ApiModel):
    from_poi_id: str
    to_poi_id: str
    preference: RoutePreference
    total_duration_min: int
    #: 요금은 주 단위(엔·유로 등) 실수다. 유로처럼 소수점이 있는 통화가 있으므로
    #: int 로 두면 2.55 EUR 이 2 로 깎인다. 통화는 fare_currency 에 따로 담는다.
    total_fare: float
    fare_currency: str | None = None
    legs: list[RouteLeg]
    # --- 아래는 표시용 부가 정보(선택). 제공자·단계에 따라 비어 있을 수 있다 ---
    transfer_count: int | None = None
    #: 약관 표기용 운영기관. 응답 값을 그대로 렌더링한다(하드코딩 금지).
    operators: list[Operator] = []
    advisories: list[RouteAdvisory] = []
    #: 성향별 경로 추천(W3) — 최단 경로 대신 고를 수 있는 '경치' 대안.
    scenic: ScenicOption | None = None
    #: 그룹 성향으로 본 추천 유형. 자연 선호 그룹이면 scenic 을 권한다.
    recommended: RoutePreference | None = None


class ScenicOption(ApiModel):
    """최단 경로와 나란히 보여주는 '경치' 대안 경로."""

    segment: RouteSegment
    #: 최단 대비 추가 소요(분).
    extra_min: int
    #: 경로 주변 자연·명소 POI 특성 합산 점수(클수록 경치가 좋다).
    scenic_score: float
    #: 경로 근처를 지나는 대표 장소 이름(최대 3개).
    highlights: list[str] = []


class ItineraryStop(ApiModel):
    order: int
    poi: Poi
    score: PoiScore
    arrive_at: str  # "HH:MM"
    stay_min: int
    depart_at: str | None = None  # "HH:MM"


class ItineraryDay(ApiModel):
    day_number: int
    stops: list[ItineraryStop]
    segments: list[RouteSegment]


class Member(ApiModel):
    member_id: str
    member_name: str


class Itinerary(ApiModel):
    plan_id: str
    city: str
    days: list[ItineraryDay]
    members: list[Member]
    min_member_satisfaction: float = Field(
        ge=0.0, le=1.0, description="그룹 최저 만족도 — 아무도 소외되지 않았는지 보여주는 지표"
    )
    briefing: str
    # --- 설명 가능성을 위한 부가 정보(선택) ---
    #: 멤버별 만족도(혼자 갔을 때의 최적 일정 대비). 최저값 = min_member_satisfaction.
    member_satisfaction: list[MemberFit] = []
    #: 사용자에게 보여줄 주의 문구(막차·이동시간 상한·식사 누락 등).
    warnings: list[str] = []
    #: 하드 제약으로 제외된 장소 수와 근거.
    excluded_notes: list[str] = []
    #: POI 데이터 출처("collected" = Google Places 수집·태깅본, "seed" = 내장 예시).
    data_source: str | None = None
    start_date: str | None = None
    stats: PlanStats | None = None


class PlanStats(ApiModel):
    """생성 과정 수치. 발표·디버깅용."""

    candidate_count: int
    routing_calls: int
    provider_calls: int
    attempts: int
    elapsed_ms: int


class PlanRequest(ApiModel):
    """일정 생성 요청. 프로필은 intake 결과(슬라이더로 수정된 값)를 그대로 보낸다."""

    city: str
    days: int = Field(default=1, ge=1, le=3)
    #: 여행 시작일 "YYYY-MM-DD" (현지). 대중교통 시간표 조회 기준이 된다.
    start_date: str
    members: list[PreferenceProfile] = Field(min_length=1, max_length=8)
    constraints: HardConstraints = HardConstraints()
    must_visit: list[str] = []


class CityInfo(ApiModel):
    """지원 도시(화이트리스트) 1개."""

    key: str
    label: str
    timezone: str
    poi_count: int
    data_source: str


# ---------- 공유 ----------

class ShareLinkResponse(ApiModel):
    plan_id: str
    url: str
    expires_at: str | None = None


class ShareRequest(ApiModel):
    """공유 링크 생성 요청. 경로가 아닌 '입력 + 장소 순서'만 저장한다(Google 약관)."""

    request: PlanRequest
    #: 일차별 poi_id 순서. 열람 시 이 순서로 경로만 다시 계산한다.
    day_orders: list[list[str]]


# ---------- 오류 ----------

class ApiError(ApiModel):
    code: str
    message: str
    retryable: bool


# ======================================================================
# 확장: 특성 벡터 + Provider 프로토콜 (홍성민, 문서화 보조 허용준)
# api.ts 와 동일 구조를 유지한다. 구현 없이 타입/인터페이스만 정의한다.
# ======================================================================

# ---------- 스코어링 입력 벡터 ----------

class PoiVector(ApiModel):
    """스코어링 엔진 입력. Poi(메타)·PoiScore(결과)와 별개 계층.

    provider마다 채울 수 있는 특성이 다르므로 상세 필드는 Optional.
    없으면 스코어링이 해당 축을 건너뛴다(graceful degradation).
    """

    poi_id: str
    # 취향 축과 정렬된 특성값 0.0~1.0 (axis 순서는 PreferenceAxis 정의 순서)
    axis_features: list[float]
    # --- 아래는 provider별 편차. 없으면 None ---
    popularity: float | None = Field(default=None, ge=0.0, le=1.0)
    avg_stay_min: int | None = None
    price_level: int | None = Field(default=None, ge=0, le=4)
    embedding: list[float] | None = None  # 의미 임베딩(있는 provider만)
    source: str | None = None             # 데이터 출처 표기용


# MatchResult 는 PoiScore 와 동일 개념 — 새 타입을 만들지 않고 별칭으로 노출한다.
MatchResult = PoiScore

# ScheduledStop 은 ItineraryStop 과 동일 개념 — 별칭으로 노출한다.
ScheduledStop = ItineraryStop


# 라우팅 provider 계약은 backend/routing/provider.py 의 RouteProvider(ABC)가
# 이미 실체다. shared/types 에 별도 RoutingProvider Protocol/Route 별칭을 두지 않는다
# (중복·불일치 방지). RouteSegment/RouteLeg 는 위에 정의된 것을 그대로 쓴다.


# ---------- LLM 응답 표준형 ----------

class LLMCompletion(ApiModel):
    """LLM 응답 표준형. provider별 부가 정보는 Optional."""

    text: str
    model_id: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    finish_reason: str | None = None


# ---------- LLM Provider 프로토콜 ----------

@runtime_checkable
class LLMProvider(Protocol):
    """모델 호출을 인터페이스 뒤로 격리한다.

    Bedrock 확보 여부와 무관하게 구현체만 교체하면 되도록 한다.
    (발표에서 확장성 근거로 사용)
    """

    name: str  # "bedrock" | "anthropic" | "mock" 등

    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> LLMCompletion: ...


# 전방 참조(RouteSegment ↔ ScenicOption, Itinerary → PlanStats)를 확정한다.
RouteSegment.model_rebuild()
Itinerary.model_rebuild()
