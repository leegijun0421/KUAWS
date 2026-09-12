"""[W1] POI 수집의 체크포인트·산출물·로그 담당 모듈.

`collect_pois.py` 의 수집 로직과 파일 입출력을 분리해 둔 곳이다.
쓰기 대상은 전부 `data/processed/pois/<city>/` 아래이며 이 경로는 .gitignore 대상이다.

산출물
    pois_<city>.json      최종 POI (확정 8필드만)
    place_ids_<city>.json Place ID 목록 (약관상 영구 저장 가능한 유일한 값)
    meta_<city>.json      수집 시점·좌표 폐기 기한·집계
    checkpoint.json       재시작용 진행 상태
    collect_<UTC>.log     도시별 수집·필터 로그
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from logging import Logger
from pathlib import Path

from poi_config import (
    CATEGORY_BY_KEY,
    CATEGORY_SPECS,
    CITY_MAX_TOTAL,
    CITY_MIN_TOTAL,
    COORD_RETENTION_DAYS,
    MIN_REVIEW_COUNT,
    CityConfig,
)

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
CHECKPOINT_VERSION = 1


@dataclass
class Stats:
    """도시 1회 수집의 집계 카운터. 체크포인트에 그대로 저장된다."""

    candidates: int = 0        # 검색으로 받은 장소 수 (중복 포함)
    duplicates: int = 0        # Place ID 중복으로 건너뛴 수
    low_reviews: int = 0       # userRatingCount < MIN_REVIEW_COUNT
    no_location: int = 0       # location 결측
    closed: int = 0            # businessStatus == CLOSED_PERMANENTLY
    out_of_bounds: int = 0     # 도시 경계 사각형 밖
    no_name: int = 0           # displayName 결측
    details_failed: int = 0    # 결측 보강용 Place Details 실패
    api_failures: int = 0      # 그 외 API 실패 (HTTP 오류·재시도 소진·id 결측)
    over_quota: int = 0        # 필터는 통과했지만 카테고리 쿼터가 차서 미채택
    accepted: int = 0          # 최종 채택


def new_checkpoint(city: CityConfig, language_code: str) -> dict:
    """빈 체크포인트를 만든다."""
    now = datetime.now(UTC).isoformat()
    return {
        "version": CHECKPOINT_VERSION,
        "city": city.key,
        "language_code": language_code,
        "created_at": now,
        "updated_at": now,
        "completed_queries": [],
        "processed": {},
        "stats": asdict(Stats()),
    }


def load_checkpoint(
    out_dir: Path, city: CityConfig, language_code: str, refresh: bool, logger: Logger
) -> dict:
    """체크포인트를 읽는다. --refresh 이거나 형식/도시가 다르면 새로 만든다."""
    path = out_dir / "checkpoint.json"
    if not path.exists():
        return new_checkpoint(city, language_code)

    if refresh:
        logger.info("--refresh: 기존 체크포인트를 버리고 전체를 다시 조회한다")
        return new_checkpoint(city, language_code)

    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("version") != CHECKPOINT_VERSION or payload.get("city") != city.key:
        logger.warning("체크포인트 형식/도시가 달라 새로 시작한다")
        return new_checkpoint(city, language_code)

    warn_if_stale(payload, logger)
    logger.info(
        "체크포인트 이어받음: 처리 %d건, 완료 검색어 %d개",
        len(payload["processed"]),
        len(payload["completed_queries"]),
    )
    return payload


def warn_if_stale(payload: dict, logger: Logger) -> None:
    """수집 시점이 30일을 넘었으면 좌표 폐기 기한을 경고한다."""
    created = datetime.fromisoformat(str(payload.get("created_at")))
    age = datetime.now(UTC) - created
    if age > timedelta(days=COORD_RETENTION_DAYS):
        logger.warning(
            "체크포인트가 %d일 경과 — Google 약관상 위경도 보관 한도(%d일)를 넘었다. "
            "--refresh 로 재수집할 것.",
            age.days,
            COORD_RETENTION_DAYS,
        )


def save_checkpoint(out_dir: Path, checkpoint: dict) -> None:
    """체크포인트를 원자적으로 저장한다."""
    checkpoint["updated_at"] = datetime.now(UTC).isoformat()
    write_json(out_dir / "checkpoint.json", checkpoint)


def write_outputs(
    out_dir: Path,
    city: CityConfig,
    checkpoint: dict,
    selected: list[dict],
    quota: dict[str, int],
    per_category: dict[str, int],
    language_code: str,
    limit: int,
) -> None:
    """최종 POI, Place ID 목록, 메타데이터를 저장한다."""
    collected_at = datetime.now(UTC)
    expires_at = collected_at + timedelta(days=COORD_RETENTION_DAYS)
    write_json(out_dir / f"pois_{city.key}.json", selected)
    write_json(out_dir / f"place_ids_{city.key}.json", [item["poi_id"] for item in selected])
    write_json(
        out_dir / f"meta_{city.key}.json",
        {
            "city": city.key,
            "label": city.label,
            "collected_at": collected_at.isoformat(),
            "coord_expires_at": expires_at.isoformat(),
            "language_code": language_code,
            "limit": limit,
            "quota": quota,
            "counts": per_category,
            "total": len(selected),
            "stats": checkpoint["stats"],
            "note": (
                "위경도는 Google 약관상 30일 임시 캐싱 대상이다. coord_expires_at 이후에는 "
                "--refresh 로 재수집하거나 좌표를 삭제할 것. 영구 저장이 가능한 값은 "
                "place_ids_*.json 의 Place ID 뿐이다."
            ),
        },
    )


def write_json(path: Path, payload: object) -> None:
    """임시 파일에 쓰고 교체해서 중단 시 파일이 깨지지 않게 한다."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


