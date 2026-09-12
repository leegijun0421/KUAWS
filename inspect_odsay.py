"""ODsay 대중교통 길찾기 응답의 필드 체크리스트를 기계적으로 검증한다.

사용법:
    python inspect_odsay.py docs/odsay_sample_response.json

출력:
    1) 응답 전체의 키 구조(스키마) — 실제로 어떤 필드가 오는지 한눈에 확인
    2) 체크리스트 항목별 있음/없음 + 실제 필드명 + 샘플값 (마크다운 표)
"""

from __future__ import annotations

import json
import sys
# Windows 기본 출력 인코딩(cp949)은 이모지를 처리하지 못하므로 UTF-8로 고정한다.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# 체크리스트 정의
#   (항목명, 탐색을 시작할 노드, 찾을 후보 필드명들)
#   후보를 여러 개 두는 이유: ODsay가 노드마다 다른 이름을 쓰기 때문
#   (예: 소요시간이 info에서는 totalTime, subPath에서는 sectionTime)
# ---------------------------------------------------------------------------
CHECKLIST: list[tuple[str, str, list[str]]] = [
    ("총 소요시간",            "info",    ["totalTime"]),
    ("총 요금",               "info",    ["payment"]),
    ("환승 횟수",              "info",    ["busTransitCount", "subwayTransitCount"]),
    ("구간별 교통수단 종류",     "subPath", ["trafficType"]),
    ("구간별 승차 정류장·역",    "subPath", ["startName", "startID"]),
    ("구간별 하차 정류장·역",    "subPath", ["endName", "endID"]),
    ("구간별 소요시간",         "subPath", ["sectionTime"]),
    ("배차간격 (구간별)",       "subPath", ["intervalTime"]),
    ("배차간격 (경로 합계)",     "info",    ["totalIntervalTime", "checkIntervalTime"]),
    ("도보 거리",              "info",    ["totalWalk"]),
    ("도보 시간",              "info",    ["totalWalkTime"]),
]

# trafficType 코드 정의 (ODsay 공통 코드)
TRAFFIC_TYPE = {1: "지하철", 2: "버스", 3: "도보"}


def walk_schema(node: Any, prefix: str = "", depth: int = 0, max_depth: int = 4) -> list[str]:
    """중첩 dict/list를 재귀 순회하며 'a.b[].c' 형태의 키 경로 목록을 만든다.

    리스트는 모든 원소를 순회한 뒤 합집합을 취한다.
    subPath처럼 원소마다 스키마가 다른 경우(도보 구간에는 lane/startName이 없음)
    첫 원소만 보면 필드를 통째로 놓치기 때문이다.
    """
    if depth > max_depth:
        return []

    paths: list[str] = []
    seen: set[str] = set()

    def add(items: list[str]) -> None:
        for item in items:
            if item not in seen:
                seen.add(item)
                paths.append(item)

    if isinstance(node, dict):
        for key, value in node.items():
            path = f"{prefix}.{key}" if prefix else key
            add([path])
            add(walk_schema(value, path, depth + 1, max_depth))
    elif isinstance(node, list):
        for element in node:
            add(walk_schema(element, f"{prefix}[]", depth, max_depth))
    return paths


def collect_nodes(path_obj: dict, node_kind: str) -> list[dict]:
    """경로 하나에서 검사 대상 노드(info 또는 subPath 리스트)를 꺼낸다."""
    if node_kind == "info":
        info = path_obj.get("info")
        return [info] if isinstance(info, dict) else []
    return [s for s in path_obj.get("subPath", []) if isinstance(s, dict)]


def find_field(nodes: list[dict], candidates: list[str]) -> tuple[str | None, Any]:
    """후보 필드명 중 실제로 존재하는 첫 번째 것과 그 샘플값을 반환한다."""
    for name in candidates:
        for node in nodes:
            if name in node:
                return name, node[name]
    return None, None


def main(json_path: str) -> int:
    raw = Path(json_path).read_text(encoding="utf-8")
    data = json.loads(raw)

    # ODsay는 실패 시 result 대신 error 노드를 반환한다.
    if "error" in data:
        print(f"[오류] API가 에러를 반환했습니다: {data['error']}", file=sys.stderr)
        return 1

    result = data["result"]
    paths = result.get("path", [])
    if not paths:
        print("[오류] result.path 가 비어 있습니다.", file=sys.stderr)
        return 1

    # --- 1) 스키마 덤프 -----------------------------------------------------
    print("## 1. 응답 키 구조\n")
    print("```")
    for p in walk_schema(result):
        print(p)
    print("```\n")

    # --- 2) 경로 요약 -------------------------------------------------------
    print(f"## 2. 경로 요약 (총 {len(paths)}개)\n")
    print("| # | pathType | 총 시간(분) | 요금(원) | 구간 수 |")
    print("|---|---------|-----------|---------|--------|")
    for i, p in enumerate(paths):
        info = p.get("info", {})
        print(
            f"| {i} | {p.get('pathType')} | {info.get('totalTime')} | "
            f"{info.get('payment')} | {len(p.get('subPath', []))} |"
        )
    print()

    # --- 3) 체크리스트 검증 -------------------------------------------------
    # 모든 경로의 모든 노드를 모아서 검사한다.
    # 필드가 특정 교통수단(예: 버스 구간)에만 나타날 수 있기 때문.
    print("## 3. 필드 체크리스트\n")
    print("| 항목 | 결과 | 실제 필드명 | 샘플값 |")
    print("|------|------|-----------|--------|")

    for label, node_kind, candidates in CHECKLIST:
        nodes: list[dict] = []
        for p in paths:
            nodes.extend(collect_nodes(p, node_kind))

        name, sample = find_field(nodes, candidates)
        if name is None:
            tried = " / ".join(candidates)
            print(f"| {label} | ❌ 없음 | (탐색: {tried}) | - |")
        else:
            location = f"`path[].{node_kind}" + ("[]" if node_kind == "subPath" else "") + f".{name}`"
            print(f"| {label} | ✅ 있음 | {location} | `{sample}` |")
    print()

    # --- 4) 구간 상세 (첫 번째 경로) ----------------------------------------
    print("## 4. 첫 번째 경로의 구간 상세\n")
    print("| idx | 수단 | 노선 | 승차 | 하차 | 소요(분) | 배차간격(분) |")
    print("|-----|------|------|------|------|---------|------------|")
    for idx, sp in enumerate(paths[0].get("subPath", [])):
        ttype = TRAFFIC_TYPE.get(sp.get("trafficType"), "?")

        # lane은 버스면 list, 지하철이면 dict, 도보면 아예 없다.
        lane = sp.get("lane")
        if isinstance(lane, list) and lane:
            lane_name = lane[0].get("busNo") or lane[0].get("name", "-")
        elif isinstance(lane, dict):
            lane_name = lane.get("name") or lane.get("busNo", "-")
        else:
            lane_name = "-"

        print(
            f"| {idx} | {ttype} | {lane_name} | {sp.get('startName', '-')} | "
            f"{sp.get('endName', '-')} | {sp.get('sectionTime', '-')} | "
            f"{sp.get('intervalTime', '없음')} |"
        )
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
