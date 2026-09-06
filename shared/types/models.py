"""백엔드·프론트엔드 공통 API 계약 (Python 측).

shared/types/api.ts 와 항상 동일한 구조를 유지한다. 수정은 PM만 한다.
백엔드 각 모듈은 자체 스키마를 새로 정의하지 말고 이 모델을 import 한다.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# ---------- 공통 ----------

PreferenceAxis = Literal[
    "activity_level",
    "crowd_tolerance",
    "nature_vs_urban",
    "food_priority",
    "pace",
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
    total_fare: int
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
