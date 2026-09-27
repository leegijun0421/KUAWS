"""W3 성향별 경로 추천 — '최단' 옆에 '경치' 대안을 병기하고, 그룹 성향으로 하나를 권한다.

    대안 경로 2~3개 → 경로별 주변 POI(300m) 성향 벡터 평균 → 그룹 선호와 코사인 − 시간 페널티

외부 호출을 늘리지 않는다. Google 은 `computeAlternativeRoutes` 로 같은 요청에서 대안을
함께 주므로(`google_provider.py`), 여기서는 이미 받은 경로를 **이미 가진 POI 데이터로만**
평가한다. Places 를 새로 부르지 않는다.

규칙(Notion W3 "성향별 경로 추천")
- 최단 경로가 `MIN_SEGMENT_MIN`(15분) 미만인 구간은 평가하지 않는다(대안을 따질 의미가 없다).
- 주변 POI 가 `MIN_NEARBY`(3곳) 미만인 경로는 평가하지 않는다(벡터 신뢰도 부족).
- 경로 벡터 = 주변 POI 5축의 **평균**. 여기서는 '경로의 성격 요약'이라 평균이 맞다
  (그룹 점수의 maximin 과 다르다).
- '경치' 후보 = 최단보다 자연 쪽(nature_vs_urban 이 낮음)이고 추가 소요 20분 이내인
  대안 중 가장 자연적인 것.
- 추천 = 그룹 선호와의 코사인 − `TIME_PENALTY` × 추가 시간(h) 이 더 큰 쪽.
  추천에는 이유 문장이 붙는다.
"""

from __future__ import annotations

from math import sqrt

from pydantic import BaseModel

from backend.routing.planner import SegmentRoute, count_transfers, haversine_km
from backend.routing.provider import PathPoint
from shared.types.models import RouteSegment, ScenicOption

NEAR_M = 300
MIN_NEARBY = 3
MIN_SEGMENT_MIN = 15
MAX_EXTRA_MIN = 20
#: 경치 후보가 되려면 최단보다 이만큼 이상 자연 쪽이어야 한다(nature_vs_urban 평균 차이).
MIN_NATURE_GAIN = 0.1
#: 추가 1시간당 깎는 점수. 너무 낮으면 늘 느린 길, 너무 높으면 늘 최단 — W3 사용자 테스트로 조정.
TIME_PENALTY = 0.8
_NATURE = 2  # PreferenceAxis 순서상 nature_vs_urban 위치


class ScenicPoi(BaseModel):
    """경로 평가용 POI 요약(이미 수집·태깅된 데이터)."""

    name: str
    lat: float
    lng: float
    category: str
    features: list[float]


class _Evaluated(BaseModel):
    """평가된 경로 1개."""

    segment: RouteSegment
    vector: list[float]
    nearby: list[str]
    extra_min: int


def recommend_route(
    segment: SegmentRoute, pois: list[ScenicPoi], group_pref: list[float]
) -> tuple[ScenicOption | None, str]:
    """(경치 대안 또는 None, 추천 유형 "fastest"|"scenic") 을 돌려준다."""
    base_min = segment.primary.total_duration_min
    if base_min < MIN_SEGMENT_MIN or not segment.transit_alternatives:
        return None, "fastest"
    primary = _evaluate(segment.primary, segment.path, pois, 0)
    if primary is None:
        return None, "fastest"
    alternatives = [
        evaluated
        for alt in segment.transit_alternatives
        if (evaluated := _evaluate(alt.segment, alt.path, pois,
                                   alt.segment.total_duration_min - base_min)) is not None
        and 0 <= evaluated.extra_min <= MAX_EXTRA_MIN
        and evaluated.vector[_NATURE] <= primary.vector[_NATURE] - MIN_NATURE_GAIN
    ]
    if not alternatives:
        return None, "fastest"
    scenic = min(alternatives, key=lambda item: item.vector[_NATURE])
    prefers_scenic = _score(scenic, group_pref) > _score(primary, group_pref)
    option = ScenicOption(
        segment=scenic.segment.model_copy(
            update={"preference": "scenic",
                    "transfer_count": count_transfers(scenic.segment.legs)}
        ),
        extra_min=scenic.extra_min,
        scenic_score=round(1 - scenic.vector[_NATURE], 2),
        highlights=scenic.nearby[:3],
        reason=_reason(scenic, prefers_scenic),
    )
    return option, "scenic" if prefers_scenic else "fastest"


def group_preference(member_vectors: list[list[float]]) -> list[float]:
    """그룹 선호 벡터 = 멤버 5축 평균(경로 성격 비교용)."""
    if not member_vectors:
        return [0.5] * 5
    return [sum(values[i] for values in member_vectors) / len(member_vectors) for i in range(5)]


def _evaluate(
    segment: RouteSegment, path: list[PathPoint], pois: list[ScenicPoi], extra_min: int
) -> _Evaluated | None:
    """경로 주변 POI 로 성향 벡터를 만든다. 주변 POI 가 부족하면 None."""
    nearby = [
        poi
        for poi in pois
        if any(haversine_km(lat, lng, poi.lat, poi.lng) * 1000 <= NEAR_M for lat, lng in path)
    ]
    if len(nearby) < MIN_NEARBY:
        return None
    vector = [sum(poi.features[i] for poi in nearby) / len(nearby) for i in range(5)]
    scenic_first = sorted(nearby, key=lambda poi: poi.features[_NATURE])
    names = [poi.name for poi in scenic_first if poi.category in ("nature", "attraction")]
    return _Evaluated(segment=segment, vector=vector, nearby=names, extra_min=extra_min)


def _score(route: _Evaluated, group_pref: list[float]) -> float:
    """그룹 선호와의 (0.5 중심) 코사인 − 시간 페널티."""
    a = [value - 0.5 for value in group_pref]
    b = [value - 0.5 for value in route.vector]
    norm = sqrt(sum(x * x for x in a)) * sqrt(sum(y * y for y in b))
    cosine = sum(x * y for x, y in zip(a, b, strict=True)) / norm if norm > 1e-9 else 0.0
    return cosine - TIME_PENALTY * route.extra_min / 60


def _reason(route: _Evaluated, recommended: bool) -> str:
    """이유 없는 추천은 랜덤으로 보인다 — 무엇을 지나는지와 왜 권하는지를 문장으로."""
    passing = "녹지가 많은 길입니다"
    if route.nearby:
        passing = f"{', '.join(route.nearby[:2])} 근처를 지납니다"
    extra = f"{route.extra_min}분 더 걸리지만 " if route.extra_min else ""
    tail = " (자연을 좋아하는 그룹이라 추천)" if recommended else ""
    return f"{extra}{passing}{tail}"
