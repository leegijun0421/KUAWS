"""[W1] 화이트리스트 도시(파리·타이베이) POI 수집·정규화 스크립트.

실행 방법 (프로젝트 루트에서)
    python data/scripts/collect_pois.py --city paris  --limit 10      # 스모크 10건
    python data/scripts/collect_pois.py --city taipei --limit 10
    python data/scripts/collect_pois.py --city paris  --limit 150     # 본 수집
    python data/scripts/collect_pois.py --city paris  --limit 150 --refresh

예상 소요 시간
    --limit 10  : 30초 이내 (Text Search 5~10회)
    --limit 150 : 3~6분 (Text Search 약 25~45회 + 결측 보강 Details 소수)
    중단해도 같은 명령을 다시 실행하면 체크포인트부터 이어서 진행한다.

필요한 환경변수
    GOOGLE_BACKEND_API_KEY  — 키 A(Places + Routes 겸용). 프로젝트 루트 `.env` 에서 읽는다.
    docs/DECISIONS.md 2026-09-06 결정에 따라 PLACES_API_KEY 는 사용하지 않는다.

⚠️ 저장 정책 (docs/DECISIONS.md 2026-08-27 / data/COLLECTION_PLAN.md 6절)
    Google Maps Platform 약관상 영구 저장 가능한 것은 Place ID 뿐이고 위경도는
    최대 30일 임시 캐싱이다. 따라서 산출물은 전부 `data/processed/` (.gitignore 대상)
    에만 쓰고 스크립트만 커밋한다. 30일이 지나면 --refresh 로 재수집한다.
    리뷰 원문·평점·리뷰수·응답 원문은 파일에도 로그에도 남기지 않는다.

모듈 구성 (steering 의 파일 300줄 규칙에 맞춰 나눴다)
    poi_config.py         도시·카테고리 정의, 최종 8필드 스키마, 쿼터 계산
    poi_places_client.py  Places API (New) 호출과 재시도
    poi_filters.py        필터·카테고리 정규화 (네트워크 없는 순수 함수)
    poi_store.py          체크포인트·산출물·로그
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, datetime
from logging import Logger
from pathlib import Path

import httpx
from poi_config import (
    CATEGORY_SPECS,
    CITIES,
    CITY_MAX_TOTAL,
    CategorySpec,
    CityConfig,
    allocate_quota,
)
from poi_filters import (
    count_candidates,
    evaluate_place,
    needs_details,
    reject_entry,
    select_within_quota,
)
from poi_places_client import PlacesClient
from poi_store import (
    build_logger,
    format_counts,
    load_checkpoint,
    log_summary,
    save_checkpoint,
    write_outputs,
)

API_KEY_ENV = "GOOGLE_BACKEND_API_KEY"

#: 산출물 위치. data/processed/* 는 .gitignore 대상이라 커밋되지 않는다.
REPO_ROOT = Path(__file__).resolve().parents[2]
PROCESSED_ROOT = REPO_ROOT / "data" / "processed" / "pois"

if str(REPO_ROOT) not in sys.path:
    # backend/common/logging.py 의 공용 로거를 쓰기 위해 리포 루트를 경로에 넣는다.
    sys.path.insert(0, str(REPO_ROOT))

try:
    from dotenv import load_dotenv

    # encoding="utf-8-sig": Windows PowerShell 이 붙이는 BOM 이 첫 키 이름에 섞이는
    # 문제를 막는다 (test_claude.py 에 같은 주석이 있다).
    load_dotenv(REPO_ROOT / ".env", encoding="utf-8-sig")
except ImportError:  # python-dotenv 없이 환경변수만으로도 동작하게 둔다
    pass


def main() -> None:
    """CLI 진입점. 도시 하나를 수집하고 산출물과 집계를 남긴다."""
    args = parse_args()
    city = CITIES[args.city]

    api_key = os.environ.get(API_KEY_ENV)
    if not api_key:
        sys.exit(f"환경변수 {API_KEY_ENV} 가 비어 있다. .env 에 키 A 를 넣을 것.")

    out_dir = PROCESSED_ROOT / city.key
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    logger = build_logger(out_dir / f"collect_{stamp}.log")

    quota = allocate_quota(args.limit)
    logger.info("=== %s POI 수집 시작 (limit=%d) ===", city.label, args.limit)
    logger.info("카테고리 쿼터: %s", format_counts(quota))

    checkpoint = load_checkpoint(out_dir, city, args.language, args.refresh, logger)
    try:
        collect(checkpoint, city, quota, api_key, args, logger, out_dir)
    finally:
        # 중단·예외 상황에서도 진행 상태는 남긴다.
        save_checkpoint(out_dir, checkpoint)

    selected, per_category = select_within_quota(checkpoint, quota)
    write_outputs(
        out_dir, city, checkpoint, selected, quota, per_category, args.language, args.limit
    )
    save_checkpoint(out_dir, checkpoint)
    log_summary(logger, city, checkpoint, per_category, quota, out_dir)


def parse_args() -> argparse.Namespace:
    """CLI 인자를 파싱한다."""
    parser = argparse.ArgumentParser(description="화이트리스트 도시 POI 수집·정규화 (W1)")
    parser.add_argument("--city", required=True, choices=sorted(CITIES), help="수집 대상 도시")
    parser.add_argument("--limit", type=int, default=CITY_MAX_TOTAL, help="도시 최종 POI 상한")
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="기존 체크포인트를 무시하고 전체를 다시 조회한다 (30일 경과 재수집용)",
    )
    parser.add_argument(
        "--max-pages", type=int, default=3, help="검색어당 최대 페이지 수 (1페이지=20건)"
    )
    parser.add_argument("--language", default="en", help="displayName·영업시간 언어 코드")
    return parser.parse_args()


def collect(
    checkpoint: dict,
    city: CityConfig,
    quota: dict[str, int],
    api_key: str,
    args: argparse.Namespace,
    logger: Logger,
    out_dir: Path,
) -> None:
    """카테고리를 순서대로 돌며 수집한다. API 실패 수를 체크포인트에 합산한다."""
    with PlacesClient(api_key, logger) as client:
        for spec in CATEGORY_SPECS:
            run_category(client, city, spec, quota[spec.key], checkpoint, args, logger, out_dir)
            save_checkpoint(out_dir, checkpoint)
        checkpoint["stats"]["api_failures"] += client.failures
        logger.info(
            "API 호출 수: searchText=%d, placeDetails=%d",
            client.search_calls,
            client.details_calls,
        )


def run_category(
    client: PlacesClient,
    city: CityConfig,
    spec: CategorySpec,
    quota: int,
    checkpoint: dict,
    args: argparse.Namespace,
    logger: Logger,
    out_dir: Path,
) -> None:
    """카테고리 하나를 쿼터가 찰 때까지 검색어 순서대로 수집한다."""
    logger.info("[%s] 목표 %d건", spec.label, quota)
    if quota <= 0:
        return

    for index, fragment in enumerate(spec.queries):
        if count_candidates(checkpoint, spec.key) >= quota:
            logger.info("  쿼터 충족 — 남은 검색어 %d개 생략", len(spec.queries) - index)
            return

        query = f"{fragment} in {city.search_suffix}"
        if query in checkpoint["completed_queries"]:
            logger.info("  체크포인트에 완료된 검색어 건너뜀: %s", query)
            continue

        fully_paginated = run_query(client, query, city, spec, quota, checkpoint, args)
        if fully_paginated:
            # 끝까지 페이지를 넘긴 검색어만 완료로 기록한다. 쿼터 때문에 중간에 끊은
            # 검색어는 남겨 둬야 --limit 을 올려 재실행할 때 이어서 볼 수 있다.
            checkpoint["completed_queries"].append(query)
        save_checkpoint(out_dir, checkpoint)


def run_query(
    client: PlacesClient,
    query: str,
    city: CityConfig,
    spec: CategorySpec,
    quota: int,
    checkpoint: dict,
    args: argparse.Namespace,
) -> bool:
    """검색어 하나를 페이지 끝까지 처리한다. 쿼터로 중단하면 False 를 반환한다."""
    pages = client.search_text(
        query, city.rectangle(), args.language, city.region_code, args.max_pages
    )
    for place in pages:
        checkpoint["stats"]["candidates"] += 1
        process_place(place, city, spec, checkpoint, client, args)
        if count_candidates(checkpoint, spec.key) >= quota:
            return False
    return True


def process_place(
    place: dict,
    city: CityConfig,
    spec: CategorySpec,
    checkpoint: dict,
    client: PlacesClient,
    args: argparse.Namespace,
) -> None:
    """장소 1건을 중복 확인 → 결측 보강 → 필터 → 정규화 순으로 처리한다."""
    stats = checkpoint["stats"]
    place_id = place.get("id")
    if not place_id:
        stats["api_failures"] += 1
        return
    if place_id in checkpoint["processed"]:
        # 이미 판정한 Place ID 는 다시 API 를 태우지 않는다 (중복 제거 + 재시작 지점).
        stats["duplicates"] += 1
        return

    if needs_details(place):
        detail = client.fetch_details(place_id, args.language, city.region_code)
        if detail is None:
            stats["details_failed"] += 1
            checkpoint["processed"][place_id] = reject_entry("details_failed")
            return
        place = {**place, **detail}

    reason, record = evaluate_place(place, city, spec)
    if record is None:
        stats[reason] += 1
        checkpoint["processed"][place_id] = reject_entry(reason)
        return
    checkpoint["processed"][place_id] = {
        "status": "candidate",
        "reason": None,
        "record": record.model_dump(),
    }


if __name__ == "__main__":
    try:
        main()
    except httpx.HTTPError as exc:
        sys.exit(f"HTTP 오류로 중단: {type(exc).__name__} — 체크포인트는 저장되어 있다")
