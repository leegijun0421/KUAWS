"""[W1] POI 필터와 정규화 — 네트워크 없이 단위 검증이 가능한 순수 함수 모음.

여기서 팀 확정 필터 5개를 적용한다.
    1. Place ID 중복 제거          (collect_pois.py 의 체크포인트 조회로 처리)
    2. userRatingCount < 10 제외
    3. location 결측 제외
    4. CLOSED_PERMANENTLY 제외
    5. 도시 검색 범위 밖 제외

⚠️ rating / userRatingCount / businessStatus / types 는 이 모듈 안에서만 쓰고 버린다.
    최종 산출물(`PoiRecord`)에는 확정된 8필드만 남는다.
"""

from __future__ import annotations

from poi_config import (
    CATEGORY_BY_KEY,
    CATEGORY_SPECS,
    MIN_REVIEW_COUNT,
    CategorySpec,
    CityConfig,
    PoiRecord,
    resolve_category,
)


def evaluate_place(
    place: dict, city: CityConfig, spec: CategorySpec
) -> tuple[str, PoiRecord | None]:
    """필터를 적용하고 통과한 장소만 최종 8필드 형식으로 정규화한다.

    필터 순서는 영구폐업 → location 결측 → 도시 범위 → userRatingCount → 이름 결측이며,
    한 장소는 처음 걸린 사유 하나에만 집계된다(같은 장소를 두 번 세지 않기 위함).
    반환값의 첫 항목은 통계 카운터 이름이고, 통과하면 "accepted" 와 레코드를 준다.
    """
    if place.get("businessStatus") == "CLOSED_PERMANENTLY":
        return "closed", None

    location = place.get("location") or {}
    raw_lat, raw_lng = location.get("latitude"), location.get("longitude")
    if raw_lat is None or raw_lng is None:
        return "no_location", None
    lat, lng = float(raw_lat), float(raw_lng)
    if not city.contains(lat, lng):
        return "out_of_bounds", None

    # review_count 는 userRatingCount 로 정의한다 (반환된 reviews 배열 길이가 아니다).
    if int(place.get("userRatingCount") or 0) < MIN_REVIEW_COUNT:
        return "low_reviews", None

    name = (place.get("displayName") or {}).get("text")
    if not name:
        return "no_name", None

    category = resolve_category(place.get("types"), spec.key)
    record = PoiRecord(
        poi_id=str(place["id"]),  # Google Place ID 를 그대로 쓴다
        name=str(name),
        lat=lat,
        lng=lng,
        tags={},  # W1 은 항상 빈 dict. 9/11 배치 태깅에서 채운다.
        category=category,
        avg_duration_min=CATEGORY_BY_KEY[category].avg_duration_min,
        open_hours=normalize_open_hours(place),
    )
    return "accepted", record


def needs_details(place: dict) -> bool:
    """Text Search 응답에 필터용 필수값이 빠졌을 때만 Place Details 를 부른다."""
    has_location = bool(place.get("location"))
    has_review_count = place.get("userRatingCount") is not None
    return not (has_location and has_review_count)


def normalize_open_hours(place: dict) -> str | None:
    """`regularOpeningHours.weekdayDescriptions` 를 한 줄 문자열로 합친다."""
    descriptions = (place.get("regularOpeningHours") or {}).get("weekdayDescriptions")
    if not descriptions:
        return None
    return " | ".join(str(item) for item in descriptions)


def select_within_quota(
    checkpoint: dict, quota: dict[str, int]
) -> tuple[list[dict], dict[str, int]]:
    """후보를 발견 순서대로 카테고리 쿼터까지 채택한다.

    발견 순서를 쓰는 이유: 평점·리뷰수를 정렬 키로 쓰려면 저장 금지 값을 파일에
    들고 있어야 한다. Google 의 relevance 순위가 이미 앞쪽에 대표 장소를 준다.
    """
    per_category = {spec.key: 0 for spec in CATEGORY_SPECS}
    selected: list[dict] = []
    over_quota = 0
    for entry in checkpoint["processed"].values():
        if entry["status"] != "candidate":
            continue
        record = entry["record"]
        key = str(record["category"])
        if per_category.get(key, 0) >= quota.get(key, 0):
            over_quota += 1
            continue
        per_category[key] += 1
        selected.append(record)
    checkpoint["stats"]["over_quota"] = over_quota
    checkpoint["stats"]["accepted"] = len(selected)
    return selected, per_category


def count_candidates(checkpoint: dict, category: str) -> int:
    """체크포인트에서 특정 카테고리로 정규화된 후보 수를 센다."""
    return sum(
        1
        for entry in checkpoint["processed"].values()
        if entry["status"] == "candidate" and entry["record"]["category"] == category
    )


def reject_entry(reason: str) -> dict:
    """체크포인트에 남길 탈락 기록을 만든다."""
    return {"status": "rejected", "reason": reason, "record": None}
