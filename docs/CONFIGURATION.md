# Configuration

ht_lens reads runtime config from environment variables (or a repo-root
`.env` file via `python-dotenv`). Phase 6e introduced a translate / chat
split — these can be configured independently.

## LLM clients (Phase 6e split)

The lifespan builds two LLM clients on startup:

| Client | Used by | Default `max_tokens` | Default `temperature` |
| ------ | ------- | -------------------- | --------------------- |
| translate | `translate_document`, `POST /blocks/{id}/retranslate`, `ht-lens translate` CLI | 2048 | 0.0 |
| chat | `POST /threads/{id}/explain`, `POST /messages`, `POST /documents/{id}/summarize`, `process_upload_job` summarize stage | 4096 | 0.2 |

`max_tokens=2048` for translate comes from the Phase E1 distribution
measurement (`~/llm_eval/`) — max observed Korean token count is 1513,
with 99.9% of blocks under 803 tokens. 2048 gives a 35% safety margin.

### Environment variables

Each client has its own scoped prefix; legacy `LLM_*` vars are used as
a fallback when the scoped key is unset (or empty/whitespace).

| Setting | Translate var | Chat var | Legacy fallback |
| ------- | ------------- | -------- | --------------- |
| Provider | `TRANSLATE_LLM_PROVIDER` | `CHAT_LLM_PROVIDER` | `LLM_PROVIDER` |
| Base URL | `TRANSLATE_LLM_BASE_URL` | `CHAT_LLM_BASE_URL` | `LLM_BASE_URL` |
| Model name | `TRANSLATE_LLM_MODEL` | `CHAT_LLM_MODEL` | `LLM_MODEL` |
| API key | `TRANSLATE_LLM_API_KEY` | `CHAT_LLM_API_KEY` | `LLM_API_KEY` |
| Max output tokens | `TRANSLATE_LLM_MAX_TOKENS` | `CHAT_LLM_MAX_TOKENS` | `LLM_MAX_TOKENS` |
| Temperature | `TRANSLATE_LLM_TEMPERATURE` | `CHAT_LLM_TEMPERATURE` | `LLM_TEMPERATURE` |
| HTTP timeout (sec) | `TRANSLATE_LLM_TIMEOUT` | `CHAT_LLM_TIMEOUT` | `LLM_TIMEOUT` |

Supported provider values: `mock`, `mock_fail`, `openai_compat`
(sglang / Ollama / OpenRouter via the OpenAI-compatible API).

> **Note on `mock_fail` asymmetry.** `FailMockLLMClient` raises
> `LLMPermanentError` from ``translate()`` only — its ``chat()`` method
> inherits the working `MockLLMClient` implementation. Setting
> `CHAT_LLM_PROVIDER=mock_fail` therefore does NOT inject chat-side
> failures (the chat path continues to succeed). Use it as a
> translate-side failure-injection knob (subprocess CLI tests rely on
> this — see `tests/integration/test_translate_cli.py`). For
> chat-side failure injection, patch ``ChatLLMClient`` directly at the
> test level (e.g. ``make_test_client(chat_llm_override=...)``).

### Precedence (per key, independent)

1. Scoped var (`TRANSLATE_LLM_*` or `CHAT_LLM_*`) — wins if set to a
   non-empty value.
2. Legacy var (`LLM_*`).
3. Default (built into the factory) — **except for `*_PROVIDER`**,
   which fails closed (Phase 6e-2).

An empty or whitespace-only scoped value (e.g. `TRANSLATE_LLM_MODEL=""`)
is treated as "not set" and falls through to the legacy slot — this is
intentional so a stray export cannot replace a working `LLM_MODEL` with
garbage.

### Provider resolution is fail-closed (Phase 6e-2)

Unlike the other keys, `TRANSLATE_LLM_PROVIDER` / `CHAT_LLM_PROVIDER` /
`LLM_PROVIDER` have **no built-in default**. If none of the three is
set to a non-empty value, `from_env_translate()` /  `from_env_chat()`
raise `LLMConfigurationError` (CLI exit code 5).

Why: prior versions silently fell back to `mock`, which let
``ht-lens translate`` pollute the database with `MockLLMClient`'s
``[KO] <english>`` output when the operator forgot to export env vars
**and** the repo `.env` was not picked up (e.g. CLI ran without a
loader, or `.env` was missing). The fail-closed behavior surfaces the
misconfiguration immediately instead.

To intentionally select mock for tests or local development, **export
the provider explicitly**:

```bash
LLM_PROVIDER=mock  # or TRANSLATE_LLM_PROVIDER=mock, etc.
```

The repo-root `.env` is auto-loaded by both the API server
(`create_app()`) and the translate CLI (`translate_command()`); see
[Phase 6e-2 plan / challenge](../.claude/phases/phase-6e-2/) for the
loader/launcher boundary.

### Migration from pre-6e

If `.env` only has `LLM_*` vars (Phase 2b style), the split factory
falls back to them and both clients share the same backend. No code
changes required — adding `TRANSLATE_LLM_*` or `CHAT_LLM_*` later is
opt-in.

### Examples

**Single-backend (current default)**

```bash
LLM_PROVIDER=openai_compat
LLM_BASE_URL=http://localhost:8081/v1
LLM_MODEL=qwen3.6-27b
```

Both clients route to qwen3.6-27b with the phase defaults
(translate: 2048/0.0, chat: 4096/0.2).

**Different model for chat-only**

```bash
LLM_PROVIDER=openai_compat
LLM_BASE_URL=http://localhost:8081/v1
LLM_MODEL=qwen3.6-27b
CHAT_LLM_MODEL=qwen3.6-instruct
```

translate keeps qwen3.6-27b, chat path swaps to qwen3.6-instruct.

**Split across two backends**

```bash
TRANSLATE_LLM_PROVIDER=openai_compat
TRANSLATE_LLM_BASE_URL=http://translate-sglang:8081/v1
TRANSLATE_LLM_MODEL=hy-mt2-7b

CHAT_LLM_PROVIDER=openai_compat
CHAT_LLM_BASE_URL=http://chat-sglang:8082/v1
CHAT_LLM_MODEL=qwen3.6-27b
```

### Health check semantics

`lifespan` runs `health_check()` on **both** clients at startup. If
either fails (or returns `False`), the app does not start. Same-backend
configs cost ~10 ms extra for the duplicate ping; cross-backend configs
gate startup on both reachable.

Set `HT_LENS_SKIP_LLM_CHECK=1` to bypass (used by integration tests).

## Other configuration

- `HT_LENS_DB_URL` — `sqlite+aiosqlite:///<path>` (default `data/ht_lens.db`)
- `HT_LENS_LOG_LEVEL` — Python logging level (default `INFO`)
- `LLM_CHAT_CONCURRENCY` — max parallel `/messages` calls (default 2, min 1)
