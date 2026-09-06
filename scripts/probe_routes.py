"""
[W0] Google Routes API TRANSIT 응답 필드 확인용 프로브 스크립트

목적
    Routes API v2 computeRoutes 를 TRANSIT 모드로 1회 호출해서,
    노션 체크리스트 13개 항목이 응답에 실제로 오는지 / 필드 경로가 무엇인지 출력한다.

사용법
    # 프로젝트 루트에서
    python scripts/probe_routes.py                      # 기본: 도쿄 신주쿠 → 마이하마
    python scripts/probe_routes.py tokyo shibuya_asakusa
    python scripts/probe_routes.py paris chatelet_montmartre --raw
    python scripts/probe_routes.py --list

⚠️ Google Maps Platform 약관상 응답의 저장·캐싱이 제한된다.
    이 스크립트는 응답을 파일로 쓰지 않는다. 표준출력으로만 본다.
    --raw 로 원본을 볼 수는 있지만, 리다이렉트해서 파일로 남기지 말 것.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import httpx  # requirements.txt 에 이미 있음 (requests 는 없음)

try:
    from dotenv import load_dotenv

    load_dotenv()  # 프로젝트 루트 .env 에서 키를 읽는다 (하드코딩 금지)
except ImportError:  # python-dotenv 미설치 환경에서도 환경변수로 동작
    pass

ENDPOINT = "https://routes.googleapis.com/directions/v2:computeRoutes"
API_KEY_ENV = "GOOGLE_BACKEND_API_KEY"  # 백엔드용 키(A). Maps JS 키(B)와 분리.

# ---------------------------------------------------------------------------
# 테스트 구간 — Google 은 (latitude, longitude) 순서. ODsay 와 반대다.
# ---------------------------------------------------------------------------
CITIES: dict[str, dict] = {
    "tokyo": {
        "tz": "Asia/Tokyo",
        "region": "JP",
        "segments": {
            # ★ 기본값: 도쿄역에서 JR→케이요선 환승이 확정적으로 발생하는 구간
            "shinjuku_maihama": {
                "label": "신주쿠역 → 마이하마역(도쿄디즈니리조트)",
                "origin": (35.6896, 139.7006),
                "destination": (35.6329, 139.8804),
            },
            # 노션 원안. 긴자선 직통이라 환승 0회로 나올 수 있음(그것도 유효한 관측).
            "shibuya_asakusa": {
                "label": "시부야역 → 아사쿠사(센소지)",
                "origin": (35.6580, 139.7016),
                "destination": (35.7148, 139.7967),
            },
            "ueno_akihabara": {
                "label": "우에노역 → 아키하바라역 (짧은 구간 / 도보 비교용)",
                "origin": (35.7141, 139.7774),
                "destination": (35.6984, 139.7731),
            },
        },
    },
    "paris": {
        "tz": "Europe/Paris",
        "region": "FR",
        "segments": {
            "chatelet_montmartre": {
                "label": "샤틀레 → 몽마르트(사크레쾨르)",
                "origin": (48.8586, 2.3470),
                "destination": (48.8867, 2.3431),
            },
            "eiffel_versailles": {
                "label": "에펠탑 → 베르사유 궁전 (도심-외곽, RER 환승)",
                "origin": (48.8584, 2.2945),
                "destination": (48.8049, 2.1204),
            },
            "louvre_orsay": {
                "label": "루브르 → 오르세 (짧은 구간)",
                "origin": (48.8606, 2.3376),
                "destination": (48.8600, 2.3266),
            },
        },
    },
    "bangkok": {
        "tz": "Asia/Bangkok",
        "region": "TH",
        "segments": {
            "siam_watpho": {
                "label": "시암 → 왓포 (BTS + 보트/버스 환승 가능성)",
                "origin": (13.7455, 100.5340),
                "destination": (13.7465, 100.4927),
            },
            "suvarnabhumi_khaosan": {
                "label": "수완나품공항 → 카오산로드 (품질 하한 측정)",
                "origin": (13.6900, 100.7501),
                "destination": (13.7590, 100.4977),
            },
            "asok_chatuchak": {
                "label": "아속 → 짜뚜짝 (BTS/MRT 환승)",
                "origin": (13.7373, 100.5601),
                "destination": (13.7999, 100.5501),
            },
        },
    },
}

# 프로브용 fieldMask — 넓게 받아서 뭐가 오는지 다 본다.
# 운영 코드에서는 아래 PROD_FIELD_MASK 로 좁힐 것. ('*' 는 비용·지연 때문에 금지)
PROBE_FIELD_MASK = ",".join(
    [
        "routes.duration",
        "routes.distanceMeters",
        "routes.description",
        "routes.routeLabels",
        "routes.localizedValues",          # 총 소요/거리/요금의 사람이 읽는 문자열
        "routes.travelAdvisory",           # transitFare (통화·금액)
        "routes.legs.duration",
        "routes.legs.distanceMeters",
        "routes.legs.startLocation",
        "routes.legs.endLocation",
        "routes.legs.stepsOverview",       # 이동수단별 step 묶음 요약
        "routes.legs.steps.travelMode",
        "routes.legs.steps.distanceMeters",
        "routes.legs.steps.staticDuration",
        "routes.legs.steps.navigationInstruction",
        "routes.legs.steps.transitDetails",  # ★ 편성 시각·노선·운영기관이 전부 여기
    ]
)

PROD_FIELD_MASK = ",".join(
    [
        "routes.duration",
        "routes.distanceMeters",
        "routes.travelAdvisory.transitFare",
        "routes.legs.steps.travelMode",
        "routes.legs.steps.staticDuration",
        "routes.legs.steps.transitDetails",
    ]
)


def default_departure(tz_name: str) -> str:
    """다음 평일 10:00(현지시각)을 RFC3339 UTC 문자열로 반환.

    departureTime 이 없으면 시간표 기반 결과가 안 나온다.
    허용 범위는 '지금부터 과거 7일 ~ 미래 100일'.
    """
    tz = ZoneInfo(tz_name)
    local_now = datetime.now(tz)
    target = datetime.combine(local_now.date() + timedelta(days=1), time(10, 0), tzinfo=tz)
    while target.weekday() >= 5:  # 토·일이면 다음 평일로 (주말 감축 운행 회피)
        target += timedelta(days=1)
    return target.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_body(seg: dict, departure_time: str, language_code: str, region_code: str) -> dict:
    """TRANSIT computeRoutes 요청 본문.

    TRANSIT 에서 넣으면 INVALID_ARGUMENT 나는 것들: intermediates,
    routingPreference, routeModifiers.avoid*, requestedReferenceRoutes,
    optimizeWaypointOrder, extraComputations=TRAFFIC_ON_POLYLINE.
    """
    o_lat, o_lng = seg["origin"]
    d_lat, d_lng = seg["destination"]
    return {
        "origin": {"location": {"latLng": {"latitude": o_lat, "longitude": o_lng}}},
        "destination": {"location": {"latLng": {"latitude": d_lat, "longitude": d_lng}}},
        "travelMode": "TRANSIT",
        "departureTime": departure_time,      # ★ 없으면 시간표 결과가 안 나온다
        "computeAlternativeRoutes": True,     # 대안 경로 개수 확인용 (최대 3개 추가)
        "languageCode": language_code,        # localizedValues 언어
        "regionCode": region_code,
        "units": "METRIC",
        # 선택: 필요하면 주석 해제
        # "transitPreferences": {
        #     "allowedTravelModes": ["SUBWAY", "TRAIN", "LIGHT_RAIL", "RAIL", "BUS"],
        #     "routingPreference": "FEWER_TRANSFERS",  # 또는 LESS_WALKING
        # },
    }


def call_routes(body: dict, api_key: str, field_mask: str) -> dict:
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": field_mask,  # ★ 누락하면 응답이 비어 온다
    }
    resp = httpx.post(ENDPOINT, json=body, headers=headers, timeout=20.0)
    if resp.status_code != 200:
        print(f"[HTTP {resp.status_code}]\n{resp.text}", file=sys.stderr)
        resp.raise_for_status()
    return resp.json()


def first_transit_step(route: dict) -> dict | None:
    for leg in route.get("legs", []):
        for step in leg.get("steps", []):
            if step.get("travelMode") == "TRANSIT":
                return step
    return None


def report(data: dict) -> None:
    """노션 체크리스트 13개 항목을 있음/없음 + 실제 필드 경로로 출력."""
    routes = data.get("routes", [])
    if not routes:
        print("경로 없음 — fieldMask 또는 대중교통 데이터 문제. 원문을 확인할 것.")
        return

    route = routes[0]
    step = first_transit_step(route)
    td = (step or {}).get("transitDetails", {})
    stop = td.get("stopDetails", {})
    line = td.get("transitLine", {})
    agencies = line.get("agencies", [{}])
    walk_steps = [
        s
        for lg in route.get("legs", [])
        for s in lg.get("steps", [])
        if s.get("travelMode") == "WALK"
    ]
    transit_steps = [
        s
        for lg in route.get("legs", [])
        for s in lg.get("steps", [])
        if s.get("travelMode") == "TRANSIT"
    ]

    rows = [
        ("편성 출발 시각 ★", stop.get("departureTime"),
         "routes[].legs[].steps[].transitDetails.stopDetails.departureTime"),
        ("편성 도착 시각 ★", stop.get("arrivalTime"),
         "routes[].legs[].steps[].transitDetails.stopDetails.arrivalTime"),
        ("총 소요시간", route.get("duration"), "routes[].duration"),
        ("총 요금", (route.get("travelAdvisory", {}).get("transitFare")
                  or route.get("localizedValues", {}).get("transitFare")),
         "routes[].travelAdvisory.transitFare / routes[].localizedValues.transitFare"),
        ("환승 횟수(=transit step 수 - 1)",
         max(len(transit_steps) - 1, 0) if transit_steps else None,
         "routes[].legs[].steps[travelMode=TRANSIT] 개수 - 1"),
        ("구간별 교통수단 종류", line.get("vehicle", {}).get("type"),
         "…transitDetails.transitLine.vehicle.type"),
        ("구간별 노선명", line.get("name") or line.get("nameShort"),
         "…transitDetails.transitLine.name / .nameShort / .color"),
        ("구간별 승·하차 정류장명",
         (stop.get("departureStop", {}).get("name"), stop.get("arrivalStop", {}).get("name")),
         "…transitDetails.stopDetails.departureStop.name / .arrivalStop.name"),
        ("구간별 소요시간", (step or {}).get("staticDuration"),
         "routes[].legs[].steps[].staticDuration"),
        ("운영기관 이름 ★약관", agencies[0].get("name") if agencies else None,
         "…transitDetails.transitLine.agencies[].name"),
        ("운영기관 URL ★약관", agencies[0].get("uri") if agencies else None,
         "…transitDetails.transitLine.agencies[].uri"),
        ("도보 거리·시간",
         (sum(s.get("distanceMeters", 0) for s in walk_steps) if walk_steps else None),
         "routes[].legs[].steps[travelMode=WALK].distanceMeters / .staticDuration"),
        ("대안 경로 개수", len(routes), "routes[] 배열 길이 (computeAlternativeRoutes=true)"),
    ]

    print(f"\n{'항목':<28} {'있음':<5} 값 / 필드 경로")
    print("-" * 100)
    for name, value, path in rows:
        mark = "O" if value not in (None, "", 0, (None, None), []) else "X"
        print(f"{name:<28} {mark:<5} {value}")
        print(f"{'':<28} {'':<5} └ {path}")

    # 참고: 노선 색·headsign·정차 수 등 부가 정보
    print("\n[참고]")
    print(f"  headsign        : {td.get('headsign')}   (…transitDetails.headsign)")
    print(f"  stopCount       : {td.get('stopCount')}  (…transitDetails.stopCount)")
    print(f"  routeLabels     : {route.get('routeLabels')}")
    print(f"  localizedValues : {json.dumps(route.get('localizedValues', {}), ensure_ascii=False)}")


def diagnose(seg: dict, departure: str, region: str, api_key: str) -> None:
    """빈 응답(routes 없음)의 원인을 단계적으로 좁힌다.

    요청을 최소 형태부터 하나씩 키워가며 어느 항목에서 결과가 사라지는지 본다.
    0번(DRIVE)이 되고 1번(TRANSIT)이 안 되면 좌표·키가 아니라 대중교통 쪽 문제다.
    """
    o_lat, o_lng = seg["origin"]
    d_lat, d_lng = seg["destination"]
    base = {
        "origin": {"location": {"latLng": {"latitude": o_lat, "longitude": o_lng}}},
        "destination": {"location": {"latLng": {"latitude": d_lat, "longitude": d_lng}}},
    }
    transit = {**base, "travelMode": "TRANSIT"}
    with_time = {**transit, "departureTime": departure}
    with_alt = {**with_time, "computeAlternativeRoutes": True}
    with_local = {**with_alt, "languageCode": "ko", "regionCode": region, "units": "METRIC"}

    cases: list[tuple[str, dict, str]] = [
        ("0. DRIVE (좌표·키 확인)", {**base, "travelMode": "DRIVE"}, "routes.duration"),
        ("1. TRANSIT 최소", transit, "routes.duration"),
        ("2. + departureTime", with_time, "routes.duration"),
        ("3. + computeAlternativeRoutes", with_alt, "routes.duration"),
        ("4. + language/region/units", with_local, "routes.duration"),
        ("5. + 전체 fieldMask", with_local, PROBE_FIELD_MASK),
    ]

    print("\n단계별 진단 — 처음으로 0개가 되는 줄이 원인이다\n" + "-" * 70)
    for label, body, mask in cases:
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": mask,
        }
        try:
            resp = httpx.post(ENDPOINT, json=body, headers=headers, timeout=20.0)
        except httpx.HTTPError as exc:
            print(f"{label:<30} 네트워크 오류: {exc}")
            continue
        if resp.status_code != 200:
            print(f"{label:<30} HTTP {resp.status_code} · {resp.text[:160]}")
            continue
        routes = resp.json().get("routes", [])
        flag = "" if routes else "   ← 여기서 결과가 사라진다"
        print(f"{label:<30} HTTP 200 · routes {len(routes)}개{flag}")
    print("-" * 70)


def main() -> None:
    parser = argparse.ArgumentParser(description="Routes API TRANSIT 응답 필드 프로브")
    parser.add_argument("city", nargs="?", default="tokyo", help="tokyo | paris | bangkok")
    parser.add_argument("segment", nargs="?", default="shinjuku_maihama")
    parser.add_argument("--departure", help="RFC3339 UTC (예: 2026-09-08T01:00:00Z)")
    parser.add_argument("--raw", action="store_true", help="원본 JSON 출력 (파일로 저장 금지)")
    parser.add_argument("--list", action="store_true", help="구간 목록만 출력")
    parser.add_argument("--diagnose", action="store_true",
                        help="빈 응답 원인을 단계적으로 좁힌다")
    args = parser.parse_args()

    if args.list:
        for city, cfg in CITIES.items():
            print(f"\n[{city}] tz={cfg['tz']}")
            for key, seg in cfg["segments"].items():
                print(f"  {key:<24} {seg['label']}  {seg['origin']} → {seg['destination']}")
        return

    api_key = os.environ.get(API_KEY_ENV)
    if not api_key:
        sys.exit(f"환경변수 {API_KEY_ENV} 가 없다. .env 에 백엔드용 키(A)를 넣을 것.")

    city_cfg = CITIES[args.city]
    seg = city_cfg["segments"][args.segment]
    departure = args.departure or default_departure(city_cfg["tz"])

    body = build_body(seg, departure, language_code="ko", region_code=city_cfg["region"])
    print(f"■ {args.city}/{args.segment} — {seg['label']}")
    print(f"■ departureTime: {departure} (UTC)")
    print(f"■ request body:\n{json.dumps(body, ensure_ascii=False, indent=2)}")

    if args.diagnose:
        diagnose(seg, departure, city_cfg["region"], api_key)
        return

    data = call_routes(body, api_key, PROBE_FIELD_MASK)

    # 결과가 비면 원문을 무조건 보여준다 — 원인을 짐작하지 않기 위해서다.
    if args.raw or not data.get("routes"):
        print(f"■ 응답 원문:\n{json.dumps(data, ensure_ascii=False, indent=2)}")
    report(data)
    print("\n⚠️ 이 출력을 파일로 저장하거나 리포에 커밋하지 말 것 (Google 약관).")


if __name__ == "__main__":
    main()
