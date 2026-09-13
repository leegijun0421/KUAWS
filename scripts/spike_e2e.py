"""수직 관통 스파이크. 알고리즘 없음. 연결만 증명한다.

하드코딩 취향 3명 → 더미 POI 10개 → 앞에서 3개 선택 → Google Routes **실호출** →
콘솔 출력. 이 중 진짜여야 하는 건 Routes 호출 하나뿐이다.

목적은 기능 구현이 아니라 **외부 의존성이 실제로 연결된다는 증명**이다.
"Routes 가 이 도시에서 이상한 응답을 준다", "키가 팀원 환경에서 안 먹는다",
".env 로딩이 Windows 에서 다르다" 같은 문제를 개학 전에 잡는다.

실행:
    python -u scripts/spike_e2e.py                  # 프로젝트 루트(KUAWS 폴더)에서. 기본 파리
    python -u scripts/spike_e2e.py --city taipei    # 지원 도시 2개째
    python -u scripts/spike_e2e.py --depart 2026-10-20T09:00:00+02:00

⚠️ 응답을 파일로 저장하지 않는다. Google 약관상 응답의 저장·캐싱이 제한된다.
   콘솔 출력까지만 하고, 발견한 사실은 노션 페이지에 텍스트로 적는다.

이 스크립트는 버리지 말 것 — W2 end-to-end 통합(9/20)의 레퍼런스다.
더미를 진짜로 하나씩 교체하면 그게 통합 작업 자체가 된다.
    더미 취향   → 홍성민의 선호 벡터 추출
    더미 POI    → 태깅된 실제 POI
    앞 3개 선택 → 이재용의 maximin 매칭
    (없음)      → W2 C1 스케줄러
    Routes 호출 → 그대로 유지   ← 처음부터 진짜였던 부분
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, tzinfo
from itertools import pairwise
from pathlib import Path

# scripts/ 에서 실행해도 backend 패키지를 찾도록 프로젝트 루트를 경로에 넣는다.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from dotenv import load_dotenv

    load_dotenv()  # 루트 .env 에서 GOOGLE_BACKEND_API_KEY 를 읽는다 (하드코딩 금지)
except ImportError:  # python-dotenv 미설치 환경에서도 환경변수로 동작
    pass

from backend.routing import GeoPoint, RouteProviderError, plan_segment  # noqa: E402
from backend.routing.planner import SegmentRoute  # noqa: E402

# ---------------------------------------------------------------------------
# 더미 입력 — 여기는 전부 가짜여도 된다
# ---------------------------------------------------------------------------

#: 하드코딩 취향 3명. W1 선호 벡터 추출이 끝나면 이 자리가 교체된다.
MEMBERS = [
    {"id": "a", "tags": {"activity": 0.8, "quiet": 0.2, "food_focus": 0.5}},
    {"id": "b", "tags": {"activity": 0.3, "quiet": 0.9, "food_focus": 0.7}},
    {"id": "c", "tags": {"activity": 0.6, "quiet": 0.4, "food_focus": 0.9}},
]

@dataclass(frozen=True)
class City:
    """더미 도시 하나. 실제 POI 는 W1 태깅 결과로 교체된다."""

    label: str
    #: 출발 시각(RFC3339, 현지 시간대). Routes 는 과거 7일 ~ 미래 100일만 받는다.
    #: 범위를 벗어나면 --depart 로 덮어쓸 것.
    depart_at: str
    pois: list[GeoPoint]


#: 지원 도시는 파리(데모)·타이베이(아시아 사례) 2개다. 도쿄·오사카는 Routes API 가
#: TRANSIT 을 반환하지 않아 제외됐다(docs/DECISIONS.md 2026-09-06).
#: 여기에 도쿄 좌표를 넣으면 애초에 경로가 나오지 않는다.
CITIES: dict[str, City] = {
    "paris": City(
        label="파리",
        depart_at="2026-10-15T09:00:00+02:00",
        pois=[
            GeoPoint(poi_id="fr1", name="에펠탑", lat=48.8584, lng=2.2945),
            GeoPoint(poi_id="fr2", name="루브르 박물관", lat=48.8606, lng=2.3376),
            GeoPoint(poi_id="fr3", name="노트르담 대성당", lat=48.8530, lng=2.3499),
            GeoPoint(poi_id="fr4", name="몽마르트(사크레쾨르)", lat=48.8867, lng=2.3431),
            GeoPoint(poi_id="fr5", name="오르세 미술관", lat=48.8600, lng=2.3266),
            GeoPoint(poi_id="fr6", name="개선문", lat=48.8738, lng=2.2950),
            GeoPoint(poi_id="fr7", name="뤽상부르 공원", lat=48.8462, lng=2.3372),
            GeoPoint(poi_id="fr8", name="퐁피두 센터", lat=48.8607, lng=2.3522),
            GeoPoint(poi_id="fr9", name="팔레 가르니에", lat=48.8720, lng=2.3316),
            GeoPoint(poi_id="fr10", name="베르사유 궁전", lat=48.8049, lng=2.1204),
        ],
    ),
    "taipei": City(
        label="타이베이",
        depart_at="2026-10-15T09:00:00+08:00",
        pois=[
            GeoPoint(poi_id="tw1", name="타이베이역", lat=25.0478, lng=121.5170),
            GeoPoint(poi_id="tw2", name="타이베이101", lat=25.0339, lng=121.5645),
            GeoPoint(poi_id="tw3", name="시먼딩", lat=25.0421, lng=121.5075),
            GeoPoint(poi_id="tw4", name="스린 야시장", lat=25.0880, lng=121.5240),
            GeoPoint(poi_id="tw5", name="국립고궁박물원", lat=25.1023, lng=121.5485),
            GeoPoint(poi_id="tw6", name="룽산사", lat=25.0372, lng=121.4997),
            GeoPoint(poi_id="tw7", name="중정기념당", lat=25.0346, lng=121.5219),
            GeoPoint(poi_id="tw8", name="다안 삼림공원", lat=25.0268, lng=121.5359),
            GeoPoint(poi_id="tw9", name="라오허제 야시장", lat=25.0510, lng=121.5773),
            GeoPoint(poi_id="tw10", name="베이터우 온천", lat=25.1365, lng=121.5066),
        ],
    ),
}

#: POI 체류 시간(분). 스케줄러가 생기기 전까지 쓰는 고정값이다.
STAY_MIN = 90

#: 이 시간을 넘으면 W2 통합에서 문제가 된다. 반드시 기록할 것.
SLOW_RESPONSE_SEC = 3.0


def main() -> None:
    """더미 입력으로 경로 조회까지 한 번 관통시키고 결과를 콘솔에 출력한다."""
    parser = argparse.ArgumentParser(description="수직 관통 스파이크 (더미 데이터 e2e 1회)")
    parser.add_argument("--city", default="paris", choices=sorted(CITIES),
                        help="지원 도시. 기본 paris")
    parser.add_argument("--depart", help="RFC3339 출발 시각. 생략하면 도시별 기본값")
    args = parser.parse_args()

    city = CITIES[args.city]
    depart_at = args.depart or city.depart_at
    selected = city.pois[:3]  # 진짜 이렇게 해도 된다. maximin 은 W1 이재용 작업이다.
    print(f"멤버 {len(MEMBERS)}명 / 후보 POI {len(city.pois)}개 → 선택 {len(selected)}개")
    print(f"출발 {depart_at} ({city.label})\n")

    clock = _parse(depart_at)
    tz = clock.tzinfo
    elapsed_log: list[tuple[str, float]] = []

    for here, nxt in pairwise(selected):
        print(f"{clock:%H:%M}  {here.name} ({STAY_MIN}분)")
        clock += timedelta(minutes=STAY_MIN)

        started = time.perf_counter()
        segment = plan_segment(here, nxt, depart_at=_rfc3339(clock))
        elapsed = time.perf_counter() - started
        elapsed_log.append((f"{here.name} → {nxt.name}", elapsed))

        if segment is None:
            print("  ↓ 경로 없음 — 화이트리스트 도시가 맞는지 확인할 것\n")
            continue
        _render(segment, tz)
        clock += timedelta(minutes=segment.primary.total_duration_min)

    print(f"{clock:%H:%M}  {selected[-1].name} ({STAY_MIN}분)")
    _report(elapsed_log)


def _render(segment: SegmentRoute, tz: tzinfo | None) -> None:
    """구간 하나를 일정표 형태로 출력한다."""
    for leg in segment.primary.legs:
        if leg.mode == "walk":
            # 도보는 정류장 이름이 없고 회전 안내만 온다. 합쳐진 총 시간만 보여준다.
            print(f"  ↓ 도보 · {leg.duration_min}분")
            continue
        schedule = _schedule_text(leg.depart_at, leg.arrive_at, tz)
        line = f" {leg.line_name}" if leg.line_name else ""
        print(f"  ↓ {leg.mode}{line} · {leg.from_name} → {leg.to_name} "
              f"· {leg.duration_min}분{schedule}")

    if segment.operators:
        # 약관 표기 의무 — 응답이 준 값을 그대로 쓴다(하드코딩 금지).
        names = " / ".join(f"{op.name}({op.url})" for op in segment.operators)
        print(f"  ↓ 제공: {names}")

    # 통화마다 소수 자릿수가 다르다(EUR 2.05 / TWD 25). :g 로 불필요한 .0 을 지운다.
    fare = f"{segment.primary.total_fare:g}"
    currency = segment.primary.fare_currency or ""
    print(f"  ↓ 합계 {segment.primary.total_duration_min}분 · 환승 "
          f"{segment.transfer_count}회 · 요금 {fare} {currency}".rstrip())
    for advisory in segment.advisories:
        print(f"  ⚠ {advisory.message}")
    print()


def _report(elapsed_log: list[tuple[str, float]]) -> None:
    """응답 시간을 정리해 출력한다. 이 표를 노션 페이지에 그대로 옮긴다."""
    if not elapsed_log:
        return
    print("─" * 60)
    print("응답 시간")
    for label, elapsed in elapsed_log:
        flag = "  ← 3초 초과. W2 통합 전에 확인할 것" if elapsed > SLOW_RESPONSE_SEC else ""
        print(f"  {label}: {elapsed:.2f}s{flag}")
    worst = max(elapsed for _, elapsed in elapsed_log)
    print(f"  최대 {worst:.2f}s / 평균 "
          f"{sum(e for _, e in elapsed_log) / len(elapsed_log):.2f}s")


def _schedule_text(depart_at: str | None, arrive_at: str | None, tz: tzinfo | None) -> str:
    """편성 시각 표기. 없으면 빈 문자열 — 없는 값을 추정으로 채우지 않는다."""
    if not depart_at or not arrive_at:
        return ""
    return f" ({_local(depart_at, tz):%H:%M} 발 → {_local(arrive_at, tz):%H:%M} 착)"


def _local(rfc3339: str, tz: tzinfo | None) -> datetime:
    """RFC3339 문자열(주로 UTC)을 출발 시각과 같은 시간대로 옮긴다.

    Windows 에는 시간대 DB 가 없을 수 있어(zoneinfo 는 tzdata 패키지가 필요하다)
    도시 이름 대신 출발 시각이 가진 UTC 오프셋을 그대로 쓴다. 표시용이라 충분하다.
    """
    return datetime.fromisoformat(rfc3339.replace("Z", "+00:00")).astimezone(tz)


def _parse(rfc3339: str) -> datetime:
    """RFC3339 문자열 → datetime. 형식이 틀리면 즉시 알려준다."""
    try:
        return datetime.fromisoformat(rfc3339.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SystemExit(f"출발 시각 형식이 잘못됐습니다: {rfc3339!r} ({exc})") from exc


def _rfc3339(moment: datetime) -> str:
    """datetime → Routes API 가 받는 RFC3339 문자열."""
    return moment.isoformat(timespec="seconds")


if __name__ == "__main__":
    try:
        main()
    except RouteProviderError as exc:
        # 키 미설정·API 오류는 삼키지 않는다. 원인을 바로 보여주고 끝낸다.
        raise SystemExit(f"경로 조회 실패: {exc}") from exc
