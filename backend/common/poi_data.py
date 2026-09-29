"""태깅된 POI 데이터 로더 — scoring 과 planner 가 함께 쓴다.

우선순위
1. `data/processed/pois/<city>/tagged.json` — Google Places 수집 + LLM 5축 태깅 결과("collected")
2. `mocks/poi_seed/<city>.json` — 리포에 들어 있는 소규모 예시 데이터("seed")

2번은 수집·태깅을 아직 돌리지 않은 팀원 PC 와 CI 에서도 서비스가 끝까지 돌게 하는 안전망이다.
예시 데이터는 누구나 아는 명소를 사람이 직접 적은 것이라 Google 콘텐츠가 아니다(커밋 가능).

⚠️ 수집본의 좌표는 Google 약관상 30일 임시 캐싱 대상이다(`meta_<city>.json` 의 만료일).
   만료 후에는 `collect_pois.py --refresh` 로 다시 받는다.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field

from backend.common.config import data_path
from backend.common.logging import get_logger
from shared.types.models import Poi

logger = get_logger(__name__)

#: 식사 장소로 보는 category. 식사 시간대 배치(C1)가 이 값을 쓴다.
MEAL_CATEGORIES = frozenset({"restaurant"})


class TaggedPoi(BaseModel):
    """태깅까지 끝난 POI 1건. 계약상 `Poi`(6필드) + `axis_features` + 배치용 메타."""

    poi_id: str
    name: str
    category: str
    lat: float
    lng: float
    address: str = ""
    avg_duration_min: int = Field(default=60, ge=15, le=480)
    open_hours: str | None = None
    #: 5축 특성값(PreferenceAxis 순서, 0~1).
    axis_features: list[float] = Field(min_length=5, max_length=5)
    reasons: list[str] = []

    def to_poi(self) -> Poi:
        """공용 계약의 `Poi` 로 변환한다."""
        return Poi(
            poi_id=self.poi_id,
            name=self.name,
            category=self.category,
            lat=self.lat,
            lng=self.lng,
            address=self.address,
        )


class CityData(BaseModel):
    """도시 하나의 POI 묶음과 출처."""

    city: str
    pois: list[TaggedPoi]
    #: "collected" | "seed"
    source: str

    def by_id(self) -> dict[str, TaggedPoi]:
        """poi_id → POI."""
        return {poi.poi_id: poi for poi in self.pois}


def collected_path(city: str) -> Path:
    """수집·태깅된 POI 파일 경로.

    테스트는 이 함수를 바꿔 로컬 수집본과 격리한다(tests/conftest.py).
    """
    return data_path(f"data/processed/pois/{city}/tagged.json")


def load_city(city: str) -> CityData:
    """도시 POI 를 읽는다. 수집본이 없으면 예시 데이터로 대체하고 경고를 남긴다."""
    return _load_city_cached(city, _collected_mtime(city))


@lru_cache(maxsize=8)
def _load_city_cached(city: str, _mtime: float) -> CityData:
    """파일이 바뀌지 않았으면 다시 읽지 않는다(수정 시각을 캐시 키에 넣는다)."""
    collected = collected_path(city)
    if collected.exists():
        items = json.loads(collected.read_text(encoding="utf-8"))
        if items:
            pois = [TaggedPoi(**item) for item in items]
            return CityData(city=city, pois=pois, source="collected")
        logger.warning("%s: tagged.json 이 비어 있습니다 — 태깅을 다시 실행하세요", city)

    seed = data_path(f"mocks/poi_seed/{city}.json")
    if not seed.exists():
        raise FileNotFoundError(f"{city} 의 POI 데이터가 없습니다 ({collected} / {seed})")
    logger.warning("%s: 태깅 수집본이 없어 예시 데이터(seed)로 동작합니다", city)
    items = json.loads(seed.read_text(encoding="utf-8"))
    return CityData(city=city, pois=[TaggedPoi(**item) for item in items], source="seed")


def _collected_mtime(city: str) -> float:
    """수집본의 수정 시각. 없으면 0."""
    path = collected_path(city)
    return path.stat().st_mtime if path.exists() else 0.0
