"""자유 텍스트·단톡방 대화 → 화자별 5축 선호 벡터 + 하드 제약 + 확정 방문지.

    speakers = parse_chat(chat_text)              # 규칙으로 화자 분리
    result = extract_profiles(speakers, "파리")    # LLM 1회 호출(캐시)

LLM 은 `LLMProvider` 인터페이스에만 의존한다(현재 구현체 Anthropic, Bedrock 교체 가능).
LLM 이 없거나 응답이 두 번 연속 깨지면 `rules.extract_by_rules` 로 폴백한다 —
어느 경우든 **추출 결과는 반드시 나온다**. 대신 폴백은 신뢰도를 낮게 매겨
후속 질문(슬라이더)으로 보강되게 한다.
"""

from __future__ import annotations

import json

from backend.common.llm import (
    LLMResponseError,
    LLMUnavailableError,
    complete_json,
    get_llm_provider,
    render_prompt,
)
from backend.common.logging import get_logger
from backend.intake.rules import AXES, extract_by_rules
from backend.intake.schema import ExtractedMember, ExtractionResult
from shared.types.models import AxisValue, HardConstraints, LLMProvider

logger = get_logger(__name__)

#: 허용하는 category key. LLM 이 다른 값을 내면 버린다(검증 없이 쓰지 않는다).
VALID_CATEGORIES = frozenset({"cafe", "restaurant", "culture", "nature", "attraction"})

#: 화자당 발화 수 상한. 긴 단톡방이 토큰을 폭증시키지 않게 최근 발화만 쓴다.
MAX_MESSAGES_PER_SPEAKER = 40

_RULES_MESSAGE = "AI 분석을 쓸 수 없어 키워드로 대략 정리했어요. 슬라이더로 확인해 주세요."


def extract_profiles(
    speakers: dict[str, list[str]],
    city_label: str,
    provider: LLMProvider | None = None,
) -> ExtractionResult:
    """화자별 발화에서 취향을 추출한다. LLM 실패 시 규칙 기반으로 폴백한다."""
    if not speakers:
        raise ValueError("취향을 읽을 발화가 없습니다.")
    try:
        llm = provider or get_llm_provider()
        payload = {
            name: messages[-MAX_MESSAGES_PER_SPEAKER:] for name, messages in speakers.items()
        }
        system, prompt = render_prompt(
            "extract_profile",
            city_label=city_label,
            speakers_json=json.dumps(payload, ensure_ascii=False, indent=2),
        )
        data = complete_json(llm, prompt, system=system, max_tokens=3000)
        return _from_llm(data, speakers)
    except (LLMUnavailableError, LLMResponseError) as exc:
        logger.warning("LLM 추출 불가 — 규칙 기반으로 폴백: %s", exc)
        return _from_rules(speakers)


def _from_llm(data: dict, speakers: dict[str, list[str]]) -> ExtractionResult:
    """LLM JSON 을 검증해 내부 모델로 바꾼다. 입력에 없는 화자는 버린다."""
    by_name = {str(item.get("name", "")).strip(): item for item in data.get("members", [])}
    members = []
    for name, messages in speakers.items():
        item = by_name.get(name)
        if item is None:
            logger.warning("LLM 이 화자 %s 를 빠뜨림 — 이 사람만 규칙으로 추출", name)
            members.append(_rules_member(name, messages))
            continue
        members.append(_member_from_item(name, item))
    message = str(data.get("assistant_message") or "대화에서 취향을 정리했어요.")
    return ExtractionResult(members=members, assistant_message=message, method="llm")


def _member_from_item(name: str, item: dict) -> ExtractedMember:
    """LLM 이 준 한 사람분을 검증한다. 범위를 벗어난 값은 잘라낸다."""
    raw_axes = item.get("axes") or {}
    axes = [_axis_value(axis, raw_axes.get(axis) or {}) for axis in AXES]
    constraints = HardConstraints(
        exclude_categories=[
            str(c) for c in item.get("exclude_categories") or [] if str(c) in VALID_CATEGORIES
        ],
        avoid_keywords=[
            str(k).strip() for k in item.get("avoid_keywords") or [] if str(k).strip()
        ],
        notes=[f"{name}: {note}" for note in item.get("constraint_notes") or [] if note],
    )
    return ExtractedMember(
        name=name,
        axes=axes,
        constraints=constraints,
        must_visit=[str(place) for place in item.get("must_visit") or [] if place],
        summary=str(item.get("summary") or ""),
    )


def _axis_value(axis: str, raw: dict) -> AxisValue:
    """축 하나를 검증한다. 값이 null 이면 중립 0.5 + 원래 신뢰도(낮음)."""
    value = raw.get("value")
    confidence = _clip(raw.get("confidence", 0.0))
    if value is None:
        return AxisValue(axis=axis, value=0.5, confidence=min(confidence, 0.3))
    return AxisValue(axis=axis, value=_clip(value), confidence=confidence)


def _from_rules(speakers: dict[str, list[str]]) -> ExtractionResult:
    """전원 규칙 기반 추출."""
    members = [_rules_member(name, messages) for name, messages in speakers.items()]
    return ExtractionResult(
        members=members,
        assistant_message=_RULES_MESSAGE,
        method="rules",
    )


def _rules_member(name: str, messages: list[str]) -> ExtractedMember:
    """한 사람분 규칙 추출."""
    axes, constraints = extract_by_rules(" ".join(messages))
    notes = [f"{name}: {note}" for note in constraints.notes]
    return ExtractedMember(
        name=name, axes=axes, constraints=constraints.model_copy(update={"notes": notes})
    )


def _clip(value: object) -> float:
    """0.0~1.0 로 자른다. 숫자가 아니면 0.0."""
    try:
        return round(min(max(float(value), 0.0), 1.0), 2)
    except (TypeError, ValueError):
        return 0.0
