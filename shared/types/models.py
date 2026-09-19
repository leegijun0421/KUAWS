"""백엔드·프론트엔드 공통 API 계약 (Python 측).

shared/types/api.ts 와 항상 동일한 구조를 유지한다. 수정은 PM만 한다.
백엔드 각 모듈은 자체 스키마를 새로 정의하지 말고 이 모델을 import 한다.
"""

from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field

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

class AxisValue(BaseModel):
    axis: PreferenceAxis
    value: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0, description="임계값 미만이면 후속 질문 대상")


class PreferenceProfile(BaseModel):
    member_id: str
    member_name: str  # 익명 기능 없음 — 이름은 항상 존재한다
    axes: list[AxisValue]
    raw_text: str
    updated_at: str


class FollowUpQuestion(BaseModel):
    """신뢰도가 낮은 축을 보강하기 위한 정량 질문."""

    question_id: str
    axis: PreferenceAxis
    prompt: str
    kind: Literal["slider", "choice"]
    choices: list[dict] | None = None


class IntakeMessageResponse(BaseModel):
    profile: PreferenceProfile
    follow_ups: list[FollowUpQuestion]
    assistant_message: str


# ---------- 장소 ----------

class Poi(BaseModel):
    poi_id: str
    name: str
    category: str
    lat: float
    lng: float
    address: str


class MemberFit(BaseModel):
    member_id: str
    fit: float = Field(ge=0.0, le=1.0)


class PoiScore(BaseModel):
    """실패 확률은 객관 지표만으로 산정한다. 인기도를 페널티로 쓰지 않는다."""

    poi_id: str
    fit_score: float = Field(ge=0.0, le=1.0)
    failure_probability: float = Field(ge=0.0, le=1.0)
    reasons: list[str]
    per_member_fit: list[MemberFit]


# ---------- 일정 ----------

class RouteLeg(BaseModel):
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


class RouteSegment(BaseModel):
    from_poi_id: str
    to_poi_id: str
    preference: RoutePreference
    total_duration_min: int
    #: 요금은 주 단위(엔·유로 등) 실수다. 유로처럼 소수점이 있는 통화가 있으므로
    #: int 로 두면 2.55 EUR 이 2 로 깎인다. 통화는 fare_currency 에 따로 담는다.
    total_fare: float
    fare_currency: str | None = None
    legs: list[RouteLeg]


class ItineraryStop(BaseModel):
    order: int
    poi: Poi
    score: PoiScore
    arrive_at: str  # "HH:MM"
    stay_min: int


class ItineraryDay(BaseModel):
    day_number: int
    stops: list[ItineraryStop]
    segments: list[RouteSegment]


class Member(BaseModel):
    member_id: str
    member_name: str


class Itinerary(BaseModel):
    plan_id: str
    city: str
    days: list[ItineraryDay]
    members: list[Member]
    min_member_satisfaction: float = Field(
        ge=0.0, le=1.0, description="그룹 최저 만족도 — 아무도 소외되지 않았는지 보여주는 지표"
    )
    briefing: str


# ---------- 공유 ----------

class ShareLinkResponse(BaseModel):
    plan_id: str
    url: str
    expires_at: str | None = None


# ---------- 오류 ----------

class ApiError(BaseModel):
    code: str
    message: str
    retryable: bool


# ======================================================================
# 확장: 특성 벡터 + Provider 프로토콜 (홍성민, 문서화 보조 허용준)
# api.ts 와 동일 구조를 유지한다. 구현 없이 타입/인터페이스만 정의한다.
# ======================================================================

# ---------- 스코어링 입력 벡터 ----------

class PoiVector(BaseModel):
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

class LLMCompletion(BaseModel):
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
