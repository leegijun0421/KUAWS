"""[W1] 대화 → 선호 벡터 추출 정답지 대조 — 가짜 카톡 대화 5종 × 정답지.

실행 (PowerShell, 프로젝트 루트 — Claude 실호출. 서버는 필요 없다)
    python scripts/eval_extraction.py
    python scripts/eval_extraction.py --rules     # LLM 없이 규칙 폴백만 평가(비교용)

결과: 표를 출력하고 docs/EXTRACTION_EVAL.md 에 저장한다(커밋 대상 — 가상 대화라 개인정보 없음).

통과 기준(Notion "[W1] 대화 텍스트 → 선호 벡터 추출 파이프라인")
- 선호 벡터 방향이 5종 중 4종 이상 일치 — 대화별로 정답이 있는 축의 70% 이상 방향 일치
  (정답이 0.5±0.15 인 '중간' 축은 예측이 0.5±0.25 안이면 일치)
- 하드 제약 5종 전부 누락 없음 — 알레르기 키워드와 시간 제약
- 05(정보 부족)에서 신뢰도가 낮게 나옴 — 축의 80% 이상이 신뢰도 0.6 미만
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

from backend.intake.chat_parser import parse_chat  # noqa: E402
from backend.intake.extractor import extract_profiles, extract_with_rules  # noqa: E402
from backend.intake.profile import merge_constraints  # noqa: E402
from shared.types.models import HardConstraints  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "conversations"
REPORT = ROOT / "docs" / "EXTRACTION_EVAL.md"
CITY_LABEL = {"paris": "파리(프랑스)", "taipei": "타이베이(대만)"}
NEUTRAL, NEUTRAL_TOLERANCE, DIRECTION_PASS = 0.15, 0.25, 0.7


def main() -> None:
    """5종을 평가하고 표를 저장한다."""
    parser = argparse.ArgumentParser(description="추출 정답지 대조")
    parser.add_argument("--rules", action="store_true", help="LLM 대신 규칙 폴백만 평가")
    args = parser.parse_args()
    rows = [evaluate(path, args.rules) for path in sorted(FIXTURES.glob("*_expected.json"))]
    report = render(rows, "규칙 폴백" if args.rules else "Claude 추출")
    if not args.rules:
        REPORT.write_text(report, encoding="utf-8")
    print(report)


def evaluate(expected_path: Path, rules_only: bool) -> dict:
    """대화 1종 평가."""
    expected = json.loads(expected_path.read_text(encoding="utf-8"))
    name = expected_path.name.replace("_expected.json", "")
    speakers = parse_chat((FIXTURES / f"{name}.txt").read_text(encoding="utf-8"))
    if rules_only:
        # extract_profiles 의 폴백 경로와 같은 함수를 LLM 없이 직접 부른다.
        result = extract_with_rules(speakers)
    else:
        result = extract_profiles(speakers, CITY_LABEL[expected["city"]])
    members = {m.name: m.axes for m in result.members}
    constraints = merge_constraints([m.constraints for m in result.members])
    method, earliest = result.method, result.earliest_start
    agree, labeled, low_conf, total = 0, 0, 0, 0
    for member in expected["members"]:
        predicted = {axis.axis: axis for axis in members.get(member["name"], [])}
        for axis, target in member["axes"].items():
            got = predicted.get(axis)
            total += 1
            low_conf += int(got is None or got.confidence < 0.6)
            if target is None:
                continue
            labeled += 1
            agree += int(got is not None and _same_direction(target, got.value))
    return {
        "name": name, "type": expected["type"], "method": method,
        "direction": agree / labeled if labeled else None, "labeled": labeled,
        "low_conf": low_conf / total,
        "constraints_ok": _constraints_ok(expected, constraints, earliest),
        "speakers": len(speakers) == len(expected["members"]),
    }


def _same_direction(target: float, value: float) -> bool:
    """정답과 예측의 방향이 같은가(중간값은 중간으로)."""
    if abs(target - 0.5) <= NEUTRAL:
        return abs(value - 0.5) <= NEUTRAL_TOLERANCE
    return (target > 0.5) == (value > 0.5)


def _constraints_ok(expected: dict, constraints: HardConstraints, earliest: str | None) -> bool:
    """하드 제약 누락이 없는가(재현율)."""
    wanted = expected["constraints"]
    keywords = {k.lower() for k in constraints.avoid_keywords}
    if wanted["avoid_keywords_any"] and not keywords & set(wanted["avoid_keywords_any"]):
        return False
    if wanted["earliest_start"] and earliest != wanted["earliest_start"]:
        return False
    return set(wanted["exclude_categories"]) <= set(constraints.exclude_categories)


def render(rows: list[dict], label: str) -> str:
    """마크다운 보고서."""
    passed_direction = sum(
        1 for r in rows if r["type"] != "vague" and (r["direction"] or 0) >= DIRECTION_PASS
    )
    vague_ok = all(r["low_conf"] >= 0.8 for r in rows if r["type"] == "vague")
    constraints_ok = all(r["constraints_ok"] for r in rows)
    lines = [
        f"# 대화 → 선호 벡터 추출 정답지 대조 ({label})", "",
        "| 대화 | 성격 | 방식 | 화자 분리 | 방향 일치 | 저신뢰 축 비율 | 하드 제약 |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        direction = "-" if r["direction"] is None else f"{r['direction']:.0%} ({r['labeled']}축)"
        lines.append(
            f"| {r['name']} | {r['type']} | {r['method']} | {'✅' if r['speakers'] else '❌'} "
            f"| {direction} | {r['low_conf']:.0%} | {'✅' if r['constraints_ok'] else '❌'} |"
        )
    lines += [
        "",
        f"- 방향 일치 대화: {passed_direction + int(vague_ok)}/5 "
        f"(축 {DIRECTION_PASS:.0%} 이상 일치, 05 는 저신뢰가 정답) "
        f"→ {'통과' if passed_direction + int(vague_ok) >= 4 else '미통과'} (기준 4/5)",
        f"- 하드 제약 누락 없음: {'통과' if constraints_ok else '미통과'}",
        f"- 정보 부족 대화 저신뢰: {'통과' if vague_ok else '미통과'}",
    ]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
