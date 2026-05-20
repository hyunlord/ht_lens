"""LLM client abstraction (Phase 2a).

Phase 2a only ships the :class:`LLMClient` Protocol and a deterministic
:class:`MockLLMClient`. Real providers (sglang/Ollama/OpenRouter) land in Phase
2b.
"""

from ht_lens.llm.client import LLMClient, Message, Role
from ht_lens.llm.factory import from_env
from ht_lens.llm.mock import MockLLMClient

__all__ = ["LLMClient", "Message", "MockLLMClient", "Role", "from_env"]
