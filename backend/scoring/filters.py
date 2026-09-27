"""하드 제약 필터 — 점수가 아니라 '제외'다.

알레르기처럼 한 명이라도 절대 안 되는 조건은 점수를 깎는 게 아니라 후보에서 뺀다.
점수로 처리하면 다른 멤버의 높은 점수가 위험한 장소를 끌어올릴 수 있기 때문이다.

한계(발표·README 에 명시): 메타데이터 기반이라 **메뉴까지는 보지 않는다.** 음식점 이름에
키워드가 있는 곳만 거른다. "해산물 전문점"은 걸러지지만 일반 비스트로의 새우 요리는 못 거른다.
"""

from __future__ import annotations

from pydantic import BaseModel

from backend.common.poi_data import TaggedPoi
from shared.types.models import HardConstraints

#: 키워드 필터를 적용할 category. 명소 이름에 우연히 들어간 단어로 빼지 않기 위해 음식점만 본다.
_FOOD_CATEGORIES = frozenset({"restaurant", "cafe"})


class FilterOutcome(BaseModel):
    """필터 결과. 무엇을 왜 뺐는지 결과 화면에 보여준다."""

    kept: list[TaggedPoi]
    excluded: dict[str, str] = {}  # poi_id → 사유

    def notes(self) -> list[str]:
        """사람이 읽는 제외 요약(사유별 개수)."""
        counts: dict[str, int] = {}
        for reason in self.excluded.values():
            counts[reason] = counts.get(reason, 0) + 1
        return [f"{reason} — {count}곳 제외" for reason, count in counts.items()]


def apply_hard_constraints(pois: list[TaggedPoi], constraints: HardConstraints) -> FilterOutcome:
    """하드 제약에 걸리는 POI 를 뺀다."""
    excluded_categories = set(constraints.exclude_categories)
    keywords = [keyword.lower() for keyword in constraints.avoid_keywords if keyword.strip()]
    kept: list[TaggedPoi] = []
    excluded: dict[str, str] = {}
    for poi in pois:
        reason = _violation(poi, excluded_categories, keywords)
        if reason is None:
            kept.append(poi)
        else:
            excluded[poi.poi_id] = reason
    return FilterOutcome(kept=kept, excluded=excluded)


def _violation(poi: TaggedPoi, categories: set[str], keywords: list[str]) -> str | None:
    """위반 사유. 없으면 None."""
    if poi.category in categories:
        return f"'{poi.category}' 유형 제외 요청"
    if poi.category in _FOOD_CATEGORIES:
        name = poi.name.lower()
        for keyword in keywords:
            if keyword in name:
                return f"'{keyword}' 포함 음식점 제외(알레르기·기피)"
    return None
