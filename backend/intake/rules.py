"""키워드 규칙 기반 취향 추출기 — LLM 을 쓸 수 없을 때의 폴백.

LLM 키가 없거나(오프라인 데모·CI) 응답이 두 번 연속 깨졌을 때도 **서비스가 멈추지 않게**
하는 안전망이다. 정확도는 LLM 보다 낮으므로 신뢰도를 0.5 로 낮게 매겨 후속 질문
(슬라이더)으로 보강되게 한다. 설계 문서의 "파싱 실패 → 정량 입력 폼 폴백"을 구현한 것이다.
"""

from __future__ import annotations

import re

from shared.types.models import AxisValue, HardConstraints, PreferenceAxis

AXES: tuple[PreferenceAxis, ...] = (
    "activity_level",
    "crowd_tolerance",
    "nature_vs_urban",
    "food_priority",
    "pace",
)

#: (축, 값) ← 이 단어가 나오면. 값은 그 축에서 이 단어가 가리키는 쪽이다.
_SIGNALS: dict[PreferenceAxis, list[tuple[float, tuple[str, ...]]]] = {
    "activity_level": [
        (0.85, ("많이 걷", "등산", "활동", "하이킹", "자전거", "뛰어")),
        (0.2, ("쉬고", "쉬엄", "힐링", "누워", "체력", "다리 아", "편하게")),
    ],
    "crowd_tolerance": [
        (0.15, ("조용", "한적", "사람 많은", "붐비는 건", "북적이는 건")),
        (0.85, ("핫플", "북적", "활기", "야시장", "사람 구경")),
    ],
    "nature_vs_urban": [
        (0.15, ("자연", "공원", "산책", "바다", "숲", "정원", "강변", "야외")),
        (0.85, ("쇼핑", "미술관", "박물관", "전시", "도심", "백화점", "야경")),
    ],
    "food_priority": [
        (0.9, ("맛집", "먹방", "미식", "디저트", "카페 투어", "빵", "야시장")),
        (0.2, ("대충 먹", "밥은 아무", "식사는 간단")),
    ],
    "pace": [
        (0.85, ("최대한 많이", "빡빡", "알차게", "뽕을 뽑", "많이 보")),
        (0.15, ("여유", "느긋", "천천히", "한두 곳", "늦잠")),
    ],
}

#: 알레르기·기피 → 음식점 이름 필터 키워드(영어·프랑스어·중국어·한국어).
_ALLERGY_KEYWORDS: dict[str, list[str]] = {
    "갑각류": [
        "seafood", "fruits de mer", "crab", "shrimp", "homard", "海鮮", "蝦", "蟹", "해산물",
    ],
    "해산물": ["seafood", "fruits de mer", "poisson", "oyster", "huître", "海鮮", "魚", "해산물"],
    "견과": ["nut", "noix", "peanut", "花生", "堅果", "견과"],
    "땅콩": ["peanut", "cacahuète", "花生", "땅콩"],
    "돼지": ["pork", "porc", "豬", "돼지"],
}


def extract_by_rules(text: str) -> tuple[list[AxisValue], HardConstraints]:
    """문장에서 키워드로 5축 값과 하드 제약을 뽑는다."""
    axes = [_axis_from_keywords(axis, text) for axis in AXES]
    return axes, _constraints_from_keywords(text)


def _axis_from_keywords(axis: PreferenceAxis, text: str) -> AxisValue:
    """한 축에 대해 걸린 신호의 평균값. 신호가 없으면 중립·저신뢰."""
    hits = [value for value, words in _SIGNALS[axis] for word in words if word in text]
    if not hits:
        return AxisValue(axis=axis, value=0.5, confidence=0.2)
    return AxisValue(axis=axis, value=round(sum(hits) / len(hits), 2), confidence=0.5)


#: "박물관은 절대 안 가" 처럼 유형 자체를 거부하는 표현 → 제외 category.
_REFUSALS: dict[str, tuple[str, ...]] = {
    "culture": ("박물관", "미술관"),
    "nature": ("등산", "공원"),
}
_REFUSAL_WORDS = ("절대 안", "안 갈", "싫어", "빼자", "빼줘")


def _refusal_pattern(words: tuple[str, ...]) -> str:
    """유형어 + 같은 절 안의 거부 표현."""
    return f"({'|'.join(words)})[^.,!?\n]{{0,15}}({'|'.join(_REFUSAL_WORDS)})"


def _constraints_from_keywords(text: str) -> HardConstraints:
    """알레르기·유형 거부 표현을 하드 제약으로 바꾼다."""
    keywords: list[str] = []
    notes: list[str] = []
    categories = [
        category
        for category, words in _REFUSALS.items()
        # 유형어 뒤 같은 절(쉼표 전) 15자 안에 거부 표현이 올 때만 — "공원 좋아, …싫어" 오탐 방지
        if re.search(_refusal_pattern(words), text)
    ]
    notes.extend(f"'{category}' 유형 거부 표현(규칙 추출)" for category in categories)
    if "알레르기" in text or "못 먹" in text:
        for trigger, words in _ALLERGY_KEYWORDS.items():
            if trigger in text:
                keywords.extend(words)
                notes.append(f"{trigger} 관련 음식점 제외(규칙 추출)")
    return HardConstraints(
        exclude_categories=categories, avoid_keywords=sorted(set(keywords)), notes=notes
    )
