"""신뢰도 낮은 축 → 정량 후속 질문(슬라이더/선택지).

질문 문구는 LLM 으로 만들지 않고 고정 문구를 쓴다. 이유는 두 가지다.
1. 슬라이더 양 끝 라벨이 축 정의와 정확히 일치해야 값이 의미를 갖는다.
2. 후속 질문마다 LLM 을 부르면 응답 지연(PI 비기능: 5초)과 비용이 늘어난다.
"""

from __future__ import annotations

from backend.intake.schema import CONFIDENCE_THRESHOLD
from shared.types.models import AxisValue, FollowUpQuestion, PreferenceAxis

#: 축별 질문 문구와 슬라이더 양 끝 라벨(0.0 쪽, 1.0 쪽).
_QUESTIONS: dict[PreferenceAxis, tuple[str, str, str]] = {
    "activity_level": ("하루에 얼마나 움직이고 싶으세요?", "푹 쉬면서", "많이 걷고 활동적으로"),
    "crowd_tolerance": ("사람 많은 곳은 어떠세요?", "한적한 곳이 좋아요", "북적여도 괜찮아요"),
    "nature_vs_urban": ("어떤 풍경이 더 끌리세요?", "공원·자연", "도심·미술관·쇼핑"),
    "food_priority": ("이번 여행에서 식사는 얼마나 중요하세요?", "간단히 때워도 OK", "맛집이 핵심"),
    "pace": ("일정 속도는 어느 쪽이 좋으세요?", "한 곳에 오래 여유롭게", "많이 빠르게 둘러보기"),
}

#: 선택지 형태로 묻는 축. 3단계로 끊어 답하기 쉬운 축만 고른다.
_CHOICE_AXES: frozenset[PreferenceAxis] = frozenset({"food_priority"})


def build_followups(member_id: str, axes: list[AxisValue]) -> list[FollowUpQuestion]:
    """신뢰도가 임계값 미만인 축마다 질문 1개를 만든다. 낮은 신뢰도 순서."""
    weak = sorted(
        (axis for axis in axes if axis.confidence < CONFIDENCE_THRESHOLD),
        key=lambda axis: axis.confidence,
    )
    return [_question(member_id, axis.axis) for axis in weak]


def _question(member_id: str, axis: PreferenceAxis) -> FollowUpQuestion:
    """축 하나에 대한 질문. 선택지 축이면 3단계 선택지를 붙인다."""
    prompt, low_label, high_label = _QUESTIONS[axis]
    if axis in _CHOICE_AXES:
        return FollowUpQuestion(
            question_id=f"{member_id}:{axis}",
            axis=axis,
            prompt=prompt,
            kind="choice",
            choices=[
                {"label": low_label, "value": 0.15},
                {"label": "적당히", "value": 0.5},
                {"label": high_label, "value": 0.9},
            ],
        )
    return FollowUpQuestion(
        question_id=f"{member_id}:{axis}",
        axis=axis,
        prompt=f"{prompt} (왼쪽: {low_label} · 오른쪽: {high_label})",
        kind="slider",
    )
