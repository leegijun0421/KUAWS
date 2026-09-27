"""지원 도시 화이트리스트 — 도시별 시간대·막차 기준을 한곳에 모은다.

화이트리스트 = 파리(데모) + 타이베이(아시아 사례). docs/DECISIONS.md 2026-09-06.
도쿄·오사카는 Google Routes 가 TRANSIT 을 주지 않아 제외했다(본선 이관).
"""

from __future__ import annotations

from pydantic import BaseModel


class CityProfile(BaseModel):
    """도시 하나의 서비스 설정."""

    key: str
    label: str
    #: IANA 시간대. 대중교통 시간표(departureTime)를 현지 시각으로 요청하는 데 쓴다.
    timezone: str
    #: 도심 지하철 마지막 운행 시각(현지, "HH:MM"). 운영기관 공개 운행시간 기준이다.
    #: 파리 RATP 메트로 평일 막차 ≈ 00:40, 타이베이 MRT 운행 종료 ≈ 24:00.
    #: 보수적으로 조금 앞당겨 둔다. 막차 경고(C1)의 기준값이다.
    last_service_at: str
    #: 도시 중심 좌표(지도 초기 위치).
    center: tuple[float, float]


CITIES: dict[str, CityProfile] = {
    "paris": CityProfile(
        key="paris",
        label="파리",
        timezone="Europe/Paris",
        last_service_at="00:30",
        center=(48.8566, 2.3522),
    ),
    "taipei": CityProfile(
        key="taipei",
        label="타이베이",
        timezone="Asia/Taipei",
        last_service_at="23:45",
        center=(25.0418, 121.5438),
    ),
}


def get_city(key: str) -> CityProfile:
    """도시 설정을 찾는다. 화이트리스트 밖이면 ValueError."""
    if key not in CITIES:
        supported = ", ".join(CITIES)
        raise ValueError(f"지원하지 않는 도시입니다: {key} (지원: {supported})")
    return CITIES[key]
