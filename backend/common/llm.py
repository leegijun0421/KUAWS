"""LLM 호출 공통 계층 — 프롬프트 로딩, provider 어댑터, JSON 파싱·재시도, 결과 캐싱.

모든 LLM 호출은 `shared.types.models.LLMProvider` 프로토콜 뒤로 격리된다.
현재 구현체는 Anthropic API 직접 호출(`AnthropicProvider`)이고, Bedrock 을 쓰게 되면
구현체 하나만 추가해 `get_llm_provider()` 에서 바꿔 끼우면 된다(2026-08-28 결정).

    provider = get_llm_provider()
    system, user = render_prompt("extract_profile", member_name="민지", text="...")
    data = complete_json(provider, user, system=system)   # 파싱 실패 시 1회 재시도

규칙(`.kiro/steering/conventions.md` — LLM 호출)
- 프롬프트는 `backend/common/prompts/*.md` 에만 둔다. 코드에 하드코딩하지 않는다.
- JSON 응답은 파싱 실패 시 1회 재시도한다. 그래도 실패하면 `LLMResponseError`.
- 동일 입력은 디스크 캐시로 재호출을 막는다(`data/processed/cache/llm/`, 커밋 금지).
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from hashlib import sha256
from pathlib import Path

from backend.common.config import data_path, get_settings
from backend.common.logging import get_logger
from shared.types.models import LLMCompletion, LLMProvider

logger = get_logger(__name__)

PROMPT_DIR = Path(__file__).resolve().parent / "prompts"

#: 재시도할 때 덧붙이는 교정 지시. 프롬프트 파일이 아니라 형식 교정이라 코드에 둔다.
_RETRY_SUFFIX = "\n\n(직전 응답이 올바른 JSON 이 아니었다. JSON 객체 하나만 다시 출력하라.)"

_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_PLACEHOLDER = re.compile(r"\{\{\s*(\w+)\s*\}\}")
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


class LLMUnavailableError(RuntimeError):
    """LLM 을 쓸 수 없다(키 미설정·오프라인 모드). 호출부는 규칙 기반 폴백으로 간다."""


class LLMResponseError(RuntimeError):
    """재시도 후에도 응답을 JSON 으로 해석하지 못했다."""


# ---------------------------------------------------------------------------
# 공개 함수
# ---------------------------------------------------------------------------


def get_llm_provider() -> LLMProvider:
    """설정에 맞는 provider 를 돌려준다. 쓸 수 없으면 `LLMUnavailableError`."""
    settings = get_settings()
    if settings.llm_offline:
        raise LLMUnavailableError("LLM_OFFLINE=1 — 오프라인 모드입니다.")
    if not settings.anthropic_api_key:
        raise LLMUnavailableError("ANTHROPIC_API_KEY 가 설정되지 않았습니다.")
    return _anthropic_provider(settings.anthropic_api_key, settings.anthropic_model)


def render_prompt(prompt_name: str, /, **values: object) -> tuple[str, str]:
    """`prompts/<name>.md` 를 읽어 (system, user) 로 나누고 `{{변수}}` 를 채운다.

    파일은 `# System` / `# User` 두 절로 이뤄진다. HTML 주석(작성자 메모)은 제거한다.
    채우지 않은 변수가 남으면 프롬프트 버그이므로 즉시 알린다.
    """
    raw = _COMMENT.sub("", (PROMPT_DIR / f"{prompt_name}.md").read_text(encoding="utf-8"))
    system_part, _, user_part = raw.partition("# User")
    system = system_part.replace("# System", "", 1).strip()

    def fill(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in values:
            raise KeyError(f"프롬프트 {prompt_name}.md 의 변수 {{{{{key}}}}} 값이 없습니다")
        return str(values[key])

    return system, _PLACEHOLDER.sub(fill, user_part).strip()


def complete_json(
    provider: LLMProvider,
    prompt: str,
    *,
    system: str | None = None,
    max_tokens: int = 1500,
    use_cache: bool = True,
) -> dict:
    """LLM 을 불러 JSON 객체를 돌려준다. 파싱 실패 시 1회 재시도, 동일 입력은 캐시."""
    key = _cache_key(provider, system, prompt)
    if use_cache and (cached := _load_cache(key)) is not None:
        return cached

    for attempt in (1, 2):
        text = prompt if attempt == 1 else prompt + _RETRY_SUFFIX
        completion = provider.complete(text, system=system, max_tokens=max_tokens, temperature=0)
        try:
            data = parse_json_object(completion.text)
        except ValueError as exc:
            logger.warning("LLM JSON 파싱 실패(%d회차): %s", attempt, exc)
            continue
        if use_cache:
            _save_cache(key, data)
        return data
    raise LLMResponseError("LLM 응답을 두 번 연속 JSON 으로 해석하지 못했습니다.")


def parse_json_object(text: str) -> dict:
    """응답 텍스트에서 JSON 객체 하나를 꺼낸다. 코드펜스·앞뒤 잡음은 허용한다."""
    cleaned = _FENCE.sub("", text.strip())
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("JSON 객체를 찾지 못했습니다")
    try:
        data = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON 문법 오류: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("최상위가 객체가 아닙니다")
    return data


# ---------------------------------------------------------------------------
# Provider 구현체
# ---------------------------------------------------------------------------


class AnthropicProvider:
    """Anthropic Messages API 직접 호출 구현체(`LLMProvider` 프로토콜 충족)."""

    name = "anthropic"

    def __init__(self, api_key: str, model: str) -> None:
        import anthropic  # SDK 는 실제로 쓸 때만 import 한다(테스트 속도)

        self._api_error = anthropic.APIError
        self._client = anthropic.Anthropic(api_key=api_key, timeout=30.0, max_retries=2)
        self.model = model

    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> LLMCompletion:
        """프롬프트 1건을 보내고 텍스트 응답을 표준형으로 돌려준다.

        `temperature` 는 프로토콜 호환을 위해 받기만 하고 보내지 않는다. 현재 SDK(1.x)와
        모델이 샘플링 파라미터를 받지 않는다(9/27 실호출에서 TypeError 확인).
        """
        del temperature  # 의도적으로 사용하지 않음 — 위 docstring 참조
        kwargs: dict = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system
        try:
            response = self._client.messages.create(**kwargs)
        except self._api_error as exc:
            # 네트워크·한도·서버 오류. 호출부가 규칙 기반 폴백으로 넘어가도록 변환한다.
            raise LLMUnavailableError(f"Anthropic API 호출 실패: {exc}") from exc
        text = "".join(block.text for block in response.content if block.type == "text")
        return LLMCompletion(
            text=text,
            model_id=response.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            finish_reason=response.stop_reason,
        )


@lru_cache(maxsize=2)
def _anthropic_provider(api_key: str, model: str) -> AnthropicProvider:
    """클라이언트를 요청마다 만들지 않도록 재사용한다."""
    return AnthropicProvider(api_key, model)


# ---------------------------------------------------------------------------
# 캐시 (LLM 결과는 우리 데이터라 저장 가능 — Google 응답과 다르다)
# ---------------------------------------------------------------------------


def _cache_key(provider: LLMProvider, system: str | None, prompt: str) -> str:
    """provider·모델·프롬프트가 같으면 같은 키."""
    model = getattr(provider, "model", "")
    raw = "\x1f".join([provider.name, model, system or "", prompt])
    return sha256(raw.encode("utf-8")).hexdigest()[:24]


def _cache_file(key: str) -> Path:
    """캐시 키 → 파일 경로."""
    return data_path(get_settings().cache_dir) / "llm" / f"{key}.json"


def _load_cache(key: str) -> dict | None:
    """캐시 적중 시 저장된 JSON, 아니면 None."""
    path = _cache_file(key)
    if not path.exists():
        return None
    logger.info("LLM 캐시 적중: %s", key)
    return json.loads(path.read_text(encoding="utf-8"))


def _save_cache(key: str, data: dict) -> None:
    """성공한 JSON 결과만 저장한다."""
    path = _cache_file(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
