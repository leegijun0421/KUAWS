"""환경 설정. 모든 비밀 값은 .env 에서만 읽는다."""

import os
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel

try:
    from dotenv import load_dotenv

    # encoding="utf-8-sig": PowerShell 의 Set-Content 가 붙이는 BOM 이 첫 키 이름에
    # 섞여 python-dotenv 가 키를 못 읽는 문제를 막는다(test_claude.py 와 동일).
    load_dotenv(encoding="utf-8-sig")
except ImportError:  # python-dotenv 가 없으면 OS 환경변수만 쓴다
    pass

#: 기본 LLM 모델. 변경 시 .env 의 ANTHROPIC_MODEL 로 덮어쓴다.
DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-5"

#: 리포 루트. 스크립트를 어느 폴더에서 실행해도 data/ 경로가 흔들리지 않게 한다.
REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseModel):
    """애플리케이션 설정."""

    anthropic_api_key: str = ""
    anthropic_model: str = DEFAULT_ANTHROPIC_MODEL
    odsay_api_key: str = ""              # 국내 대중교통 경로 (ODsay)
    #: 키 A — Places + Routes 겸용. IP 제한, 절대 노출 금지.
    #: 프론트용 Maps JS 키(B)는 백엔드가 쓰지 않으므로 여기에 두지 않는다.
    google_backend_api_key: str = ""     # 해외 대중교통 경로 + POI (Google)
    cache_dir: str = "data/processed/cache"
    #: 공유 링크의 앞부분. 배포 시 실제 프론트 주소로 바꾼다.
    public_base_url: str = "http://localhost:5173"
    #: 1이면 LLM 을 부르지 않고 규칙 기반 추출기로 대체한다(키 없는 데모·CI 용).
    llm_offline: bool = False


@lru_cache
def get_settings() -> Settings:
    """설정을 한 번만 읽어 재사용한다."""
    return Settings(
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
        anthropic_model=os.getenv("ANTHROPIC_MODEL") or DEFAULT_ANTHROPIC_MODEL,
        odsay_api_key=os.getenv("ODSAY_API_KEY", ""),
        google_backend_api_key=os.getenv("GOOGLE_BACKEND_API_KEY", ""),
        cache_dir=os.getenv("CACHE_DIR", "data/processed/cache"),
        public_base_url=os.getenv("PUBLIC_BASE_URL") or "http://localhost:5173",
        llm_offline=os.getenv("LLM_OFFLINE", "") == "1",
    )


def data_path(relative: str) -> Path:
    """리포 루트 기준 상대 경로를 절대 경로로 바꾼다."""
    path = Path(relative)
    return path if path.is_absolute() else REPO_ROOT / path
