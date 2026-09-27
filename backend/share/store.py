"""공유 링크 저장소 — SQLite 한 테이블.

저장하는 것: 일정 생성 **입력**(도시·날짜·멤버 프로필·제약)과 **일차별 Place ID 순서**뿐이다.
경로·시각은 저장하지 않는다. Google 약관상 경로 응답은 저장·캐싱할 수 없고, Place ID 는
영구 저장이 허용되기 때문이다. 링크를 열 때 `planner.replay` 가 경로만 다시 계산한다.

만료: 30일. 수집 좌표의 임시 캐싱 한도(30일)와 맞췄다.
"""

from __future__ import annotations

import secrets
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone

from backend.common.config import data_path, get_settings
from shared.types.models import ShareRequest

EXPIRES_DAYS = 30

_SCHEMA = """
CREATE TABLE IF NOT EXISTS shared_plans (
    plan_id    TEXT PRIMARY KEY,
    payload    TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
)
"""


def save_share(request: ShareRequest) -> tuple[str, str]:
    """공유 요청을 저장하고 (plan_id, 만료 시각 ISO) 를 돌려준다."""
    plan_id = secrets.token_urlsafe(6)
    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=EXPIRES_DAYS)
    with closing(_connect()) as connection, connection:
        connection.execute(
            "INSERT INTO shared_plans VALUES (?, ?, ?, ?)",
            (plan_id, request.model_dump_json(), now.isoformat(), expires.isoformat()),
        )
    return plan_id, expires.isoformat(timespec="seconds")


def load_share(plan_id: str) -> ShareRequest | None:
    """저장된 요청을 읽는다. 없거나 만료됐으면 None."""
    with closing(_connect()) as connection:
        row = connection.execute(
            "SELECT payload, expires_at FROM shared_plans WHERE plan_id = ?", (plan_id,)
        ).fetchone()
    if row is None:
        return None
    payload, expires_at = row
    if datetime.fromisoformat(expires_at) < datetime.now(timezone.utc):
        return None
    return ShareRequest.model_validate_json(payload)


def _connect() -> sqlite3.Connection:
    """DB 연결. 파일과 테이블이 없으면 만든다."""
    path = data_path(get_settings().share_db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.execute(_SCHEMA)
    return connection
