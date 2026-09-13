"""경로 조회 프로바이더의 공통 인터페이스와 선택 로직.

왜 프로바이더를 나누는가
------------------------
Google Maps 는 전 세계를 커버하지만 **대한민국에서는 도보·자동차 경로를
공식 지원하지 않는다**(국가공간정보 기본법에 따른 고정밀 지도 반출 제한).
반대로 ODsay 는 국내 대중교통 데이터가 정확하지만 해외를 다루지 못한다.

그래서 `backend/routing` 은 구체 API 를 직접 부르지 않고 이 인터페이스에만
의존한다. 좌표가 어디냐에 따라 구현체가 자동으로 갈린다.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from hashlib import sha256
from pathlib import Path

from pydantic import BaseModel

from backend.common.config import get_settings
from backend.common.logging import get_logger
from shared.types.models import RoutePreference, RouteSegment

logger = get_logger(__name__)

#: 대한민국 본토·제주를 포함하는 대략적인 경계 상자 (남,북,서,동).
#: 정밀한 국경 판정이 목적이 아니라 프로바이더 분기용이므로 이 정도로 충분하다.
KOREA_BBOX = (33.0, 38.7, 124.5, 132.0)


class GeoPoint(BaseModel):
    """경로의 출발지/도착지 한 지점."""

    poi_id: str
    name: str
    lat: float
    lng: float


class RouteProviderError(Exception):
    """경로 조회 실패. 호출부가 사용자에게 재시도를 안내할 수 있도록 던진다."""


class NoRouteError(RouteProviderError):
    """요청은 성공했지만 그 구간에 대중교통 경로가 없다.

    키 미설정·API 오류와 구분하기 위한 하위 예외다. 전자는 우리가 고쳐야 할 버그지만
    이쪽은 정상적인 결과이고, 호출부(`planner.plan_segment`)는 다른 후보로 넘어가면 된다.
    `RouteProviderError` 를 잡던 기존 호출부는 그대로 동작한다(상속).
    """


class Operator(BaseModel):
    """대중교통 운영기관. Google Maps 약관상 화면 표기 의무가 있다.

    공통 모델 `RouteLeg` 에는 이 값을 담을 자리가 없다(`shared/types/` 는 PM 소유라
    임의로 못 고친다). 그래서 구간 단위로 모아 `RouteDetail` 에 실어 보낸다.
    필드 경로는 `transitLine.agencies[].name` / `.uri` — 9/6 필드 확인에서 두 도시 모두 확인됐다.
    """

    name: str
    url: str | None = None


class RouteDetail(BaseModel):
    """정규화된 경로 + 공통 모델에 자리가 없는 부가 정보."""

    segment: RouteSegment
    #: 이 구간에 등장한 운영기관 (중복 제거). 프론트가 그대로 렌더링한다.
    operators: list[Operator] = []


class RouteProvider(ABC):
    """경로 조회 프로바이더. 구현체는 응답을 RouteSegment 로 정규화해 돌려준다."""

    #: 로그·캐시 키에 쓰이는 식별자
    name: str = "base"

    #: 원본 응답을 디스크에 저장해도 되는가.
    #: 제공자 약관마다 다르므로 프로바이더별로 명시한다. 기본값은 보수적으로 False.
    cacheable: bool = False

    def fetch_route(
        self,
        origin: GeoPoint,
        destination: GeoPoint,
        preference: RoutePreference,
        depart_at: str | None = None,
    ) -> RouteSegment:
        """두 지점 사이의 대중교통 경로를 조회해 공통 모델로 반환한다."""
        return self.fetch_route_detail(origin, destination, preference, depart_at).segment

    def fetch_route_detail(
        self,
        origin: GeoPoint,
        destination: GeoPoint,
        preference: RoutePreference,
        depart_at: str | None = None,
    ) -> RouteDetail:
        """경로 1건을 조회해 정규화 결과와 운영기관 표기를 함께 반환한다.

        `depart_at`(RFC3339)을 넘기면 그 시각의 시간표가 적용된다. 생략하면 요청 시각
        기준이라 `RouteLeg.depart_at` / `arrive_at` 이 "지금 출발" 기준으로 채워진다 —
        일정표를 만들 때는 반드시 넘길 것.

        캐싱 여부는 `cacheable` 이 결정한다. 구현체는 `_request()` 와
        `_to_segment()` 만 채우면 되고 캐시 정책을 신경 쓰지 않는다.
        """
        key = self.cache_key(origin, destination, preference, depart_at)
        payload = load_cached(key) if self.cacheable else None
        if payload is None:
            payload = self._request(origin, destination, preference, depart_at)
            if self.cacheable:
                save_cache(key, payload)
        return RouteDetail(
            segment=self._to_segment(payload, origin, destination, preference),
            operators=self._extract_operators(payload),
        )

    @abstractmethod
    def _request(
        self,
        origin: GeoPoint,
        destination: GeoPoint,
        preference: RoutePreference,
        depart_at: str | None = None,
    ) -> dict:
        """외부 API 를 호출해 원본 응답(dict)을 돌려준다."""

    def _extract_operators(self, payload: dict) -> list[Operator]:
        """원본 응답에서 운영기관 목록을 뽑는다. 주지 않는 제공자는 빈 목록."""
        return []

    @abstractmethod
    def _to_segment(
        self,
        payload: dict,
        origin: GeoPoint,
        destination: GeoPoint,
        preference: RoutePreference,
    ) -> RouteSegment:
        """원본 응답을 공통 RouteSegment 로 정규화한다."""

    def cache_key(
        self,
        origin: GeoPoint,
        destination: GeoPoint,
        preference: RoutePreference,
        depart_at: str | None = None,
    ) -> str:
        """동일 요청을 식별하는 캐시 키. 좌표는 소수점 5자리(약 1m)로 절삭한다.

        출발 시각이 다르면 시간표가 달라지므로 키도 달라야 한다.
        """
        raw = "|".join(
            [
                self.name,
                preference,
                f"{origin.lat:.5f},{origin.lng:.5f}",
                f"{destination.lat:.5f},{destination.lng:.5f}",
                depart_at or "now",
            ]
        )
        return sha256(raw.encode()).hexdigest()[:16]


def is_in_korea(lat: float, lng: float) -> bool:
    """좌표가 대한민국 경계 상자 안에 있는지 판정한다."""
    south, north, west, east = KOREA_BBOX
    return south <= lat <= north and west <= lng <= east


def select_provider(origin: GeoPoint, destination: GeoPoint) -> RouteProvider:
    """출발지·도착지 위치에 맞는 프로바이더를 고른다.

    양쪽 모두 국내면 ODsay, 그 외(해외 또는 국가 간 이동)는 Google Maps 를 쓴다.
    국내-해외가 섞인 경로는 ODsay 가 아예 처리하지 못하므로 Google 로 넘긴다.
    """
    # 순환 import 를 피하기 위해 함수 안에서 import 한다.
    from backend.routing.google_provider import GoogleRouteProvider
    from backend.routing.odsay_provider import OdsayRouteProvider

    both_domestic = is_in_korea(origin.lat, origin.lng) and is_in_korea(
        destination.lat, destination.lng
    )
    provider = OdsayRouteProvider() if both_domestic else GoogleRouteProvider()
    logger.info("경로 프로바이더 선택: %s (국내 구간=%s)", provider.name, both_domestic)
    return provider


def load_cached(key: str) -> dict | None:
    """캐시된 원본 응답을 읽는다. 없으면 None."""
    path = _cache_path(key)
    if not path.exists():
        return None
    logger.info("경로 캐시 적중: %s", key)
    return json.loads(path.read_text(encoding="utf-8"))


def save_cache(key: str, payload: dict) -> None:
    """원본 응답을 캐시에 저장한다. 무료 호출 한도를 아끼기 위한 필수 단계다."""
    path = _cache_path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _cache_path(key: str) -> Path:
    """캐시 키에 대응하는 파일 경로."""
    return Path(get_settings().cache_dir) / "routes" / f"{key}.json"
