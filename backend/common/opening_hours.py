"""Google Places `weekdayDescriptions` 문자열 → 요일별 영업 구간.

수집 스크립트는 영업시간을 사람이 읽는 한 줄로 저장한다(`data/scripts/poi_filters.py`).

    "Monday: 7:30 AM – 1:30 AM | Tuesday: Closed | Wednesday: 12:00 – 1:30 PM, 7:30 – 9:30 PM"

스케줄러는 "이 시각에 열려 있나"만 알면 되므로 요일(0=월) → [("HH:MM", "HH:MM"), …] 로
바꾼다. 자정을 넘겨 닫는 곳은 "24:00" 으로 자른다(일정은 21시에 끝난다).
해석하지 못한 요일은 결과에서 빠진다 — 호출부는 없는 요일을 '모름'으로 다룬다.
"""

from __future__ import annotations

import re

_DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
_TIME = re.compile(r"(\d{1,2})(?::(\d{2}))?\s*([AP]M)?", re.IGNORECASE)
_SPACES = re.compile(r"[   ]")


def parse_weekly_hours(text: str | None) -> dict[int, list[tuple[str, str]]] | None:
    """영업시간 문자열을 요일별 구간으로 바꾼다. 입력이 없으면 None(= 모름)."""
    if not text:
        return None
    weekly: dict[int, list[tuple[str, str]]] = {}
    for part in _SPACES.sub(" ", text).split("|"):
        day_name, _, body = part.strip().partition(":")
        day = day_name.strip().lower()
        if day not in _DAYS:
            continue
        ranges = _parse_day(body.strip())
        if ranges is not None:
            weekly[_DAYS.index(day)] = ranges
    return weekly or None


def _parse_day(body: str) -> list[tuple[str, str]] | None:
    """하루치 본문. "Closed" 는 빈 목록, 해석 실패는 None."""
    lowered = body.lower()
    if lowered.startswith("closed"):
        return []
    if "24 hours" in lowered:
        return [("00:00", "24:00")]
    ranges = []
    for chunk in body.split(","):
        pieces = re.split(r"\s*[–-]\s*", chunk.strip())
        if len(pieces) != 2:
            return None
        parsed = _parse_range(pieces[0], pieces[1])
        if parsed is None:
            return None
        ranges.append(parsed)
    return ranges


def _parse_range(start: str, end: str) -> tuple[str, str] | None:
    """"12:00" – "1:30 PM" 처럼 앞쪽 오전/오후가 생략된 구간까지 처리한다."""
    end_match, start_match = _TIME.fullmatch(end.strip()), _TIME.fullmatch(start.strip())
    if not end_match or not start_match:
        return None
    end_min = _to_minutes(end_match, end_match.group(3))
    start_min = _to_minutes(start_match, start_match.group(3) or end_match.group(3))
    if start_match.group(3) is None and start_min > end_min:
        start_min = _to_minutes(start_match, "AM")  # "11:00 – 2:00 PM" → 오전 11시
    if end_min <= start_min:
        end_min = 24 * 60  # 자정 넘어 영업 — 일정 범위에서는 '끝까지 연다'로 충분
    return _fmt(start_min), _fmt(end_min)


def _to_minutes(match: re.Match[str], meridiem: str | None) -> int:
    """정규식 매치 → 자정 기준 분. 오전/오후 표기가 없으면 24시간제로 본다."""
    hour, minute = int(match.group(1)), int(match.group(2) or 0)
    if meridiem:
        hour = hour % 12 + (12 if meridiem.upper() == "PM" else 0)
    return hour * 60 + minute


def _fmt(minutes: int) -> str:
    """분 → "HH:MM"."""
    return f"{minutes // 60:02d}:{minutes % 60:02d}"
