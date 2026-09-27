"""share API. 경로 접두사 `/api/share` 는 `backend/main.py` 에서 붙인다.

| 메서드 | 경로 | 설명 |
|--------|------|------|
| POST | `/`          | 공유 링크 생성(입력 + 장소 순서만 저장) |
| GET  | `/{plan_id}` | 링크 열람 — 같은 순서로 경로만 다시 계산한 `Itinerary` |

플랫폼 비종속: 링크 하나(URL)로 끝난다. 카카오톡·인스타 등 특정 SDK 를 쓰지 않는다.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.common.config import get_settings
from backend.planner.service import create_plan
from backend.routing.provider import RouteProviderError
from backend.share.store import load_share, save_share
from shared.types.models import Itinerary, ShareLinkResponse, ShareRequest

router = APIRouter()


@router.post("", response_model=ShareLinkResponse)
def post_share(body: ShareRequest) -> ShareLinkResponse:
    """공유 링크를 만든다."""
    if not any(body.day_orders):
        raise HTTPException(422, "공유할 장소가 없습니다.")
    plan_id, expires_at = save_share(body)
    base = get_settings().public_base_url.rstrip("/")
    return ShareLinkResponse(plan_id=plan_id, url=f"{base}/s/{plan_id}", expires_at=expires_at)


@router.get("/{plan_id}", response_model=Itinerary)
def get_share(plan_id: str) -> Itinerary:
    """링크를 열면 저장된 순서대로 일정을 다시 계산한다."""
    stored = load_share(plan_id)
    if stored is None:
        raise HTTPException(404, "링크가 없거나 만료됐습니다(30일).")
    try:
        return create_plan(stored.request, day_orders=stored.day_orders)
    except RouteProviderError as exc:
        raise HTTPException(503, f"경로를 다시 불러오지 못했습니다. ({exc})") from exc
