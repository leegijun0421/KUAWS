"""planner API. 경로 접두사 `/api/planner` 는 `backend/main.py` 에서 붙인다.

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET  | `/cities` | 지원 도시(화이트리스트)와 데이터 출처 |
| POST | `/plan`   | 프로필 N개 → 일정(`Itinerary`) |
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.common.cities import CITIES
from backend.common.poi_data import load_city
from backend.planner.service import create_plan
from backend.routing.provider import RouteProviderError
from shared.types.models import CityInfo, Itinerary, PlanRequest

router = APIRouter()


@router.get("/cities", response_model=list[CityInfo])
def get_cities() -> list[CityInfo]:
    """지원 도시 목록. 데이터가 예시(seed)인지 수집본인지 함께 알려준다."""
    infos = []
    for city in CITIES.values():
        data = load_city(city.key)
        infos.append(
            CityInfo(
                key=city.key,
                label=city.label,
                timezone=city.timezone,
                poi_count=len(data.pois),
                data_source=data.source,
            )
        )
    return infos


@router.post("/plan", response_model=Itinerary)
def post_plan(body: PlanRequest) -> Itinerary:
    """일정을 만든다. 경로 API 오류는 재시도 가능 오류(503)로 알린다."""
    try:
        return create_plan(body)
    except ValueError as exc:  # 지원하지 않는 도시·날짜 형식 등 입력 오류
        raise HTTPException(422, str(exc)) from exc
    except RouteProviderError as exc:
        message = f"대중교통 경로 조회에 실패했습니다. 잠시 후 다시 시도해 주세요. ({exc})"
        raise HTTPException(503, message) from exc
