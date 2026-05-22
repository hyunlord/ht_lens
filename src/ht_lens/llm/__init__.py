"""LLM client abstraction — Phase 2b OpenAICompatibleClient, Phase 6e split."""

from ht_lens.llm.client import (
    ChatLLMClient,
    LLMClient,
    Message,
    Role,
    TranslateLLMClient,
)
from ht_lens.llm.errors import (
    EmptyLLMResponseError,
    LLMError,
    LLMHealthCheckFailed,
    LLMPermanentError,
    LLMTransientError,
)
from ht_lens.llm.factory import from_env, from_env_chat, from_env_translate
from ht_lens.llm.mock import MockLLMClient

__all__ = [
    "ChatLLMClient",
    "EmptyLLMResponseError",
    "LLMClient",
    "LLMError",
    "LLMHealthCheckFailed",
    "LLMPermanentError",
    "LLMTransientError",
    "Message",
    "MockLLMClient",
    "Role",
    "TranslateLLMClient",
    "from_env",
    "from_env_chat",
    "from_env_translate",
]
