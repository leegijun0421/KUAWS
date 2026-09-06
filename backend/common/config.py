"""환경 설정. 모든 비밀 값은 .env 에서만 읽는다."""

import os
from functools import lru_cache

from pydantic import BaseModel

#: 기본 LLM 모델. 변경 시 .env 의 ANTHROPIC_MODEL 로 덮어쓴다.
DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-5"


class Settings(BaseModel):
    """애플리케이션 설정."""

    anthropic_api_key: str = ""
    anthropic_model: str = DEFAULT_ANTHROPIC_MODEL
    odsay_api_key: str = ""              # 국내 대중교통 경로 (ODsay)
    #: 키 A — Places + Routes 겸용. IP 제한, 절대 노출 금지.
    #: 프론트용 Maps JS 키(B)는 백엔드가 쓰지 않으므로 여기에 두지 않는다.
    google_backend_api_key: str = ""     # 해외 대중교통 경로 + POI (Google)
    cache_dir: str = "data/processed/cache"


@lru_cache
def get_settings() -> Settings:
    """설정을 한 번만 읽어 재사용한다."""
    return Settings(
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
        anthropic_model=os.getenv("ANTHROPIC_MODEL") or DEFAULT_ANTHROPIC_MODEL,
        odsay_api_key=os.getenv("ODSAY_API_KEY", ""),
        google_backend_api_key=os.getenv("GOOGLE_BACKEND_API_KEY", ""),
        cache_dir=os.getenv("CACHE_DIR", "data/processed/cache"),
    )
