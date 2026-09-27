"""[W1] POI 5축 사전 배치 태깅 (LLM) — 수집된 POI 에 `axis_features` 를 붙인다.

실행 방법 (프로젝트 루트에서)
    python data/scripts/tag_pois.py --city paris --limit 20     # 스파이크/스모크 20건 (PS-8)
    python data/scripts/tag_pois.py --city paris                # 전량
    python data/scripts/tag_pois.py --city taipei --workers 8

입력  data/processed/pois/<city>/pois_<city>.json   (collect_pois.py 산출물, 8필드)
출력  data/processed/pois/<city>/tagged.json         (.gitignore 대상 — 커밋하지 않는다)

예상 소요 시간
    POI 135개 · workers 6 기준 약 2~3분. 결과는 LLM 캐시(`data/processed/cache/llm/`)에
    남으므로 중단 후 다시 실행하면 이미 태깅한 POI 는 API 를 다시 부르지 않는다(PS-6).

계약 (`.kiro/specs/poi-scoring/requirements.md`, docs/DECISIONS.md 2026-09-09)
- PS-1/4 axis_features 는 길이 5, PreferenceAxis 순서, 각 0.0~1.0
- PS-2 입력은 메타데이터만(name/category/address/avg_duration_min/open_hours). 리뷰 텍스트 없음
- PS-3 LLM 은 `LLMProvider` 뒤로 격리(`backend.common.llm`)
- PS-5 JSON 파싱 1회 재시도 후 실패하면 그 POI 만 건너뛰고 배치는 계속
- PS-7 사람이 검수할 수 있게 축 값 옆에 근거(reasons)를 함께 저장

필요한 환경변수: ANTHROPIC_API_KEY (선택 ANTHROPIC_MODEL). 루트 `.env` 에서 읽는다.
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.common.llm import (  # noqa: E402
    LLMResponseError,
    LLMUnavailableError,
    complete_json,
    get_llm_provider,
    render_prompt,
)
from backend.common.logging import get_logger  # noqa: E402
from shared.types.models import LLMProvider  # noqa: E402

logger = get_logger("tag_pois")

POI_ROOT = REPO_ROOT / "data" / "processed" / "pois"
AXIS_COUNT = 5


def main() -> None:
    """도시 하나의 POI 를 태깅해 tagged.json 을 쓴다."""
    parser = argparse.ArgumentParser(description="POI 5축 사전 배치 태깅")
    parser.add_argument("--city", required=True, choices=["paris", "taipei"])
    parser.add_argument("--limit", type=int, default=0, help="앞에서 N건만 (0 = 전량)")
    parser.add_argument("--workers", type=int, default=6, help="동시 호출 수")
    args = parser.parse_args()

    pois = load_pois(args.city)
    if args.limit:
        pois = pois[: args.limit]
    provider = get_llm_provider()
    model = getattr(provider, "model", "?")
    logger.info("%s: %d건 태깅 시작 (모델 %s)", args.city, len(pois), model)

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(lambda poi: tag_one(poi, provider), pois))

    tagged = [item for item in results if item is not None]
    skipped = len(pois) - len(tagged)
    out_path = POI_ROOT / args.city / "tagged.json"
    out_path.write_text(json.dumps(tagged, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("완료: %d건 저장, %d건 건너뜀 → %s", len(tagged), skipped, out_path)


def load_pois(city: str) -> list[dict]:
    """수집 산출물을 읽는다. 없으면 수집 명령을 알려주고 종료한다."""
    path = POI_ROOT / city / f"pois_{city}.json"
    if not path.exists():
        raise SystemExit(f"{path} 가 없습니다. 먼저 collect_pois.py --city {city} 를 실행하세요.")
    return json.loads(path.read_text(encoding="utf-8"))


def tag_one(poi: dict, provider: LLMProvider) -> dict | None:
    """POI 1건을 태깅한다. 실패하면 로그를 남기고 None(PS-5)."""
    system, prompt = render_prompt(
        "tag_poi",
        poi_id=poi["poi_id"],
        name=_escape(poi["name"]),
        category=poi["category"],
        address=_escape(poi.get("address") or ""),
        avg_duration_min=int(poi.get("avg_duration_min") or 60),
        open_hours=_escape(poi.get("open_hours") or ""),
    )
    try:
        data = complete_json(provider, prompt, system=system, max_tokens=600)
        return to_record(poi, data)
    except (LLMResponseError, LLMUnavailableError, ValueError) as exc:
        logger.warning("건너뜀 %s (%s): %s", poi["name"], poi["poi_id"], exc)
        return None


def to_record(poi: dict, data: dict) -> dict:
    """LLM 응답을 검증해 저장 레코드로 만든다. 계약 위반이면 ValueError."""
    features = _unit_vector(data.get("axis_features"), "axis_features")
    confidence = _unit_vector(data.get("confidence") or [0.5] * AXIS_COUNT, "confidence")
    return {
        "poi_id": poi["poi_id"],
        "name": poi["name"],
        "category": poi["category"],
        "lat": poi["lat"],
        "lng": poi["lng"],
        "address": poi.get("address") or "",
        "avg_duration_min": int(poi.get("avg_duration_min") or 60),
        "open_hours": poi.get("open_hours"),
        "axis_features": features,
        "confidence": confidence,
        "reasons": [str(reason) for reason in data.get("reasons") or []][:5],
    }


def _unit_vector(values: object, label: str) -> list[float]:
    """길이 5, 각 0.0~1.0 인지 검증한다."""
    if not isinstance(values, list) or len(values) != AXIS_COUNT:
        raise ValueError(f"{label} 길이가 {AXIS_COUNT} 가 아닙니다: {values!r}")
    try:
        numbers = [float(value) for value in values]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} 에 숫자가 아닌 값: {values!r}") from exc
    if any(number < 0 or number > 1 for number in numbers):
        raise ValueError(f"{label} 값이 0~1 범위를 벗어남: {numbers}")
    return [round(number, 2) for number in numbers]


def _escape(text: str) -> str:
    """프롬프트의 JSON 문자열 안에 들어가므로 따옴표·역슬래시를 이스케이프한다."""
    return json.dumps(text, ensure_ascii=False)[1:-1]


if __name__ == "__main__":
    try:
        main()
    except LLMUnavailableError as exc:
        raise SystemExit(f"LLM 을 쓸 수 없습니다: {exc}") from exc
