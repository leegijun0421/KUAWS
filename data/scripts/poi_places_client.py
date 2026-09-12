"""[W1] Google Places API (New) 호출 래퍼.

`collect_pois.py` 가 쓰는 얇은 클라이언트다. 이 모듈의 책임은 세 가지다.
    1. Text Search (New) 페이지네이션
    2. 필요한 장소만 Place Details (New) 로 보강
    3. 실패 재시도와 실패 횟수 집계

⚠️ 다음은 이 모듈이 **하지 않는** 일이다 (Google 약관 및 팀 규칙).
    - `reviews` 필드를 field mask 에 넣지 않는다. 리뷰 원문은 요청도 저장도 하지 않는다.
    - 응답 원문(raw response)을 파일에 쓰지 않고 로그에도 남기지 않는다.
    - API 키를 로그·예외 메시지·URL 에 노출하지 않는다 (헤더로만 전달).
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from logging import Logger

import httpx

SEARCH_ENDPOINT = "https://places.googleapis.com/v1/places:searchText"
DETAILS_ENDPOINT = "https://places.googleapis.com/v1/places/{place_id}"

#: Text Search 응답에서 받을 필드. 여기 없는 필드는 응답에 오지 않는다.
#: rating / userRatingCount / businessStatus / types 는 **필터 전용**이며
#: 최종 저장 파일에는 넣지 않는다 (collect_pois.py 의 정규화 단계에서 버린다).
SEARCH_FIELD_MASK = ",".join(
    [
        "places.id",
        "places.displayName",
        "places.location",
        "places.types",
        "places.businessStatus",
        "places.rating",
        "places.userRatingCount",
        "places.regularOpeningHours.weekdayDescriptions",
        "nextPageToken",
    ]
)

#: Place Details 는 Text Search 에서 값이 빠진 장소를 보강할 때만 호출한다.
#: 필드 구성은 위와 같고, reviews 는 포함하지 않는다.
DETAILS_FIELD_MASK = ",".join(
    [
        "id",
        "displayName",
        "location",
        "types",
        "businessStatus",
        "rating",
        "userRatingCount",
        "regularOpeningHours.weekdayDescriptions",
    ]
)

#: 한 페이지 최대 20건이 API 상한이다 (pageSize 20 초과는 20 으로 강제된다).
PAGE_SIZE = 20
MAX_RETRIES = 3
BACKOFF_BASE_SEC = 1.5
PAGE_DELAY_SEC = 0.4
RETRY_STATUS = frozenset({408, 429, 500, 502, 503, 504})


class PlacesClient:
    """Places API (New) 호출기. 실패는 삼키지 않고 세어서 상위에 보고한다."""

    def __init__(self, api_key: str, logger: Logger, timeout: float = 20.0) -> None:
        self._logger = logger
        self._client = httpx.Client(timeout=timeout)
        # 키는 헤더로만 보낸다. URL 쿼리에 넣으면 로그·프록시에 남는다.
        self._auth = {"Content-Type": "application/json", "X-Goog-Api-Key": api_key}
        self.failures = 0
        self.search_calls = 0
        self.details_calls = 0

    def __enter__(self) -> PlacesClient:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        """HTTP 커넥션을 정리한다."""
        self._client.close()

    def search_text(
        self,
        query: str,
        rectangle: dict[str, dict[str, float]],
        language_code: str,
        region_code: str,
        max_pages: int,
    ) -> Iterator[dict]:
        """Text Search (New) 결과를 페이지 단위로 순회하며 장소 dict 를 하나씩 넘긴다.

        호출부가 도중에 멈출 수 있도록 제너레이터로 만들었다 (쿼터가 차면 더 안 부른다).
        """
        body: dict[str, object] = {
            "textQuery": query,
            "languageCode": language_code,
            "regionCode": region_code,
            "pageSize": PAGE_SIZE,
            # rectangle 로 도시 밖 결과를 API 단계에서 막는다. 그래도 호출부에서
            # 좌표를 한 번 더 검사한다 (경계 밖 응답을 신뢰하지 않기 위함).
            "locationRestriction": {"rectangle": rectangle},
        }
        for page in range(1, max_pages + 1):
            payload = self._post(SEARCH_ENDPOINT, body, SEARCH_FIELD_MASK, f"searchText[{query}]")
            self.search_calls += 1
            if payload is None:
                return

            places = payload.get("places", [])
            self._logger.info("    p%d: %d건 (query=%s)", page, len(places), query)
            yield from places

            token = payload.get("nextPageToken")
            if not token:
                return
            # pageToken 외의 파라미터는 첫 호출과 동일해야 INVALID_ARGUMENT 가 안 난다.
            body = {**body, "pageToken": token}
            time.sleep(PAGE_DELAY_SEC)

    def fetch_details(self, place_id: str, language_code: str, region_code: str) -> dict | None:
        """Text Search 에서 값이 빠진 장소만 Place Details (New) 로 보강한다."""
        url = DETAILS_ENDPOINT.format(place_id=place_id)
        params = {"languageCode": language_code, "regionCode": region_code}
        payload = self._get(url, params, DETAILS_FIELD_MASK, "placeDetails")
        self.details_calls += 1
        return payload

    # ---------- 내부 HTTP ----------

    def _post(self, url: str, body: dict, field_mask: str, label: str) -> dict | None:
        return self._request("POST", url, field_mask, label, body=body)

    def _get(self, url: str, params: dict, field_mask: str, label: str) -> dict | None:
        return self._request("GET", url, field_mask, label, params=params)

    def _request(
        self,
        method: str,
        url: str,
        field_mask: str,
        label: str,
        body: dict | None = None,
        params: dict | None = None,
    ) -> dict | None:
        """재시도까지 포함한 단일 호출. 실패하면 None 을 반환하고 실패 수를 올린다."""
        headers = {**self._auth, "X-Goog-FieldMask": field_mask}
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = self._client.request(
                    method, url, headers=headers, json=body, params=params
                )
            except httpx.HTTPError as exc:
                # 예외 객체를 그대로 찍으면 URL 이 섞여 나올 수 있어 타입명만 남긴다.
                self._logger.warning(
                    "%s 네트워크 오류 %s (%d/%d)", label, type(exc).__name__, attempt, MAX_RETRIES
                )
            else:
                payload, retryable = self._handle(response, label, attempt)
                if not retryable:
                    return payload
            time.sleep(BACKOFF_BASE_SEC * attempt)

        self._logger.error("%s 재시도 %d회 모두 실패", label, MAX_RETRIES)
        self.failures += 1
        return None

    def _handle(
        self, response: httpx.Response, label: str, attempt: int
    ) -> tuple[dict | None, bool]:
        """응답을 판정해 (본문, 재시도 필요 여부)를 돌려준다."""
        if response.status_code == 200:
            return response.json(), False
        if response.status_code not in RETRY_STATUS:
            self._logger.error(
                "%s HTTP %d (%s) — 재시도하지 않는다",
                label,
                response.status_code,
                _error_status(response),
            )
            self.failures += 1
            return None, False
        self._logger.warning(
            "%s HTTP %d — 재시도 %d/%d", label, response.status_code, attempt, MAX_RETRIES
        )
        return None, True


def _error_status(response: httpx.Response) -> str:
    """오류 응답에서 `error.status` 열거값만 뽑는다 (본문 전체는 로그에 남기지 않는다)."""
    try:
        status = response.json()["error"]["status"]
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return "UNPARSEABLE"
    return str(status)
