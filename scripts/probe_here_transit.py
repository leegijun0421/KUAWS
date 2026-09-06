"""일본 대중교통 대안 판정용 프로브 — HERE Public Transit API v8.

왜 필요한가
    Google Routes API 는 일본(도쿄·오사카) TRANSIT 경로를 반환하지 않는다
    (2026-09-06 확인, docs/DECISIONS.md). 우회 방법이 없으므로 일본을 살리려면
    다른 라우팅 제공자를 붙여야 한다. 이 스크립트는 **붙이기 전에 30분 안에**
    "HERE 가 일본 대중교통을 주는가"만 판정한다.

사용법
    1. https://platform.here.com 에서 무료 계정 생성 → API 키 발급
    2. .env 에 HERE_API_KEY= 추가 (커밋 금지)
    3. python -u scripts/probe_here_transit.py

판정 기준 (통과해야 어댑터를 붙일 가치가 있다)
    - 도쿄 3구간 모두 경로가 나오는가
    - 편성 출발·도착 시각이 오는가        ← C1 막차 경고 / W3 위험도의 입력
    - 운영기관 이름·URL 이 오는가          ← 약관 표기 필수
    - 오사카도 나오는가                    ← 도쿄 한정이면 의미가 작다

⚠️ 응답을 파일로 저장하지 말 것. 제공자마다 저장 제한이 다르므로 보수적으로 간다.
"""

from __future__ import annotations

import os
import sys

import httpx

try:
    from dotenv import load_dotenv

    load_dotenv(".env")
except ImportError:
    pass

ENDPOINT = "https://transit.router.hereapi.com/v8/routes"
API_KEY_ENV = "HERE_API_KEY"

#: (도시, 라벨, 출발 lat,lng, 도착 lat,lng) — Google 로 확인한 것과 같은 구간을 쓴다.
SEGMENTS: list[tuple[str, str, tuple[float, float], tuple[float, float]]] = [
    ("tokyo", "신주쿠역 → 마이하마역", (35.6896, 139.7006), (35.6329, 139.8804)),
    ("tokyo", "시부야역 → 아사쿠사", (35.6580, 139.7016), (35.7148, 139.7967)),
    ("tokyo", "우에노역 → 아키하바라역", (35.7141, 139.7774), (35.6984, 139.7731)),
    ("osaka", "오사카역 → 난바", (34.7025, 135.4959), (34.6659, 135.5011)),
    ("paris", "샤틀레 → 몽마르트 (대조군)", (48.8586, 2.3470), (48.8867, 2.3431)),
]


def fetch(origin: tuple[float, float], destination: tuple[float, float], key: str) -> dict:
    """HERE Public Transit v8 에 경로를 요청한다."""
    params = {
        "origin": f"{origin[0]},{origin[1]}",
        "destination": f"{destination[0]},{destination[1]}",
        "return": "travelSummary,intermediate,fares",
        "lang": "ko",
        "apiKey": key,
    }
    resp = httpx.get(ENDPOINT, params=params, timeout=20.0)
    if resp.status_code != 200:
        return {"_error": f"HTTP {resp.status_code} · {resp.text[:200]}"}
    return resp.json()


def summarize(data: dict) -> str:
    """판정에 필요한 것만 한 줄로 요약한다."""
    if "_error" in data:
        return data["_error"]
    routes = data.get("routes", [])
    if not routes:
        return "routes 0개  ← 경로 없음"

    sections = routes[0].get("sections", [])
    transit = [s for s in sections if s.get("type") == "transit"]
    if not transit:
        return f"routes {len(routes)}개 · 하지만 transit 구간 없음(도보만)"

    first = transit[0]
    dep = first.get("departure", {}).get("time")
    arr = first.get("arrival", {}).get("time")
    transport = first.get("transport", {})
    agency = first.get("agency", {})
    return (
        f"routes {len(routes)}개 · transit {len(transit)}구간 · "
        f"편성시각 {'O' if dep and arr else 'X'} ({dep}) · "
        f"노선 {transport.get('name') or transport.get('mode')} · "
        f"운영기관 {agency.get('name')} / {agency.get('website')}"
    )


def main() -> None:
    key = os.environ.get(API_KEY_ENV)
    if not key:
        sys.exit(f"환경변수 {API_KEY_ENV} 가 없다. .env 에 HERE 무료 키를 넣을 것.")

    print("HERE Public Transit API v8 — 일본 대중교통 판정\n" + "-" * 78)
    for city, label, origin, destination in SEGMENTS:
        try:
            data = fetch(origin, destination, key)
        except httpx.HTTPError as exc:
            print(f"[{city:<6}] {label:<26} 네트워크 오류: {exc}")
            continue
        print(f"[{city:<6}] {label:<26} {summarize(data)}")
    print("-" * 78)
    print("도쿄 3구간 + 오사카가 전부 나오고 편성시각·운영기관이 오면 어댑터를 붙일 가치가 있다.")
    print("⚠️ 이 출력을 파일로 저장하거나 리포에 커밋하지 말 것.")


if __name__ == "__main__":
    main()
