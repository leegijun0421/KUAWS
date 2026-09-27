"""참가자 상태 보관·병합·후속 질문 라운드 제한·그룹 집계.

예선 범위에서는 서버 메모리에 보관한다(계정 시스템 없음 — 링크 접근만, PI 범위 밖).
서버를 재시작하면 대화 상태가 사라지지만, 프론트가 최종 프로필을 들고 있다가
일정 생성 요청에 그대로 실어 보내므로 일정 생성에는 영향이 없다.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from backend.intake.followup import build_followups
from backend.intake.schema import (
    MAX_FOLLOWUP_ROUNDS,
    NEUTRAL_VALUE,
    ExtractedMember,
    MemberState,
)
from shared.types.models import (
    AxisValue,
    HardConstraints,
    IntakeMessageResponse,
    PreferenceAxis,
    PreferenceProfile,
)

_STATES: dict[str, MemberState] = {}


def upsert_member(
    extracted: ExtractedMember, raw_text: str, member_id: str | None = None
) -> MemberState:
    """추출 결과를 상태에 반영한다. 이미 있으면 사용자가 고정한 축은 유지한다(PI-5)."""
    state = _STATES.get(member_id or "")
    if state is None:
        state = MemberState(
            member_id=member_id or f"m-{uuid4().hex[:8]}",
            member_name=extracted.name,
            raw_text=raw_text,
            axes=extracted.axes,
        )
    else:
        pinned = {axis.axis: axis for axis in state.axes if axis.axis in state.pinned_axes}
        state.axes = [pinned.get(axis.axis, axis) for axis in extracted.axes]
        state.raw_text = raw_text
    state.constraints = extracted.constraints
    state.must_visit = extracted.must_visit
    state.rounds += 1
    _STATES[state.member_id] = state
    return state


def apply_answer(member_id: str, axis: PreferenceAxis, value: float) -> MemberState:
    """후속 질문 응답을 즉시 반영한다(PI-4). 직접 답한 값은 신뢰도 1.0 으로 고정."""
    state = get_member(member_id)
    state.axes = [
        AxisValue(axis=axis, value=value, confidence=1.0) if item.axis == axis else item
        for item in state.axes
    ]
    state.pinned_axes.add(axis)
    state.rounds += 1
    return state


def get_member(member_id: str) -> MemberState:
    """상태를 찾는다. 없으면 KeyError — 라우터가 404 로 바꾼다."""
    if member_id not in _STATES:
        raise KeyError(member_id)
    return _STATES[member_id]


def to_response(state: MemberState, assistant_message: str) -> IntakeMessageResponse:
    """상태를 API 응답으로 만든다. 라운드 상한을 넘으면 남은 축을 중립값으로 확정한다."""
    axes = state.axes
    follow_ups = build_followups(state.member_id, axes)
    if state.rounds > MAX_FOLLOWUP_ROUNDS and follow_ups:
        weak = {question.axis for question in follow_ups}
        axes = [
            AxisValue(axis=a.axis, value=NEUTRAL_VALUE, confidence=0.6) if a.axis in weak else a
            for a in axes
        ]
        state.axes = axes
        follow_ups = []
        assistant_message += " 나머지 취향은 중간값으로 두고 진행할게요."
    return IntakeMessageResponse(
        profile=to_profile(state),
        follow_ups=follow_ups,
        assistant_message=assistant_message,
        constraints=state.constraints,
        must_visit=state.must_visit,
    )


def to_profile(state: MemberState) -> PreferenceProfile:
    """공용 계약의 프로필 형태로 변환한다."""
    return PreferenceProfile(
        member_id=state.member_id,
        member_name=state.member_name,
        axes=state.axes,
        raw_text=state.raw_text,
        updated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )


def merge_constraints(parts: list[HardConstraints]) -> HardConstraints:
    """참가자별 하드 제약을 그룹 제약으로 합친다(PI-6). 한 명의 알레르기도 그룹 제약이다."""
    return HardConstraints(
        exclude_categories=sorted({c for part in parts for c in part.exclude_categories}),
        avoid_keywords=sorted({k for part in parts for k in part.avoid_keywords}),
        notes=[note for part in parts for note in part.notes],
    )


def reset_states() -> None:
    """테스트용 초기화."""
    _STATES.clear()
