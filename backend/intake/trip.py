"""대화 속 '확정 사항'(도시·일수·날짜·시간 제약) 정규화.

LLM 이 뽑은 값과 규칙으로 뽑은 값을 같은 형태(`TripFacts` + 시간 제약)로 맞춘다.
도시는 화이트리스트 key 로 바꾸고, 지원하지 않는 도시면 `city_supported=False` 로 돌려
화면이 지원 도시를 다시 묻게 한다(Notion W1: "화이트리스트 밖이면 그대로 진행하지 말 것").
"""

from __future__ import annotations

import re
from datetime import date

from shared.types.models import TripFacts

#: 도시 표기 → 화이트리스트 key. 소문자·공백 제거 후 포함 여부로 찾는다.
_CITY_ALIASES = {
    "paris": ("paris", "파리", "巴黎"),
    "taipei": ("taipei", "타이베이", "타이페이", "台北", "臺北"),
}
_HHMM = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")
_NIGHTS_DAYS = re.compile(r"(\d)\s*박\s*(\d)\s*일")
_DAYS = re.compile(r"(?<!\d)([1-7])\s*일(?:짜리|간|치)")
_DAY_TRIP = re.compile(r"당일|하루짜리")
_DATE = re.compile(r"(\d{1,2})\s*월\s*(\d{1,2})\s*일")
_EARLIEST = re.compile(
    r"(오전\s*)?(\d{1,2})\s*시\s*(이전|전)(에는|엔|에|은|는)?\s*(일정\s*)?(잡지\s*말|못|안\s*돼|불가)"
)
_KOREAN_DAYS = {"하루": 1, "이틀": 2, "사흘": 3}
_DEFAULT_YEAR = 2026


def facts_from_llm(raw: dict | None) -> tuple[TripFacts, str | None, str | None]:
    """LLM 의 trip 객체 → (TripFacts, earliest_start, latest_end). 형식이 틀린 값은 버린다."""
    raw = raw or {}
    city = raw.get("city") or None
    key = city_key(str(city)) if city else None
    days = raw.get("days")
    facts = TripFacts(
        city=key or city,
        city_supported=key is not None,
        days=days if isinstance(days, int) and 1 <= days <= 14 else None,
        start_date=_valid_date(raw.get("start_date")),
    )
    return facts, _valid_hhmm(raw.get("earliest_start")), _valid_hhmm(raw.get("latest_end"))


def facts_from_text(text: str) -> tuple[TripFacts, str | None]:
    """규칙 기반 폴백 — 발화 본문에서 도시·일수·날짜·'N시 이전 불가'를 찾는다.

    내보내기 머리말의 날짜(저장한 날짜·날짜 구분선)가 섞이지 않도록 **발화만** 넘길 것.
    """
    key = next(
        (k for k, names in _CITY_ALIASES.items() if any(n in text.lower() for n in names)), None
    )
    days = None
    if match := _NIGHTS_DAYS.search(text):
        days = int(match.group(2))
    elif match := _DAYS.search(text):
        days = int(match.group(1))
    elif _DAY_TRIP.search(text):
        days = 1
    else:
        days = next(
            (n for word, n in _KOREAN_DAYS.items() if any(word + s in text for s in "이니간")),
            None,
        )
    start = None
    if match := _DATE.search(text):
        start = _valid_date(f"{_DEFAULT_YEAR}-{int(match.group(1)):02d}-{int(match.group(2)):02d}")
    earliest = None
    if match := _EARLIEST.search(text):
        earliest = f"{int(match.group(2)):02d}:00"
    facts = TripFacts(city=key, city_supported=key is not None, days=days, start_date=start)
    return facts, earliest


def city_key(name: str) -> str | None:
    """도시 표기를 화이트리스트 key 로. 모르면 None."""
    lowered = name.lower().replace(" ", "")
    for key, names in _CITY_ALIASES.items():
        if any(alias in lowered for alias in names):
            return key
    return None


def _valid_hhmm(value: object) -> str | None:
    """ "HH:MM" 이면 두 자리로 맞춰 돌려주고, 아니면 None."""
    if not isinstance(value, str) or not (match := _HHMM.match(value.strip())):
        return None
    return f"{int(match.group(1)):02d}:{match.group(2)}"


def _valid_date(value: object) -> str | None:
    """ISO 날짜면 그대로, 아니면 None."""
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value.strip()).isoformat()
    except ValueError:
        return None