# ---------- 로깅 ----------


def build_logger(log_path: Path) -> Logger:
    """공용 로거를 얻고 도시별 로그 파일 핸들러를 붙인다.

    `.kiro/steering/conventions.md` 규칙에 따라 print() 를 쓰지 않고
    `backend/common/logging.py` 의 로거를 재사용한다. 리포 루트 밖에서 단독 실행하는
    경우에만 같은 포맷의 대체 로거로 내려간다 (probe_routes.py 의 dotenv 처리와 동일한 방식).
    """
    try:
        from backend.common.logging import get_logger
    except ImportError:
        logger = logging.getLogger("collect_pois")
        logger.setLevel(logging.INFO)
        if not logger.handlers:
            stream = logging.StreamHandler()
            stream.setFormatter(logging.Formatter(LOG_FORMAT))
            logger.addHandler(stream)
    else:
        logger = get_logger("collect_pois")

    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    logger.addHandler(handler)
    return logger


def format_counts(counts: dict[str, int]) -> str:
    """카테고리 카운트를 한 줄로 만든다."""
    return ", ".join(
        f"{CATEGORY_BY_KEY[key].label}={counts.get(key, 0)}" for key in CATEGORY_BY_KEY
    )


def log_summary(
    logger: Logger,
    city: CityConfig,
    checkpoint: dict,
    per_category: dict[str, int],
    quota: dict[str, int],
    out_dir: Path,
) -> None:
    """수집·필터 집계를 도시별로 출력한다. API 키와 응답 원문은 남기지 않는다."""
    stats = checkpoint["stats"]
    logger.info("=== %s 수집 결과 ===", city.label)
    logger.info("검색된 후보 수(중복 포함) : %d", stats["candidates"])
    logger.info("Place ID 중복 제거        : %d", stats["duplicates"])
    logger.info("review_count < %d 제외    : %d", MIN_REVIEW_COUNT, stats["low_reviews"])
    logger.info("location 없음 제외        : %d", stats["no_location"])
    logger.info("영구 폐업 제외            : %d", stats["closed"])
    logger.info("도시 범위 밖 제외         : %d", stats["out_of_bounds"])
    logger.info("이름 없음 제외            : %d", stats["no_name"])
    logger.info("Details 보강 실패         : %d", stats["details_failed"])
    logger.info("기타 API 실패             : %d", stats["api_failures"])
    logger.info("쿼터 초과 미채택          : %d", stats["over_quota"])
    logger.info("최종 accepted             : %d", stats["accepted"])
    logger.info("카테고리별 최종           : %s", format_counts(per_category))
    warn_on_shortfall(logger, stats, per_category, quota)
    logger.info("산출물: %s (Git 추적 대상 아님)", out_dir)


def warn_on_shortfall(
    logger: Logger, stats: dict, per_category: dict[str, int], quota: dict[str, int]
) -> None:
    """본 수집에서 카테고리 최소치나 도시 밴드를 못 채우면 경고한다."""
    for spec in CATEGORY_SPECS:
        got = per_category.get(spec.key, 0)
        if quota.get(spec.key, 0) >= spec.min_count and got < spec.min_count:
            logger.warning(
                "%s 목표 미달: %d건 (최소 %d) — 검색어 추가나 --max-pages 상향 필요",
                spec.label,
                got,
                spec.min_count,
            )

    # 쿼터 합이 밴드에 못 미치는 스모크 테스트(--limit 10 등)에서는 경고하지 않는다.
    if sum(quota.values()) < CITY_MIN_TOTAL:
        return
    total = stats["accepted"]
    if not CITY_MIN_TOTAL <= total <= CITY_MAX_TOTAL:
        logger.warning("도시 총합 %d건 — 목표 밴드 %d~%d 밖", total, CITY_MIN_TOTAL, CITY_MAX_TOTAL)
