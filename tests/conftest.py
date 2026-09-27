"""공통 테스트 설정 — 외부 API·디스크 부작용 격리."""

import pytest

from backend.common.config import get_settings


@pytest.fixture(autouse=True)
def _isolate_settings(tmp_path, monkeypatch):
    """캐시·공유 DB 를 임시 폴더로 돌리고, 실제 키로 외부 API 를 부르지 않게 한다."""
    monkeypatch.setenv("CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("SHARE_DB_PATH", str(tmp_path / "share.db"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("GOOGLE_BACKEND_API_KEY", "")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
