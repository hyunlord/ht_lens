"""OpenAI-compatible LLM client (sglang / Ollama / OpenRouter).

Phase 2b default: sglang Qwen3.6-27B with ``enable_thinking=false``.
The ``extra_body`` field is sglang-specific; for other providers this
should be left empty (future factory extension).
"""

from __future__ import annotations

from typing import Any

import openai
from openai.types.chat import ChatCompletionMessageParam

from ht_lens.llm.client import LLMClient, Message
from ht_lens.llm.errors import (
    EmptyLLMResponseError,
    LLMHealthCheckFailed,
    LLMPermanentError,
    LLMTransientError,
)

_LANG_NAMES: dict[str, str] = {
    "en": "English",
    "ko": "Korean",
    "ja": "Japanese",
    "zh": "Chinese",
}


def _map_openai_error(exc: Exception) -> LLMTransientError | LLMPermanentError:
    if isinstance(exc, openai.APIStatusError):
        if exc.status_code >= 500:
            err: LLMTransientError | LLMPermanentError = LLMTransientError(str(exc))
            err.__cause__ = exc
            return err
        err = LLMPermanentError(str(exc))
        err.__cause__ = exc
        return err
    transient = LLMTransientError(str(exc))
    transient.__cause__ = exc
    return transient


class OpenAICompatibleClient:
    """Async LLM client for sglang / OpenAI-compatible endpoints.

    Implements the :class:`~ht_lens.llm.client.LLMClient` protocol.
    ``model_name`` is exposed as a plain attribute so callers can store
    provenance without widening the Protocol.
    """

    model_name: str

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str = "EMPTY",
        timeout: float = 60.0,
        max_retries: int = 0,
        enable_thinking: bool = False,
        # Phase 6e split: defaults preserved for pre-6e callers (live_llm_client,
        # test_health_check_live, test_translate_pipeline_live). Factories pass
        # explicit values: translate → 2048/0.0, chat → 4096/0.2.
        max_tokens: int = 2048,
        temperature: float = 0.7,
    ) -> None:
        self.model_name = model
        self._enable_thinking = enable_thinking
        self.max_tokens = max_tokens
        self.temperature = temperature
        self._client = openai.AsyncOpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=timeout,
            max_retries=max_retries,
        )

    # ------------------------------------------------------------------
    # LLMClient protocol
    # ------------------------------------------------------------------

    async def translate(
        self,
        text: str,
        src: str,
        tgt: str,
        *,
        context: str | None = None,
    ) -> str:
        system = self._translate_system(src, tgt)
        user = self._translate_user(text, context)
        try:
            response = await self._client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=self.temperature,
                top_p=0.80,
                presence_penalty=1.5,
                max_tokens=self.max_tokens,
                extra_body=self._extra_body(),
            )
        except Exception as exc:
            raise _map_openai_error(exc) from exc
        return _extract_safe(response)

    async def chat(
        self,
        messages: list[Message],
        *,
        system: str | None = None,
    ) -> str:
        openai_messages: list[ChatCompletionMessageParam] = []
        if system:
            sys_msg: ChatCompletionMessageParam = {"role": "system", "content": system}
            openai_messages.append(sys_msg)
        for m in messages:
            role = m["role"]
            content = m["content"]
            if role == "system":
                msg: ChatCompletionMessageParam = {"role": "system", "content": content}
            elif role == "assistant":
                msg = {"role": "assistant", "content": content}
            else:
                msg = {"role": "user", "content": content}
            openai_messages.append(msg)
        try:
            response = await self._client.chat.completions.create(
                model=self.model_name,
                messages=openai_messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                extra_body=self._extra_body(),
            )
        except Exception as exc:
            raise _map_openai_error(exc) from exc
        return _extract_safe(response)

    async def health_check(self) -> bool:
        """Ping the endpoint and verify ``reasoning_tokens == 0`` (thinking-off regression)."""
        try:
            response = await self._client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": "Reply with 'ok'"}],
                max_tokens=8,
                temperature=0,
                extra_body=self._extra_body(),
            )
            content = _content_str(response.choices[0].message.content)
            if not content:
                raise LLMHealthCheckFailed("health_check: empty response")
            reasoning = _reasoning_tokens(response)
            if reasoning > 0:
                raise LLMHealthCheckFailed(
                    f"health_check: reasoning_tokens={reasoning} — "
                    "enable_thinking may be ON (chat template regression)"
                )
            return True
        except LLMHealthCheckFailed:
            raise
        except Exception as exc:
            raise LLMHealthCheckFailed(str(exc)) from exc

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _extra_body(self) -> dict[str, Any]:
        return {"chat_template_kwargs": {"enable_thinking": self._enable_thinking}}

    @staticmethod
    def _translate_system(src: str, tgt: str) -> str:
        # Phase 6f-5: en→ko routes get a Korean-instruction prompt that
        # was A/B-validated against the prior generic English prompt:
        #   - qwen3.6-27b: KR 0.867 (legacy) → 0.874 (v2_ko), AllKor 55→65%
        #   - gemma-4-26b-a4b-it: KR 0.546 → 0.755, AllKor 0→25%
        # Other language pairs (ko→en, en→ja, etc.) keep the generic
        # English prompt — this is the documented backward-compat path
        # for non-Korean targets. Codes are lower/stripped so "EN" / " ko"
        # still hit the v2_ko branch (Codex debate §2).
        src_norm = (src or "").strip().lower()
        tgt_norm = (tgt or "").strip().lower()
        if src_norm == "en" and tgt_norm == "ko":
            return (
                "다음 영어 텍스트를 자연스러운 한국어로 번역하세요.\n\n"
                "규칙:\n"
                "- 모든 내용을 한국어로 번역합니다.\n"
                "- 기술 용어는 표준 한국어 번역을 사용합니다 "
                "(예: gradient descent → 경사 하강법).\n"
                "- 다음만 영어 유지: 고유명사 (GPT-4 등), 수식 ($...$), 코드, URL, arXiv ID.\n"
                "- 번역문만 출력합니다. 설명 없음."
            )
        src_name = _LANG_NAMES.get(src, src)
        tgt_name = _LANG_NAMES.get(tgt, tgt)
        return (
            f"You translate {src_name} to {tgt_name}. "
            "Output only the translation. "
            "Preserve technical terms, acronyms, numbers, and markdown structure "
            "(bold, italic, lists, code). "
            "Do not add explanations, quotes, or preamble."
        )

    @staticmethod
    def _translate_user(text: str, context: str | None) -> str:
        if context:
            return (
                f"Context (for reference, do not translate):\n{context}"
                f"\n\n---\n\nTranslate:\n{text}"
            )
        return text


