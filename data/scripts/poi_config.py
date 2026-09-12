"""[W1] POI 수집 대상 도시·카테고리 정의와 최종 출력 스키마.

`collect_pois.py` 가 이 모듈의 상수와 순수 함수만 읽는다.
여기에는 API 호출도, 파일 입출력도 두지 않는다 (테스트와 검토를 쉽게 하기 위함).

⚠️ 저장 정책 (docs/DECISIONS.md 2026-08-27 / data/COLLECTION_PLAN.md 6절)
    Google Maps Platform 약관상 영구 저장이 가능한 것은 Place ID 뿐이고,
    위경도는 최대 30일 임시 캐싱이다. 그래서 최종 산출물은 `data/processed/`
    (= .gitignore 대상)에만 두고, 스크립트만 커밋한다.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, Field


class PoiRecord(BaseModel):
    """최종 저장 형식. 확정된 `POIVector` 8필드와 정확히 일치한다.

    필드 순서·이름·타입을 바꾸지 말 것. 9/11 배치 태깅이 이 형식을 전제로 한다.
    TODO: 공용 `schemas.py` 의 `POIVector` 가 main 에 머지되면 이 클래스를 삭제하고
          `from shared.types.schemas import POIVector` 로 교체한다.
          (아직 main 에 없으므로 내부 이름으로 임시 정의한다 — 공용 계약 아님)
    """

    poi_id: str
    """Google Place ID 를 그대로 쓴다. 별도 place_id 필드는 두지 않는다."""

    name: str
    lat: float
    lng: float

    tags: dict[str, float] = Field(default_factory=dict)
    """성향 태그 벡터. W1 에서는 항상 빈 dict 이고 9/11 배치 태깅에서 채운다."""

    category: str
    avg_duration_min: int
    open_hours: str | None = None


@dataclass(frozen=True)
class CategorySpec:
    """수집 카테고리 하나의 정규화 규칙과 목표 개수."""

    key: str
    """정규화된 category 값. 프로젝트 전체에서 이 문자열을 그대로 쓴다."""

    label: str
    min_count: int
    max_count: int
    avg_duration_min: int

    google_types: tuple[str, ...]
    """이 카테고리로 정규화할 Google place type 목록."""

    type_suffix: str | None
    """접미사 규칙. Google 의 음식점 타입은 `korean_restaurant` 처럼 수십 종이라
    전부 열거하는 대신 접미사로 잡는다. 없으면 None."""

    queries: tuple[str, ...]
    """Text Search 검색어 조각. 도시의 `search_suffix` 와 조합해서 쓴다."""


#: 정규화 우선순위 순서다. 한 장소가 여러 type 을 갖는 경우
#: (예: 미술관이 tourist_attraction 도 함께 반환) 위에 있는 카테고리가 이긴다.
#: 카페를 음식점보다 먼저 두는 이유: 카페 대부분이 restaurant type 을 함께 갖는다.
CATEGORY_SPECS: tuple[CategorySpec, ...] = (
    CategorySpec(
        key="cafe",
        label="카페",
        min_count=15,
        max_count=20,
        avg_duration_min=40,
        google_types=("cafe", "coffee_shop", "bakery", "tea_house", "dessert_shop"),
        type_suffix=None,
        queries=(
            "cafes",
            "coffee shops",
            "dessert cafes",
            "bakeries",
        ),
    ),
    CategorySpec(
        key="restaurant",
        label="음식점",
        min_count=30,
        max_count=40,
        avg_duration_min=60,
        google_types=("restaurant", "food_court", "steak_house", "bar_and_grill"),
        type_suffix="_restaurant",
        queries=(
            "restaurants",
            "popular local restaurants",
            "traditional restaurants",
            "fine dining restaurants",
            "casual dining restaurants",
        ),
    ),
    CategorySpec(
        key="culture",
        label="문화시설·전시",
        min_count=15,
        max_count=20,
        avg_duration_min=120,
        google_types=(
            "museum",
            "art_gallery",
            "performing_arts_theater",
            "cultural_center",
            "opera_house",
            "concert_hall",
            "planetarium",
        ),
        type_suffix=None,
        queries=(
            "museums",
            "art galleries",
            "exhibition halls",
            "theaters",
            "cultural centers",
        ),
    ),
    CategorySpec(
        key="nature",
        label="공원·자연",
        min_count=10,
        max_count=15,
        avg_duration_min=60,
        google_types=(
            "park",
            "national_park",
            "state_park",
            "garden",
            "botanical_garden",
            "hiking_area",
            "beach",
        ),
        type_suffix=None,
        queries=(
            "parks",
            "botanical gardens",
            "riverside parks",
            "nature viewpoints",
        ),
    ),
    CategorySpec(
        key="attraction",
        label="관광지·명소",
        min_count=30,
        max_count=40,
        avg_duration_min=90,
        google_types=(
            "tourist_attraction",
            "historical_landmark",
            "historical_place",
            "monument",
            "observation_deck",
            "plaza",
            "church",
            "place_of_worship",
            "buddhist_temple",
            "hindu_temple",
            "mosque",
            "synagogue",
            "amusement_park",
            "zoo",
            "aquarium",
        ),
        type_suffix=None,
        queries=(
            "tourist attractions",
            "famous landmarks",
            "historic sites",
            "observation decks",
            "famous temples and churches",
        ),
    ),
)

CATEGORY_BY_KEY: dict[str, CategorySpec] = {spec.key: spec for spec in CATEGORY_SPECS}

#: 도시별 최종 목표 개수 밴드. 팀 확정값(100~150)이며 카테고리 합과 일치해야 한다.
CITY_MIN_TOTAL = 100
CITY_MAX_TOTAL = 150

#: 리뷰 수 필터 기준. review_count 는 반환된 reviews 배열 길이가 아니라
#: Google 의 `userRatingCount`(전체 평가 규모)로 정의한다. 미만이면 제외한다.
MIN_REVIEW_COUNT = 10

#: Google Maps Platform 약관상 위경도 임시 캐싱 한도(일).
COORD_RETENTION_DAYS = 30


@dataclass(frozen=True)
class CityConfig:
    """수집 대상 도시 하나의 검색 조건과 경계 사각형."""

    key: str
    label: str
    search_suffix: str
    """검색어 뒤에 붙이는 지역 표현. 예) "restaurants in Paris, France"."""

    region_code: str
    #: 남서(low) / 북동(high) 코너. Google 은 (latitude, longitude) 순서다.
    low: tuple[float, float]
    high: tuple[float, float]

    def rectangle(self) -> dict[str, dict[str, float]]:
        """Places API 의 `locationRestriction.rectangle` 형식으로 변환한다."""
        return {
            "low": {"latitude": self.low[0], "longitude": self.low[1]},
            "high": {"latitude": self.high[0], "longitude": self.high[1]},
        }

    def contains(self, lat: float, lng: float) -> bool:
        """좌표가 도시 경계 사각형 안에 있는지 판정한다."""
        return self.low[0] <= lat <= self.high[0] and self.low[1] <= lng <= self.high[1]


#: 화이트리스트 = 파리(데모) + 타이베이(아시아 사례).
#: docs/DECISIONS.md 2026-09-06 "지원 도시는 파리 + 타이베이 2개로 확정" 기준.
CITIES: dict[str, CityConfig] = {
    "paris": CityConfig(
        key="paris",
        label="파리",
        search_suffix="Paris, France",
        region_code="FR",
        low=(48.8156, 2.2241),   # périphérique 내부 파리시 경계에 맞춘 박스
        high=(48.9022, 2.4699),
    ),
    "taipei": CityConfig(
        key="taipei",
        label="타이베이",
        search_suffix="Taipei, Taiwan",
        region_code="TW",
        low=(24.9600, 121.4570),  # 타이베이시 행정구역에 맞춘 박스
        high=(25.2100, 121.6660),
    ),
}


def resolve_category(google_types: list[str] | None, fallback: str) -> str:
    """Google 의 복수 type 을 내부 category 문자열 하나로 정규화한다.

    `CATEGORY_SPECS` 순서가 우선순위다. 어느 규칙에도 걸리지 않으면
    그 장소를 찾아낸 검색 카테고리(fallback)를 쓴다.
    """
    types = set(google_types or ())
    for spec in CATEGORY_SPECS:
        if types & set(spec.google_types):
            return spec.key
        if spec.type_suffix and any(t.endswith(spec.type_suffix) for t in types):
            return spec.key
    return fallback


def allocate_quota(limit: int) -> dict[str, int]:
    """`--limit` 을 카테고리 목표 비율대로 나눈다 (최대잉여법).

    `--limit 150` 이면 각 카테고리 상한을 그대로 쓰고(합 135, 목표 밴드 안),
    `--limit 10` 같은 스모크 테스트에서는 비율을 유지한 채 축소한다.
    """
    if limit <= 0:
        raise ValueError("limit 은 1 이상이어야 한다")

    ceilings = {spec.key: spec.max_count for spec in CATEGORY_SPECS}
    total_ceiling = sum(ceilings.values())
    target = min(limit, total_ceiling)

    exact = {key: value * target / total_ceiling for key, value in ceilings.items()}
    quota = {key: int(value) for key, value in exact.items()}

    remainder = target - sum(quota.values())
    by_fraction = sorted(exact, key=lambda key: exact[key] - quota[key], reverse=True)
    for key in by_fraction[:remainder]:
        quota[key] += 1
    return quota
