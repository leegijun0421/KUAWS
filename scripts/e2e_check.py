"""[W2] end-to-end 통합 검증 — 가짜 카톡 대화 5종을 실제 API 로 끝까지 돌린다.

    대화 붙여넣기 → /api/intake/chat (Claude 실호출)
               → /api/planner/plan (Google Routes 실호출)
               → /api/share 생성 → /api/share/{id} 열람(경로 재계산)

각 단계 소요 시간·경로 호출 수·만족도·약관 표기 필드 존재 여부를 표로 만든다.
결과(`Claude outputs/e2e_report.md`)는 PoC 문서의 실측 절과 Notion 통합 태스크에 옮긴다.
**경로 응답 자체는 저장하지 않는다**(Google 약관) — 수치 요약만 남긴다.

실행 (PowerShell, 프로젝트 루트, 백엔드가 :8000 에 떠 있어야 함)
    python scripts/e2e_check.py
    python scripts/e2e_check.py --only 01 --days 1
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import date, timedelta
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")  # Windows cp949 콘솔 대비

import httpx  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CHATS = ROOT / "tests" / "fixtures" / "conversations"
REPORT = ROOT / "Claude outputs" / "e2e_report.md"
API = "http://127.0.0.1:8000"
CITY_BY_PREFIX = {"01": "paris", "02": "paris", "03": "paris", "04": "taipei", "05": "paris"}


def main() -> None:
    """대화 5종(또는 선택한 것)을 끝까지 돌리고 표를 출력·저장한다."""
    parser = argparse.ArgumentParser(description="end-to-end 통합 검증")
    parser.add_argument("--only", help="대화 파일 앞 두 자리(01~05)")
    parser.add_argument("--days", type=int, default=2)
    parser.add_argument("--repeat", type=int, default=1, help="대화마다 반복 횟수(편차 확인)")
    args = parser.parse_args()
    start = (date.today() + timedelta(days=18)).isoformat()
    rows = []
    with httpx.Client(base_url=API, timeout=180.0) as client:
        client.get("/health").raise_for_status()
        for path in sorted(CHATS.glob("*.txt")):
            if args.only and not path.name.startswith(args.only):
                continue
            for attempt in range(args.repeat):
                row = run_one(client, path, args.days, start)
                row["chat"] += f" #{attempt + 1}" if args.repeat > 1 else ""
                rows.append(row)
    report = render(rows, start)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(report, encoding="utf-8")
    print(report)
    print(f"저장 → {REPORT}")


def run_one(client: httpx.Client, path: Path, days: int, start: str) -> dict:
    """대화 1종을 끝까지 돌린다. 실패해도 다음 대화로 넘어가도록 사유를 기록한다."""
    city = CITY_BY_PREFIX[path.name[:2]]
    row: dict = {"chat": path.stem, "city": city, "ok": False}
    try:
        tick = time.perf_counter()
        intake = post(client, f"/api/intake/chat?city={city}",
                      {"chatText": path.read_text(encoding="utf-8")})
        row["intake_s"] = time.perf_counter() - tick
        row["members"] = len(intake["members"])
        row["followups"] = sum(len(m["followUps"]) for m in intake["members"])
        row["must"] = ", ".join(intake["mustVisit"]) or "-"
        request = {
            "city": city, "days": days, "startDate": start,
            "members": [m["profile"] for m in intake["members"]],
            "constraints": intake["constraints"], "mustVisit": intake["mustVisit"],
        }
        tick = time.perf_counter()
        plan = post(client, "/api/planner/plan", request)
        row["plan_s"] = time.perf_counter() - tick
        summarize(plan, row)
        orders = [[s["poi"]["poiId"] for s in d["stops"]] for d in plan["days"]]
        row["stop_ids"] = {poi for day in orders for poi in day}
        link = post(client, "/api/share", {"request": request, "dayOrders": orders})
        tick = time.perf_counter()
        shared = client.get(f"/api/share/{link['planId']}").json()
        row["share_s"] = time.perf_counter() - tick
        replayed = [[s["poi"]["poiId"] for s in d["stops"]] for d in shared["days"]]
        row["share_same"] = orders == replayed
        row["ok"] = row["stops"] > 0 and row["share_same"]
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        row["error"] = str(exc)[:200]
    print(f"[{'OK ' if row['ok'] else 'ERR'}] {path.stem}: {row.get('error', '')}")
    return row


def summarize(plan: dict, row: dict) -> None:
    """일정 응답에서 검증 지표를 뽑는다."""
    stops = [s for d in plan["days"] for s in d["stops"]]
    segments = [g for d in plan["days"] for g in d["segments"]]
    transit_legs = [leg for g in segments for leg in g["legs"] if leg["mode"] != "walk"]
    row.update(
        source=plan.get("dataSource"),
        stops=len(stops),
        meals=sum(1 for s in stops if s["poi"]["category"] == "restaurant"),
        min_sat=plan["minMemberSatisfaction"],
        max_risk=max((s["score"]["failureProbability"] for s in stops), default=0),
        routing=plan["stats"]["routingCalls"],
        provider=plan["stats"]["providerCalls"],
        timed=sum(1 for leg in transit_legs if leg.get("departAt")),
        transit=len(transit_legs),
        operators=sum(1 for g in segments if g["operators"]),
        segments=len(segments),
        scenic=sum(1 for g in segments if g.get("scenic")),
        warnings=len(plan["warnings"]),
        excluded="; ".join(plan["excludedNotes"]) or "-",
    )


def post(client: httpx.Client, url: str, body: dict) -> dict:
    """POST 후 JSON. 4xx/5xx 는 본문 detail 과 함께 예외."""
    response = client.post(url, json=body)
    if response.status_code >= 400:
        raise ValueError(f"{url} → {response.status_code} {response.text[:150]}")
    return response.json()


def render(rows: list[dict], start: str) -> str:
    """마크다운 표."""
    head = (
        f"# end-to-end 통합 검증 결과\n\n출발일 {start} · 실행 {date.today()} · "
        f"성공 {sum(r['ok'] for r in rows)}/{len(rows)}\n\n"
        "| 대화 | 도시 | 인원 | 후속질문 | 취향추출(s) | 일정생성(s) | 공유열람(s) | 스톱 | 식사 "
        "| 최저만족 | 최대위험 | 경로호출(외부) | 편성시각 leg | 운영기관 구간 | 경치대안 "
        "| 경고 | 공유 일치 |\n"
        + "|---" * 17 + "|\n"
    )
    lines = []
    for r in rows:
        if "error" in r:
            lines.append(f"| {r['chat']} | {r['city']} | 오류: {r['error']} |" + " |" * 14)
            continue
        lines.append(
            f"| {r['chat']} | {r['city']} | {r['members']} | {r['followups']} "
            f"| {r['intake_s']:.1f} "
            f"| {r['plan_s']:.1f} | {r['share_s']:.1f} | {r['stops']} | {r['meals']} "
            f"| {r['min_sat']:.0%} | {r['max_risk']:.0%} | {r['routing']}({r['provider']}) "
            f"| {r['timed']}/{r['transit']} | {r['operators']}/{r['segments']} | {r['scenic']} "
            f"| {r['warnings']} | {'✅' if r['share_same'] else '❌'} |"
        )
    notes = [f"- {r['chat']}: must_visit={r.get('must', '-')} · 제외={r.get('excluded', '-')} "
             f"· 데이터={r.get('source', '-')}" for r in rows if "error" not in r]
    return head + "\n".join(lines) + "\n\n" + "\n".join(notes) + "\n" + _variance(rows)


def _variance(rows: list[dict]) -> str:
    """같은 대화를 여러 번 돌렸을 때 스톱 구성이 얼마나 같은지(리허설 편차)."""
    groups: dict[str, list[set]] = {}
    for row in rows:
        if "stop_ids" in row:
            groups.setdefault(row["chat"].split(" #")[0], []).append(row["stop_ids"])
    lines = []
    for chat, runs in groups.items():
        if len(runs) < 2:
            continue
        common = set.intersection(*runs)
        union = set.union(*runs)
        lines.append(f"- {chat}: {len(runs)}회 실행, 스톱 구성 일치 {len(common)}/{len(union)}")
    return ("\n## 반복 실행 편차\n\n" + "\n".join(lines) + "\n") if lines else ""


if __name__ == "__main__":
    main()
