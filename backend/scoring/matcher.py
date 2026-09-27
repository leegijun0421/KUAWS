"""선호 벡터 ↔ POI 매칭 — 멤버별 적합도와 maximin 그룹 점수.

왜 평균이 아니라 maximin 인가
-----------------------------
두 사람이 정반대 취향이면 평균 점수 1위는 "둘 다 그럭저럭"인 밋밋한 장소다.
그룹 점수를 **가장 손해 보는 사람의 적합도**로 두면, 누군가를 희생시키는 장소는
위로 올라오지 못한다(`mocks/chats/03_paris_conflict.txt` 가 그 사례).
최저값이 같은 장소끼리는 평균으로 순위를 가른다.

정규화 — "그 사람에게 이 도시에서 가능한 최선" 대비
-----------------------------------------------------
취향이 독특한 사람은 어느 장소와도 원시 적합도가 낮게 나온다. 원시값으로 maximin 을 하면
그 사람 한 명이 모든 순위를 좌우하고, 화면에는 "만족도 33%" 같은 숫자가 뜬다.
그래서 멤버별로 **도시 전체 POI 중 최고 적합도를 1.0 으로 나눠** 정규화한 뒤 maximin 을 한다.
표시되는 만족도는 "이 도시에서 그 사람에게 가장 잘 맞는 곳 대비 몇 %"라는 뜻이 된다.

적합도 계산
-----------
멤버 벡터 m, POI 벡터 p(5축, 0~1)를 0.5 중심으로 옮긴 뒤 **신뢰도 가중 코사인 유사도**를
구하고 0~1 로 옮긴다. 원점(0,0,…)이 아니라 0.5 중심으로 옮기는 이유는, 값이 전부 양수라
그대로 코사인을 쓰면 거의 모든 쌍이 0.8 이상으로 뭉개지기 때문이다.
방향만 보는 코사인의 약점(0.55 와 0.95 를 같은 방향으로 봄)은 거리 항으로 보정한다.

    fit = 0.6 × (1 + cos) / 2  +  0.4 × (1 − 가중 평균 절대오차)
"""

from __future__ import annotations

from math import sqrt

from backend.common.poi_data import TaggedPoi
from shared.types.models import MemberFit, PoiScore, PreferenceProfile

#: 적합도 식의 코사인 항 비중. 나머지는 거리 항.
COSINE_WEIGHT = 0.6
#: 그룹 점수 = 최저 적합도 × (1 − TIE_WEIGHT) + 평균 × TIE_WEIGHT. 평균은 동점 해소용.
TIE_WEIGHT = 0.15
#: 멤버 1명의 (축 값, 신뢰도 가중치).
Vector = tuple[list[float], list[float]]

AXIS_ORDER = ("activity_level", "crowd_tolerance", "nature_vs_urban", "food_priority", "pace")
#: 이 값 이하 신뢰도는 가중치 하한으로 올린다 — 모르는 축도 완전히 무시하지는 않는다.
_MIN_WEIGHT = 0.2
_AXIS_LABELS = {
    "activity_level": "활동량",
    "crowd_tolerance": "혼잡 허용",
    "nature_vs_urban": "자연·도심",
    "food_priority": "식사 비중",
    "pace": "일정 속도",
}


def score_pois(pois: list[TaggedPoi], members: list[PreferenceProfile]) -> list[PoiScore]:
    """모든 POI 의 멤버별 (정규화) 적합도와 그룹 점수를 계산해 점수 내림차순으로 돌려준다."""
    vectors = [(_vector(member), member) for member in members]
    raw = {
        poi.poi_id: [member_fit(vals, weights, poi.axis_features) for (vals, weights), _ in vectors]
        for poi in pois
    }
    best = [
        max((fits[i] for fits in raw.values()), default=1.0) or 1.0 for i in range(len(members))
    ]
    scores = [_score_one(poi, raw[poi.poi_id], best, vectors) for poi in pois]
    scores.sort(key=lambda score: score.fit_score, reverse=True)
    return scores


