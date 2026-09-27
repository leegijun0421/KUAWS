"""W3 성향별 경로 추천 — '최단' 옆에 '경치' 대안을 병기한다.

    대안 경로 2~3개 × 경로 주변 POI 의 성향 벡터 합산 → 경치 점수 → 최단보다 확실히 나으면 병기

외부 호출을 늘리지 않는다. Google 은 `computeAlternativeRoutes` 로 같은 요청에서 대안을
함께 주므로(`google_provider.py`), 여기서는 이미 받은 경로들을 **점수만 매긴다**.

경치 점수 = 경로가 지나는 좌표(정류장·도보 꺾임점)에서 `NEAR_M` 이내에 있는 POI 들의
"자연·명소다움" 합. 자연다움은 태깅된 5축 중 `nature_vs_urban` 을 뒤집은 값(1 − x)이고,
공원·명소 category 만 센다(음식점 옆을 지난다고 경치가 좋은 건 아니다).
"""

from __future__ import annotations

from pydantic import BaseModel

from backend.routing.planner import SegmentRoute, count_transfers, haversine_km
from backend.routing.provider import PathPoint
from shared.types.models import RouteSegment, ScenicOption

#: 경로 좌표에서 이 거리(m) 안의 POI 를 "지나간다"고 본다.
NEAR_M = 350
#: 최단 대비 이만큼(분)까지 더 걸리는 대안만 권한다. "4분 더 걸려도 바다가 보이는 길".
MAX_EXTRA_MIN = 20
#: 최단 경로보다 경치 점수가 이만큼 이상 높아야 병기한다(비슷하면 굳이 안 권함).
MIN_GAIN = 0.5
#: 경치 점수에 넣는 category.
_SCENIC_CATEGORIES = frozenset({"nature", "attraction"})
#: 그룹 자연 선호가 이 값 이하(0 = 자연 쪽)면 경치 경로를 '추천'으로 표시한다.
NATURE_LEANING = 0.4


class ScenicPoi(BaseModel):
    """경치 점수 계산용 POI 요약."""

    name: str
    lat: float
    lng: float
    category: str
    #: 태깅 5축의 nature_vs_urban 값(0 = 자연, 1 = 도심).
    nature_vs_urban: float


def pick_scenic(segment: SegmentRoute, pois: list[ScenicPoi]) -> ScenicOption | None:
    """대안 중 경치가 확실히 나은 경로 1개를 고른다. 없으면 None."""
    if not segment.transit_alternatives:
        return None
    base_score, _ = scenic_score(segment.path, pois)
    base_min = segment.primary.total_duration_min
    best: ScenicOption | None = None
    for alt in segment.transit_alternatives:
        extra = alt.segment.total_duration_min - base_min
        score, highlights = scenic_score(alt.path, pois)
        if extra > MAX_EXTRA_MIN or score < base_score + MIN_GAIN:
            continue
        if best is None or score > best.scenic_score:
            best = ScenicOption(
                segment=_as_scenic(alt.segment),
                extra_min=max(extra, 0),
                scenic_score=round(score, 2),
                highlights=highlights[:3],
            )
    return best


def scenic_score(path: list[PathPoint], pois: list[ScenicPoi]) -> tuple[float, list[str]]:
    """경로 주변 자연·명소 POI 의 자연다움 합과, 점수 높은 순 이름 목록."""
    hits: list[tuple[float, str]] = []
    for poi in pois:
        if poi.category not in _SCENIC_CATEGORIES:
            continue
        if any(haversine_km(lat, lng, poi.lat, poi.lng) * 1000 <= NEAR_M for lat, lng in path):
            hits.append((1.0 - poi.nature_vs_urban, poi.name))
    hits.sort(reverse=True)
    return sum(value for value, _ in hits), [name for _, name in hits]


def recommend(group_nature: float, has_scenic: bool) -> str:
    """그룹의 평균 자연 선호로 추천 유형을 정한다."""
    return "scenic" if has_scenic and group_nature <= NATURE_LEANING else "fastest"


def _as_scenic(segment: RouteSegment) -> RouteSegment:
    """대안 경로를 '경치' 유형으로 표시하고 환승 수를 채운다."""
    return segment.model_copy(
        update={"preference": "scenic", "transfer_count": count_transfers(segment.legs)}
    )
