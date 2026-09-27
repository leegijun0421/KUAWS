"""단톡방 대화 텍스트 → 화자별 발화 묶음.

카카오톡 '대화 내보내기' 형식 두 가지와 단순 `이름: 메시지` 형식을 받는다.
화자 분리는 규칙으로 한다 — LLM 에게 맡기면 토큰이 늘고 이름을 지어낼 위험이 있다.

    [민지] [오후 3:01] 파리 가면 루브르는 꼭 가자        ← PC 내보내기
    2026년 9월 20일 오후 3:01, 민지 : 파리 가면 ...      ← 모바일 내보내기
    민지: 파리 가면 ...                                   ← 직접 붙여넣기
"""

from __future__ import annotations

import re

_PC_LINE = re.compile(r"^\[(?P<name>[^\]]+)\]\s*\[[^\]]+\]\s*(?P<msg>.*)$")
_MOBILE_LINE = re.compile(
    r"^\d{4}[.년]\s*\d{1,2}[.월]\s*\d{1,2}[.일]?\s*(?:오전|오후)?\s*\d{1,2}:\d{2},\s*"
    r"(?P<name>[^:]+?)\s*:\s*(?P<msg>.*)$"
)
_SIMPLE_LINE = re.compile(r"^(?P<name>[^\s:\[\]][^:\[\]]{0,19}?)\s*:\s*(?P<msg>.+)$")

#: 대화가 아닌 줄(날짜 구분선, 입퇴장 안내, 내보내기 머리말).
_NOISE = re.compile(
    r"^(-{3,}.*-{3,}|.*님이 (들어왔습니다|나갔습니다|초대했습니다).*|"
    r".*님과 카카오톡 대화|저장한 날짜\s*:.*|\d{4}년 \d{1,2}월 \d{1,2}일 .요일)$"
)

#: 내용 없는 메시지. 취향 근거가 되지 않으므로 버린다.
_EMPTY_MESSAGES = frozenset({"사진", "이모티콘", "동영상", "삭제된 메시지입니다."})


def parse_chat(text: str) -> dict[str, list[str]]:
    """대화 텍스트를 {화자: [메시지…]} 로 나눈다. 화자 순서는 첫 발화 순서다."""
    speakers: dict[str, list[str]] = {}
    last_speaker: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or _NOISE.match(line):
            continue
        parsed = _match_line(line)
        if parsed is None:
            # 여러 줄 메시지의 이어지는 줄. 직전 화자에게 붙인다.
            if last_speaker is not None:
                speakers[last_speaker][-1] += " " + line
            continue
        name, message = parsed
        if message in _EMPTY_MESSAGES:
            continue
        speakers.setdefault(name, []).append(message)
        last_speaker = name
    return speakers


def _match_line(line: str) -> tuple[str, str] | None:
    """한 줄에서 (화자, 메시지)를 뽑는다. 대화 줄이 아니면 None."""
    for pattern in (_PC_LINE, _MOBILE_LINE, _SIMPLE_LINE):
        match = pattern.match(line)
        if match:
            return match.group("name").strip(), match.group("msg").strip()
    return None