def member_fit(member_values: list[float], weights: list[float], poi: list[float]) -> float:
    """멤버 1명과 POI 1개의 적합도(0~1)."""
    centered_m = [value - 0.5 for value in member_values]
    centered_p = [value - 0.5 for value in poi]
    dot = sum(w * a * b for w, a, b in zip(weights, centered_m, centered_p, strict=True))
    norm_m = sqrt(sum(w * a * a for w, a in zip(weights, centered_m, strict=True)))
    norm_p = sqrt(sum(w * b * b for w, b in zip(weights, centered_p, strict=True)))
    cosine = dot / (norm_m * norm_p) if norm_m > 1e-9 and norm_p > 1e-9 else 0.0
    distance = sum(
        w * abs(a - b) for w, a, b in zip(weights, member_values, poi, strict=True)
    ) / sum(weights)
    fit = COSINE_WEIGHT * (1 + cosine) / 2 + (1 - COSINE_WEIGHT) * (1 - distance)
    return round(min(max(fit, 0.0), 1.0), 3)


def group_score(fits: list[float]) -> float:
    """maximin 그룹 점수(평균은 동점 해소용 가중치로만)."""
    if not fits:
        return 0.0
    worst, mean = min(fits), sum(fits) / len(fits)
    return round(worst * (1 - TIE_WEIGHT) + mean * TIE_WEIGHT, 3)


def _score_one(
    poi: TaggedPoi,
    raw_fits: list[float],
    best: list[float],
    vectors: list[tuple[Vector, PreferenceProfile]],
) -> PoiScore:
    """POI 1개의 점수와 설명. 멤버 적합도는 각자의 최고값 대비로 정규화한다."""
    fits = [
        MemberFit(member_id=member.member_id, fit=round(min(fit / top, 1.0), 3))
        for fit, top, (_, member) in zip(raw_fits, best, vectors, strict=True)
    ]
    names = {member.member_id: member.member_name for _, member in vectors}
    return PoiScore(
        poi_id=poi.poi_id,
        fit_score=group_score([item.fit for item in fits]),
        failure_probability=0.0,  # 일정·경로가 정해진 뒤 planner.risk 가 채운다
        reasons=_reasons(poi, fits, names, vectors),
        per_member_fit=fits,
    )


def _vector(member: PreferenceProfile) -> Vector:
    """프로필 → (축 값, 신뢰도 가중치). 축 순서는 PreferenceAxis 정의 순서."""
    by_axis = {axis.axis: axis for axis in member.axes}
    values, weights = [], []
    for axis in AXIS_ORDER:
        item = by_axis.get(axis)
        values.append(item.value if item else 0.5)
        weights.append(max(item.confidence if item else 0.0, _MIN_WEIGHT))
    return values, weights


def _reasons(
    poi: TaggedPoi,
    fits: list[MemberFit],
    names: dict[str, str],
    vectors: list[tuple[Vector, PreferenceProfile]],
) -> list[str]:
    """결과 화면용 근거 2~3줄: 가장 잘 맞는 사람·가장 손해 보는 사람·결정 축."""
    ranked = sorted(fits, key=lambda item: item.fit)
    worst, best = ranked[0], ranked[-1]
    reasons = [f"가장 잘 맞는 사람: {names[best.member_id]} ({best.fit:.0%})"]
    if len(fits) > 1:
        reasons.append(f"가장 아쉬운 사람: {names[worst.member_id]} ({worst.fit:.0%})")
    axis = _closest_shared_axis(poi.axis_features, [values for (values, _), _ in vectors])
    if axis is not None:
        reasons.append(f"그룹과 잘 맞는 축: {_AXIS_LABELS[axis]}")
    return reasons


def _closest_shared_axis(poi: list[float], members: list[list[float]]) -> str | None:
    """멤버들과의 평균 차이가 가장 작은 축. 차이가 0.2 넘으면 내세울 게 없다고 본다."""
    gaps = [
        (sum(abs(values[i] - poi[i]) for values in members) / len(members), AXIS_ORDER[i])
        for i in range(len(AXIS_ORDER))
    ]
    gap, axis = min(gaps)
    return axis if gap <= 0.2 else None