# ------------------------------------------------------------------
# Module-level helpers (used by tests)
# ------------------------------------------------------------------


def _content_str(raw: str | list[Any] | None) -> str:
    """Normalise ``message.content`` to a plain string.

    Handles ``None``, plain ``str``, and content-list formats
    (some providers / SDK versions return segmented content).
    """
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw.strip()
    # Content list: extract text parts
    parts: list[str] = []
    for item in raw:
        if isinstance(item, dict):
            text = item.get("text", "")
        elif hasattr(item, "text"):
            text = item.text or ""
        else:
            text = str(item)
        parts.append(text)
    return "".join(parts).strip()


def _reasoning_tokens(response: Any) -> int:
    """Extract reasoning_tokens from usage, defaulting to 0."""
    usage = getattr(response, "usage", None)
    if usage is None:
        return 0
    rt = getattr(usage, "reasoning_tokens", None)
    if rt is not None:
        return int(rt)
    details = getattr(usage, "completion_tokens_details", None)
    if details is not None:
        return int(getattr(details, "reasoning_tokens", 0) or 0)
    return 0


def _extract_safe(response: Any) -> str:
    """Extract content string from a chat completion response with safety guards.

    Raises:
        EmptyLLMResponseError: on ``finish_reason="length"`` (truncated),
            ``None`` content, or empty/whitespace-only content.
    """
    choice = response.choices[0]
    finish = choice.finish_reason

    if finish == "length":
        raise LLMTransientError(
            f"finish_reason='length' — response was truncated "
            f"(model={getattr(response, 'model', '?')})"
        )

    content = _content_str(choice.message.content)
    if not content:
        raise EmptyLLMResponseError(f"empty content after extraction (finish_reason={finish!r})")
    return content


# Satisfy the LLMClient Protocol at static-analysis time.
def _assert_protocol() -> None:
    _: LLMClient = OpenAICompatibleClient.__new__(OpenAICompatibleClient)


__all__ = ["OpenAICompatibleClient", "_content_str", "_extract_safe", "_reasoning_tokens"]
