"""intake API. 경로 접두사 `/api/intake` 는 `backend/main.py` 에서 붙인다.

| 메서드 | 경로 | 설명 |
|--------|------|------|
| POST | `/message` | 참가자 1명 자유 텍스트 → 프로필 초안 + 후속 질문 |
| POST | `/chat`    | 단톡방 대화 전체 → 화자별 프로필 + 그룹 하드 제약 |
| POST | `/answer`  | 후속 질문(슬라이더/선택지) 응답 반영 |
| GET  | `/profile/{member_id}` | 현재 프로필 조회 |
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from backend.intake import profile as store
from backend.intake.chat_parser import parse_chat
from backend.intake.extractor import extract_profiles
from shared.types.models import (
    ChatIntakeRequest,
    ChatIntakeResponse,
    IntakeAnswerRequest,
    IntakeMessageRequest,
    IntakeMessageResponse,
    PreferenceProfile,
)

router = APIRouter()

#: 도시 key → 프롬프트에 넣을 한국어 이름. 알레르기 키워드를 현지어로 만들 때 쓴다.
_CITY_LABELS = {"paris": "파리(프랑스)", "taipei": "타이베이(대만)"}


@router.post("/message", response_model=IntakeMessageResponse)
def post_message(body: IntakeMessageRequest, city: str = Query("paris")) -> IntakeMessageResponse:
    """참가자 1명의 자유 텍스트를 받아 프로필 초안과 후속 질문을 돌려준다(PI-1~3, 5)."""
    previous = _previous_text(body.member_id)
    raw_text = f"{previous}\n{body.text}".strip()
    result = extract_profiles({body.member_name: raw_text.splitlines()}, _label(city))
    state = store.upsert_member(result.members[0], raw_text, body.member_id)
    return store.to_response(state, result.assistant_message)


@router.post("/chat", response_model=ChatIntakeResponse)
def post_chat(body: ChatIntakeRequest, city: str = Query("paris")) -> ChatIntakeResponse:
    """단톡방 대화에서 화자별 프로필을 만든다. LLM 호출은 대화 전체에 1회."""
    speakers = parse_chat(body.chat_text)
    if not speakers:
        raise HTTPException(
            422, "대화에서 화자를 찾지 못했습니다. '이름: 메시지' 형식인지 확인해 주세요."
        )
    result = extract_profiles(speakers, _label(city))
    responses = []
    for member in result.members:
        state = store.upsert_member(member, "\n".join(speakers[member.name]))
        responses.append(store.to_response(state, member.summary))
    constraints = store.merge_constraints([m.constraints for m in result.members])
    constraints = constraints.model_copy(
        update={"earliest_start": result.earliest_start, "latest_end": result.latest_end}
    )
    message = result.assistant_message
    if result.trip.city and not result.trip.city_supported:
        message += (
            f" 아쉽게도 '{result.trip.city}' 은(는) 아직 지원하지 않아요"
            " — 파리·타이베이 중에서 골라 주세요."
        )
    return ChatIntakeResponse(
        members=responses,
        constraints=constraints,
        must_visit=sorted({place for m in result.members for place in m.must_visit}),
        assistant_message=message,
        trip=result.trip,
    )


@router.post("/answer", response_model=IntakeMessageResponse)
def post_answer(body: IntakeAnswerRequest) -> IntakeMessageResponse:
    """정량 응답을 즉시 프로필에 반영한다(PI-4)."""
    try:
        state = store.apply_answer(body.member_id, body.axis, body.value)
    except KeyError as exc:
        raise HTTPException(404, "참가자를 찾지 못했습니다. 처음부터 다시 입력해 주세요.") from exc
    return store.to_response(state, "반영했어요.")


@router.get("/profile/{member_id}", response_model=PreferenceProfile)
def get_profile(member_id: str) -> PreferenceProfile:
    """현재 프로필을 조회한다."""
    try:
        return store.to_profile(store.get_member(member_id))
    except KeyError as exc:
        raise HTTPException(404, "참가자를 찾지 못했습니다.") from exc


def _previous_text(member_id: str | None) -> str:
    """이어서 대화하는 경우 이전 발화를 붙여 맥락을 유지한다(PI-5)."""
    if not member_id:
        return ""
    try:
        return store.get_member(member_id).raw_text
    except KeyError:
        return ""


def _label(city: str) -> str:
    """프롬프트용 도시 이름."""
    return _CITY_LABELS.get(city, city)
