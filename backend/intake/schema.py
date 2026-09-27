"""intake 내부 모델. API 로 나가는 모델은 `shared/types/models.py` 를 그대로 쓴다."""

from __future__ import annotations

from pydantic import BaseModel, Field

from shared.types.models import AxisValue, HardConstraints, TripFacts

#: 이 값 미만의 신뢰도를 가진 축은 후속 질문(슬라이더) 대상이다.
#: 0.6 = "간접 근거" 구간(0.4~0.6)까지 되묻는다. 설문이 길어지는 것보다
#: 잘못된 취향으로 일정을 짜는 비용이 크다고 봤다(PI 미결 사항 확정, 2026-09-27).
CONFIDENCE_THRESHOLD = 0.6

#: 후속 질문 최대 라운드(PI-3). 넘으면 남은 축은 중립값으로 채우고 진행한다.
MAX_FOLLOWUP_ROUNDS = 3

#: 근거가 없을 때 쓰는 중립값.
NEUTRAL_VALUE = 0.5


class ExtractedMember(BaseModel):
    """추출기 출력 1명분. 아직 member_id 가 붙기 전 단계다."""

    name: str
    axes: list[AxisValue]
    constraints: HardConstraints = HardConstraints()
    must_visit: list[str] = []
    summary: str = ""


class ExtractionResult(BaseModel):
    """추출기 출력 전체."""

    members: list[ExtractedMember]
    assistant_message: str
    #: "llm" = Claude 추출, "rules" = 키워드 규칙 폴백(키 없음·파싱 실패).
    method: str = "llm"
    #: 확정 사항(도시·일수·날짜).
    trip: TripFacts = TripFacts()
    #: 그룹 공통 시간 제약("HH:MM").
    earliest_start: str | None = None
    latest_end: str | None = None


class MemberState(BaseModel):
    """대화가 이어지는 동안 서버가 들고 있는 참가자 상태(PI-5)."""

    member_id: str
    member_name: str
    raw_text: str
    axes: list[AxisValue]
    #: 사용자가 슬라이더로 직접 고정한 축. 재추출해도 덮어쓰지 않는다.
    pinned_axes: set[str] = set()
    constraints: HardConstraints = HardConstraints()
    must_visit: list[str] = []
    rounds: int = Field(default=0, ge=0)
