"""LLM client abstraction — Phase 2b adds OpenAICompatibleClient."""

from ht_lens.llm.client import LLMClient, Message, Role
from ht_lens.llm.errors import (
    EmptyLLMResponseError,
    LLMError,
    LLMHealthCheckFailed,
    LLMPermanentError,
    LLMTransientError,
)
from ht_lens.llm.factory import from_env
from ht_lens.llm.mock import MockLLMClient

__all__ = [
    "EmptyLLMResponseError",
    "LLMClient",
    "LLMError",
    "LLMHealthCheckFailed",
    "LLMPermanentError",
    "LLMTransientError",
    "Message",
    "MockLLMClient",
    "Role",
    "from_env",
]
