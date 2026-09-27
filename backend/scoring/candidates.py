"""점수표 → 스케줄러 후보 목록.

스케줄러(C1)는 후보 순서대로 탐욕 배치하므로, 여기서 **무엇을 몇 개 넘기느냐**가 일정의
성격을 정한다. 점수만으로 자르면 음식점 40개가 명소를 밀어낼 수 있어 유형별로 몫을 나눈다.
"""

from __future__ import annotations

import unicodedata

from backend.common.opening_hours import parse_weekly_hours
from backend.common.poi_data import MEAL_CATEGORIES, TaggedPoi
from backend.planner.schemas import MatchResult, OpeningHours, POIVector
from shared.types.models import PoiScore

#: 하루당 후보 수. 하루 최대 6곳 배치 + 재시도 여유.
SIGHTS_PER_DAY = 9
MEALS_PER_DAY = 4
CAFES_PER_DAY = 2
#: must_visit 로 지정된 장소에 주는 점수 — 1일차 첫 스톱 후보로 올린다.
MUST_VISIT_SCORE = 1.0

#: 장소 이름 매칭에서 무시하는 일반 명사(이것만 겹쳐서는 같은 장소가 아니다).
_GENERIC = frozenset(
    {"musee", "museum", "national", "parc", "park", "jardin", "garden", "place", "temple",
     "cathedrale", "church", "market", "night", "street", "paris", "taipei", "tower", "tour"}
)


def build_candidates(
    scores: list[PoiScore],
    pois: dict[str, TaggedPoi],
    days: int,
    must_visit: list[str],
) -> tuple[list[MatchResult], list[str]]:
    """유형별 몫으로 후보를 고른다. (후보 목록, 매칭된 must_visit poi_id) 를 돌려준다."""
    must_ids = match_must_visit(must_visit, list(pois.values()))
    quotas = {"meal": MEALS_PER_DAY * days, "cafe": CAFES_PER_DAY * days,
              "sight": SIGHTS_PER_DAY * days}
    chosen: list[MatchResult] = []
    for score in scores:  # 이미 점수 내림차순
        poi = pois[score.poi_id]
        bucket = _bucket(poi)
        is_must = poi.poi_id in must_ids
        if quotas[bucket] <= 0 and not is_must:
            continue
        quotas[bucket] -= 1
        chosen.append(to_match(score, must=is_must))
    # 동점(1.0) 이 생겨도 must_visit 가 먼저 오도록 앞으로 옮긴다(정렬은 안정적이다).
    chosen.sort(key=lambda match: match.poi_id not in must_ids)
    return chosen, sorted(must_ids)


def to_match(score: PoiScore, must: bool = False) -> MatchResult:
    """점수 → 스케줄러 입력."""
    worst = min((item.fit for item in score.per_member_fit), default=None)
    return MatchResult(
        poi_id=score.poi_id,
        group_score=MUST_VISIT_SCORE if must else score.fit_score,
        min_member_fit=worst,
        reasons=(["꼭 가고 싶은 곳으로 지정됨"] if must else []) + score.reasons,
    )


def to_poi_vector(poi: TaggedPoi) -> POIVector:
    """태깅 POI → 스케줄러용 상세(영업시간은 요일별로 해석)."""
    return POIVector(
        poi_id=poi.poi_id,
        name=poi.name,
        lat=poi.lat,
        lng=poi.lng,
        category=poi.category,
        avg_duration_min=poi.avg_duration_min,
        opening=OpeningHours(weekly=parse_weekly_hours(poi.open_hours)),
        is_meal=poi.category in MEAL_CATEGORIES,
    )


def match_must_visit(names: list[str], pois: list[TaggedPoi]) -> set[str]:
    """'꼭 가고 싶은 곳' 이름을 POI 와 대조한다. 악센트·대소문자·일반 명사는 무시한다."""
    matched: set[str] = set()
    for wanted in names:
        target = _normalize(wanted)
        tokens = {token for token in target.split() if len(token) >= 4 and token not in _GENERIC}
        for poi in pois:
            name = _normalize(poi.name)
            if target and (target in name or name in target):
                matched.add(poi.poi_id)
            elif tokens and tokens <= set(name.split()):
                matched.add(poi.poi_id)
    return matched


def _bucket(poi: TaggedPoi) -> str:
    """후보 몫 분류."""
    if poi.category in MEAL_CATEGORIES:
        return "meal"
    return "cafe" if poi.category == "cafe" else "sight"


def _normalize(text: str) -> str:
    """악센트 제거·소문자·구두점 공백화."""
    stripped = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    cleaned = "".join(ch if ch.isalnum() else " " for ch in (stripped or text).lower())
    return " ".join(cleaned.split())
