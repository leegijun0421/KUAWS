"""환경 설정. 모든 비밀 값은 .env 에서만 읽는다."""

import os
from functools import lru_cache

from pydantic import BaseModel


class Settings(BaseModel):
    """애플리케이션 설정."""

    aws_region: str = "us-east-1"
    bedrock_model_id: str = ""
    transit_api_key: str = ""
    places_api_key: str = ""
    cache_dir: str = "data/processed/cache"


@lru_cache
def get_settings() -> Settings:
    """설정을 한 번만 읽어 재사용한다."""
    return Settings(
        aws_region=os.getenv("AWS_REGION", "us-east-1"),
        bedrock_model_id=os.getenv("BEDROCK_MODEL_ID", ""),
        transit_api_key=os.getenv("TRANSIT_API_KEY", ""),
        places_api_key=os.getenv("PLACES_API_KEY", ""),
        cache_dir=os.getenv("CACHE_DIR", "data/processed/cache"),
    )
