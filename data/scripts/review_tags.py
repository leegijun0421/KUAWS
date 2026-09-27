"""[W1 게이트] 태깅 결과 수동 검수 30건 — 검수표 생성과 통과 판정.

실행 방법 (프로젝트 루트에서)
    python data/scripts/review_tags.py sheet             # 두 도시에서 30건 층화 추출 → 검수표
    python data/scripts/review_tags.py score             # 검수자가 채운 판정 집계 → 게이트 판정

산출물 (전부 data/processed/ — .gitignore 대상. POI 이름은 Google 콘텐츠라 커밋하지 않는다)
    data/processed/pois/review_30.md        사람이 읽는 검수표
    data/processed/pois/review_30.json      판정 입력 파일 (verdict 칸을 채운다)

판정 규칙
    각 POI 의 5축 값을 보고 "납득(ok) / 한 축 어긋남(minor) / 틀림(fail)" 중 하나를 적는다.
    통과 기준: ok 비율 ≥ 80% 이고 fail ≤ 2건. 미달이면 프롬프트를 고쳐 전량 재실행한다
    ("그럭저럭이면 프롬프트 수정 후 재실행" — Notion 게이트 태스크 메모).
"""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from pathlib import Path

POI_ROOT = Path(__file__).resolve().parents[2] / "data" / "processed" / "pois"
SHEET_MD = POI_ROOT / "review_30.md"
SHEET_JSON = POI_ROOT / "review_30.json"

CITIES = ("paris", "taipei")
CATEGORIES = ("cafe", "restaurant", "culture", "nature", "attraction")
PER_CITY_CATEGORY = 3  # 2도시 × 5카테고리 × 3 = 30건
SEED = 20260912  # 게이트 날짜. 누가 돌려도 같은 30건이 뽑힌다.

PASS_OK_RATIO = 0.8
PASS_MAX_FAIL = 2
AXES = ("activity", "crowd", "nature←→urban", "food", "pace")


def build_sheet() -> None:
    """두 도시 tagged.json 에서 카테고리별로 고르게 30건을 뽑아 검수표를 만든다."""
    rng = random.Random(SEED)
    rows: list[dict] = []
    for city in CITIES:
        tagged = json.loads((POI_ROOT / city / "tagged.json").read_text(encoding="utf-8"))
        for category in CATEGORIES:
            pool = [item for item in tagged if item["category"] == category]
            for item in rng.sample(pool, min(PER_CITY_CATEGORY, len(pool))):
                rows.append({"city": city, **item, "verdict": "", "note": ""})
    SHEET_JSON.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    SHEET_MD.write_text(_markdown(rows), encoding="utf-8")
    print(f"검수표 {len(rows)}건 → {SHEET_MD}")


def score_sheet() -> None:
    """채워진 판정을 집계하고 게이트 통과 여부를 출력한다."""
    rows = json.loads(SHEET_JSON.read_text(encoding="utf-8"))
    counts = Counter(row.get("verdict") or "미판정" for row in rows)
    ok_ratio = counts["ok"] / len(rows)
    passed = ok_ratio >= PASS_OK_RATIO and counts["fail"] <= PASS_MAX_FAIL and not counts["미판정"]
    print(f"검수 {len(rows)}건: {dict(counts)} · 납득 비율 {ok_ratio:.0%}")
    print("게이트 통과" if passed else "게이트 미통과 — 프롬프트 수정 후 재실행")
    for row in rows:
        if row.get("verdict") in ("minor", "fail"):
            label = f"{row['city']}/{row['category']} {row['poi_id']}"
            print(f"  [{row['verdict']}] {label}: {row['note']}")


def _markdown(rows: list[dict]) -> str:
    """검수표 본문."""
    header = "| # | 도시 | 카테고리 | 이름 | " + " | ".join(AXES) + " | 근거 | 판정 |\n"
    header += "|---" * (len(AXES) + 6) + "|\n"
    lines = []
    for index, row in enumerate(rows, 1):
        values = " | ".join(f"{value:.2f}" for value in row["axis_features"])
        reasons = "<br>".join(row.get("reasons") or [])
        lines.append(
            f"| {index} | {row['city']} | {row['category']} | {row['name']} | {values} "
            f"| {reasons} | |"
        )
    return "# 태깅 수동 검수 30건\n\n" + header + "\n".join(lines) + "\n"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="태깅 수동 검수 30건")
    parser.add_argument("command", choices=["sheet", "score"])
    command = parser.parse_args().command
    build_sheet() if command == "sheet" else score_sheet()
