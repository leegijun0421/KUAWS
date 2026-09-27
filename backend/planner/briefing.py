"""코스 브리핑 — 스케줄러 결과에서 규칙 기반으로 3~4문장을 만든다(W3, 절단 1).

런타임 LLM 호출이 없다. 9/4 절단 1 로 LLM 브리핑을 정적 템플릿으로 바꿨고, 그 덕분에
데모 중 API 장애·지연 리스크가 사라졌다. 본선에서 LLM 브리핑을 되살릴 때는
`LLMProvider` 구현체를 이 함수 뒤에 붙이면 된다(입력 `BriefingFacts` 는 그대로).
"""

from __future__ import annotations

from collections import Counter

from pydantic import BaseModel

_CATEGORY_KO = {
    "culture": "미술관·전시",
    "nature": "공원·자연",
    "attraction": "명소",
    "restaurant": "맛집",
    "cafe": "카페",
}


class BriefingFacts(BaseModel):
    """브리핑에 필요한 사실만 모은 입력. 문장은 이 값에서만 만든다(지어내지 않음)."""

    city_label: str
    days: int
    member_names: list[str]
    categories: list[str]
    stop_count: int
    meal_names: list[str]
    min_satisfaction: float
    worst_member: str | None
    avg_travel_min_per_day: int
    scenic_count: int
    warning_count: int


def build_briefing(facts: BriefingFacts) -> str:
    """템플릿 문장 3~4개를 이어 붙인다."""
    sentences = [_opening(facts), _fairness(facts)]
    optional = [_focus(facts), _meals(facts), _scenic(facts), _warnings(facts)]
    sentences.extend(sentence for sentence in optional if sentence)
    return " ".join(sentences[:4])


def _opening(facts: BriefingFacts) -> str:
    """누구의 어떤 일정인지."""
    names = "·".join(facts.member_names[:4]) + (" 외" if len(facts.member_names) > 4 else "")
    return (
        f"{names} {len(facts.member_names)}명의 {facts.city_label} {facts.days}일 일정이에요. "
        f"하루 평균 이동은 {facts.avg_travel_min_per_day}분이에요."
    )


def _fairness(facts: BriefingFacts) -> str:
    """maximin 결과 — 가장 손해 보는 사람 기준으로 말한다."""
    percent = round(facts.min_satisfaction * 100)
    if facts.worst_member is None or facts.min_satisfaction >= 0.7:
        return f"모두의 만족도가 {percent}% 이상이 되도록 골랐어요."
    return f"가장 아쉬운 {facts.worst_member}님도 {percent}%는 만족하도록 맞췄어요."


def _focus(facts: BriefingFacts) -> str | None:
    """가장 많이 들어간 유형."""
    counts = Counter(c for c in facts.categories if c not in ("restaurant", "cafe"))
    if not counts:
        return None
    top, _ = counts.most_common(1)[0]
    return f"{_CATEGORY_KO.get(top, top)} 위주로 {facts.stop_count}곳을 담았어요."


def _meals(facts: BriefingFacts) -> str | None:
    """식사 장소."""
    if not facts.meal_names:
        return None
    shown = ", ".join(facts.meal_names[:2])
    return f"식사는 {shown}{' 등' if len(facts.meal_names) > 2 else ''}에서 해요."


def _scenic(facts: BriefingFacts) -> str | None:
    """경치 대안 경로."""
    if not facts.scenic_count:
        return None
    return f"{facts.scenic_count}개 구간에는 조금 돌아가도 풍경이 좋은 경로를 함께 넣었어요."


def _warnings(facts: BriefingFacts) -> str | None:
    """주의 문구 개수."""
    if not facts.warning_count:
        return None
    return f"출발 전에 주의할 점 {facts.warning_count}개를 확인해 주세요."
