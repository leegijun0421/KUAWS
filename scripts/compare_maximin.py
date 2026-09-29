"""[W1] maximin vs 평균 — 같은 그룹·같은 POI 로 상위 10곳을 나란히 비교한다.

의견 충돌 대화(tests/fixtures/conversations/02_conflict_expected.json)의 **정답지 프로필**을 그대로
써서 LLM 없이 재현 가능하게 했다. POI 는 태깅된 수집본(없으면 예시 데이터)을 쓴다.

실행 (프로젝트 루트)
    python scripts/compare_maximin.py                  # 파리
    python scripts/compare_maximin.py --names          # 장소 이름까지(내부 공유용 — 커밋 금지)

기본 출력은 장소 이름 대신 유형만 보여준다(Google 콘텐츠를 리포 문서에 남기지 않기 위해).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.common.poi_data import load_city  # noqa: E402
from backend.scoring.matcher import average_rank, score_pois  # noqa: E402
from shared.types.models import AxisValue, PoiScore, PreferenceProfile  # noqa: E402

KEY = ROOT / "tests" / "fixtures" / "conversations" / "02_conflict_expected.json"
LABEL = {
    "cafe": "카페",
    "restaurant": "식당",
    "culture": "미술관·전시",
    "nature": "공원·자연",
    "attraction": "명소",
}


def main() -> None:
    """두 순위를 표로 출력한다."""
    parser = argparse.ArgumentParser(description="maximin vs 평균 상위 10 비교")
    parser.add_argument("--city", default=None)
    parser.add_argument("--names", action="store_true")
    args = parser.parse_args()
    key = json.loads(KEY.read_text(encoding="utf-8"))
    members = [_profile(m) for m in key["members"]]
    data = load_city(args.city or key["city"])
    by_id = data.by_id()
    maximin = score_pois(data.pois, members)
    average = average_rank(maximin)
    names = [m.member_name for m in members]

    def label(score: PoiScore) -> str:
        poi = by_id[score.poi_id]
        kind = LABEL.get(poi.category, poi.category)
        return f"{poi.name} ({kind})" if args.names else kind

    print(f"# maximin vs 평균 — {data.city} ({data.source}), 그룹: {', '.join(names)}\n")
    print(
        "| 순위 | 평균 방식 | "
        + " / ".join(names)
        + " | 최저 | maximin | "
        + " / ".join(names)
        + " | 최저 |"
    )
    print("|---" * 7 + "|")
    for rank, (avg, mm) in enumerate(zip(average[:10], maximin[:10], strict=True), 1):
        print(
            f"| {rank} | {label(avg)} | {_fits(avg)} | {_worst(avg)} "
            f"| {label(mm)} | {_fits(mm)} | {_worst(mm)} |"
        )
    overlap = len({s.poi_id for s in average[:10]} & {s.poi_id for s in maximin[:10]})
    print(
        f"\n상위 10 겹침: {overlap}/10 · 평균 방식 상위 10의 최저 만족도 평균 "
        f"{sum(min(f.fit for f in s.per_member_fit) for s in average[:10]) / 10:.0%} → "
        f"maximin {sum(s.fit_score for s in maximin[:10]) / 10:.0%}"
    )


def _profile(member: dict) -> PreferenceProfile:
    """정답지 → 프로필. 정답이 null 인 축은 중립·저신뢰."""
    axes = [
        AxisValue(
            axis=axis,
            value=0.5 if value is None else value,
            confidence=0.2 if value is None else 0.9,
        )
        for axis, value in member["axes"].items()
    ]
    return PreferenceProfile(
        member_id=member["name"], member_name=member["name"], axes=axes, raw_text="", updated_at=""
    )


def _fits(score: PoiScore) -> str:
    return " / ".join(f"{f.fit:.0%}" for f in score.per_member_fit)


def _worst(score: PoiScore) -> str:
    return f"{min(f.fit for f in score.per_member_fit):.0%}"


if __name__ == "__main__":
    main()
