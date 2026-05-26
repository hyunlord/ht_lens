# Phase 7a-3 — Plan (V2, post Codex debate)

> **V1 → V2 changelog**:
> - V1 had a critical bug: `from_env_embedding()` was called outside the try/except, so a `BgeM3Client()` init/download failure would abort `translate_command` (asymmetric with API lifespan fail-soft). V2 wraps the factory call in the same except.
> - V1 shipped `_FailingMockEmbeddingClient` behind `EMBEDDING_PROVIDER=mock_fail`, leaking a test fixture into production. V2 removes it; encode-level failure is replaced by an init-failure **unit test** (monkeypatch `from_env_embedding` to raise) which exercises the real production graceful-degradation path.
> - V1 redesigned the CLI output (`embedded=…`, `embed_skipped=…`, new `partial:` line). V2 keeps the existing `ok:` / `partial-failure` lines unchanged and prints embed status on a separate new line (`embed: …`), so existing substring checks are unaffected.
> - V1 wired the factory into a single caller (translate/cli). V2 wires it into all three caller sites (`translate/cli.py`, `cli.py::embed_command`, `api/app.py::_lifespan`) for consistency.
> - V1 subprocess test left `EMBEDDING_*` / `RAG_*` / `HF_*` env keys to leak from the operator shell. V2 helper filters them.
> - V1 had 4 tests; V2 has 7 subprocess + 1 unit = 8 tests (adds console-script equivalence, partial-failure-still-embeds, rerun-cleanliness, init-failure-unit).

## Goal
`ht-lens translate --doc-id N` 명령이 `block_embeddings` 자동 backfill을 실행하도록 한다. `jobs/pipeline.py` (Phase 7a Fix c) 패턴을 CLI 경로에도 영구화. v1.6 마일스톤 (Phase 7a-2 + 7a-3) 완료.

## Context
- **Phase 7a Fix c** (`jobs/pipeline.py::process_upload_job`): translate 직후 `backfill(session, embedding_client, doc_id)` 호출. graceful skip on init/encode failure.
- **CLI 경로 미적용**: `translate_command`는 translate만, embed는 수동 `ht-lens embed`.
- **doc 6 ops 경험**: shell `&&` chain 워크어라운드 + HF_HOME 상속 사고 (settings.json 영구 fix 완료).
- **doc 7 (36K) 준비**: Phase 7a-2 + 7a-3 후 `nohup ht-lens translate --doc-id 7 --concurrency 7 & disown` 단일 명령.

사용자 결정 (Stage 1):
- **A**: `--no-embed` flag (기본 자동, 명시적 skip).
- **B**: Embed failure → warning log + exit code 0 (jobs/pipeline.py 패턴).
- **C**: Mock embedding client subprocess test (`EMBEDDING_PROVIDER=mock`).

## Scope

**In**:

### Sub-goal 1 — Embedding factory (3 caller wire-up)
- 새 파일 `src/ht_lens/embedding/factory.py`:
  - `from_env_embedding() -> EmbeddingClient | None`:
    - `RAG_DISABLED in (1,true,yes)` → `None` (caller가 skip + log).
    - `EMBEDDING_PROVIDER=mock` → `MockEmbeddingClient(dim=32)` (test/dev only).
    - 그 외 → `BgeM3Client()` (default, may download 2GB on first run; may raise on bad HF cache / offline / missing torch).
  - **No `_FailingMockEmbeddingClient`** (V1 removed). Failure injection is unit-level.
- 3 caller 모두 wire-up:
  - `src/ht_lens/translate/cli.py::translate_command` (Sub-goal 2).
  - `src/ht_lens/cli.py::embed_command` (replace inline `BgeM3Client()` with `from_env_embedding()`. `None` 반환 시 stderr "RAG_DISABLED" + exit 0).
  - `src/ht_lens/api/app.py::_lifespan` (replace inline `BgeM3Client()` + RAG_DISABLED check. lifespan은 이미 동등 logic이라 factory로 합쳐도 동일 동작. 단 `BgeM3Client init failure → warn + None` 부분은 V1 lifespan 패턴 그대로 유지).

### Sub-goal 2 — CLI translate auto-embed chain
- `translate_command`:
  - 새 typer option `no_embed: bool = typer.Option(False, "--no-embed/--embed", help=...)`. default False (auto-embed on).
  - translate 완료 후, `dry_run=False`이고 `no_embed=False`이면 **factory call + backfill call 모두 outer try/except 안에서**:
    ```python
    embed_summary = ""
    if dry_run:
        pass
    elif no_embed:
        embed_summary = "embed: skipped (--no-embed)"
    else:
        try:
            embedding_client = from_env_embedding()
            if embedding_client is None:
                embed_summary = "embed: skipped (RAG_DISABLED)"
            else:
                async with factory() as session:
                    ek = await backfill(session, embedding_client, doc_id=doc_id)
                embed_summary = (
                    f"embed: embedded={ek['embedded']} skipped={ek['skipped']}"
                )
        except Exception as exc:
            typer.echo(
                f"warning: auto-embed failed: {exc}. "
                f"Run 'ht-lens embed --doc-id {doc_id}' manually.",
                err=True,
            )
            embed_summary = "embed: failed (see stderr)"
    ```
  - 출력 위치: 기존 `ok:` 또는 partial-failure `warning:` 메시지 **다음 줄**에 `embed: ...` 별도 echo. 기존 ok/warning line은 글자 그대로 유지 (회귀 0).
  - Partial success (`stats.failed > 0`): exit code 1 유지. embed은 시도 (성공 block은 자연 embed; 실패 block은 `_candidate_blocks` 가 `status='translated'` filter라 제외).

### Sub-goal 3 — Tests (8개: 7 subprocess + 1 unit)
- 새 파일 `tests/integration/test_translate_cli_auto_embed.py`:
  - **subprocess helper `_run_translate_with_embed`**: 기존 `_run_translate`와 동일하지만 `EMBEDDING_*` / `RAG_*` / `HF_*` prefix도 filter.
  - **Test 1** `test_translate_cli_auto_embeds_with_mock_provider`: `LLM_PROVIDER=mock EMBEDDING_PROVIDER=mock`. exit 0, stdout `embed: embedded=3`, DB `block_embeddings` rows = 3.
  - **Test 2** `test_translate_cli_no_embed_flag_skips_embedding`: + `--no-embed`. exit 0, stdout `embed: skipped (--no-embed)`, embeddings = 0.
  - **Test 3** `test_translate_cli_rag_disabled_env_skips_embedding`: `RAG_DISABLED=1`. exit 0, stdout `embed: skipped (RAG_DISABLED)`, embeddings = 0.
  - **Test 4** `test_translate_console_script_auto_embeds`: 사용 가능 시 `ht-lens translate` (console script, not `python -m`). 검증 동일 (Codex §5b). venv 의존: console script 부재 시 `pytest.skip`.
  - **Test 5** `test_translate_cli_partial_failure_still_embeds_successful_blocks`: 일부 block fail 시 성공 block만 embed (Codex §5c). `TRANSLATE_LLM_PROVIDER=mock_partial` (또는 fixture로 일부 fail) + `EMBEDDING_PROVIDER=mock`. exit 1 (translate partial fail), stdout partial+embed 두 줄, DB translations status mixed, embeddings only for translated blocks. **fixture 결정**: 기존 `mock_fail` 은 모든 block fail. partial fail용으로 새 mock 또는 mid-block fail 방법 필요. 가장 단순한 방식: doc에 두 block, 하나는 mock LLM 성공 (정상 text), 다른 하나는 empty original_text 또는 length-zero block (translate가 자연 skip). 단 skip은 fail 아님. 대안: `MockLLMClient` subclass가 특정 input에 LLMPermanentError raise하도록 fixture 작성 (subprocess에서 env로 선택). 또는 **plan에서 결정**: test 5는 단위 test로 분리 — `translate_command` 직접 호출 + monkeypatched LLM/embedding. 그게 더 깔끔.
  - **Test 6** `test_translate_cli_rerun_clean_output`: 동일 doc 두 번째 호출. exit 0, stdout `embed: embedded=0 skipped=3` (Codex §5e). DB embeddings 변동 없음 (idempotent).
  - **Test 7** `test_embed_command_uses_factory_RAG_DISABLED`: `RAG_DISABLED=1` 으로 `ht-lens embed --doc-id N` 호출. Factory가 None 반환 → stderr warning + exit 0 또는 정의된 exit code. (factory wire-up 검증)
  - **Test 8** `test_translate_command_handles_factory_raise` (unit, not subprocess): `from_env_embedding`을 `RuntimeError` raise하도록 monkeypatch. `typer.testing.CliRunner` 또는 `asyncio.run(translate_command(...))` 직접 호출. 검증: translate stats 정상 + stderr warning + exit 0 (Codex §5a). production-relevant init failure path (BgeM3 import/HF cache 오류 등).

**Out**:
- `--retry-failed` stale embedding GC (Codex §3.2 — defer to separate phase, summary known limitation).
- ROADMAP §C (DB batch commit, Phase 7a-2 user-deferred).
- bge-m3 live download in CI (mock only).
- doc 7 강제 retranslate trigger (ops, 별도).
- `--retry-failed` semantics 변경 (기존 동작 유지).

## Approach

### 1. Factory
```python
# src/ht_lens/embedding/factory.py (NEW)
"""Embedding client factory — Phase 7a-3.

Wired into all three callers that build an EmbeddingClient:
- src/ht_lens/translate/cli.py::translate_command (Phase 7a-3, auto-embed chain)
- src/ht_lens/cli.py::embed_command (Phase 7a-3, consistency)
- src/ht_lens/api/app.py::_lifespan (Phase 7a-3, consistency)

Returns ``None`` when RAG_DISABLED so callers can short-circuit without
constructing BgeM3Client (no 2 GB download).
"""

from __future__ import annotations

import os

from ht_lens.embedding.service import (
    BgeM3Client,
    EmbeddingClient,
    MockEmbeddingClient,
)


def from_env_embedding() -> EmbeddingClient | None:
    """Build an embedding client from env.

    - ``RAG_DISABLED=1|true|yes`` → ``None`` (caller skips).
    - ``EMBEDDING_PROVIDER=mock`` → ``MockEmbeddingClient(dim=32)``
      (test/dev only — never set this in a production DB that already
      has 1024-dim bge-m3 rows; mixed-dim collisions degrade RAG).
    - default → ``BgeM3Client()`` (may download ~2 GB on first run).
    """
    if os.environ.get("RAG_DISABLED", "").lower() in ("1", "true", "yes"):
        return None
    if os.environ.get("EMBEDDING_PROVIDER", "").lower() == "mock":
        return MockEmbeddingClient(dim=32)
    return BgeM3Client()


__all__ = ["from_env_embedding"]
```

### 2. CLI translate auto-embed
- `--no-embed/--embed` 추가 (default False).
- 기존 ok/warning lines 그대로. 새 줄 `embed: ...` 추가.
- factory call + backfill call 모두 same try/except.
- dry_run에서는 embed skip (no translation rows produced).
- Partial-failure (`stats.failed > 0`) 시도 embed 수행 후 exit 1 raise.

### 3. embed_command wire-up
```python
# src/ht_lens/cli.py::embed_command — modified

async def _run() -> None:
    from ht_lens.embedding.factory import from_env_embedding
    client = from_env_embedding()
    if client is None:
        typer.echo(
            "error: RAG_DISABLED=1 — cannot run embed command", err=True
        )
        raise typer.Exit(code=5)
    engine = make_engine(db_path)
    factory = make_session_factory(engine)
    try:
        async with factory() as session:
            stats = await backfill(session, client, doc_id=doc_id, batch_size=batch_size)
        typer.echo(
            f"ok: doc_id={doc_id} candidates={stats['candidates']} "
            f"embedded={stats['embedded']} skipped={stats['skipped']}"
        )
    finally:
        await engine.dispose()
```

### 4. API lifespan wire-up
```python
# src/ht_lens/api/app.py::_lifespan — modified

app.state.embedding_client = None
try:
    from ht_lens.embedding.factory import from_env_embedding
    app.state.embedding_client = from_env_embedding()
    if app.state.embedding_client is not None:
        _log.info(
            "embedding client ready: %s (dim=%d)",
            app.state.embedding_client.model_name,
            app.state.embedding_client.dim,
        )
    else:
        _log.info("embedding disabled (RAG_DISABLED=1)")
except Exception as exc:
    _log.warning("embedding client init failed; cross-doc RAG disabled: %s", exc)
```

기존 동작과 동등 (try/except + RAG_DISABLED short-circuit), factory 호출만 추가.

### 5. Test 5 design decision
**Partial failure unit test design** (subprocess 어려움):
- 옵션 1: `mock_partial` LLM provider 추가 → production code pollution. Codex §1.2와 동일 문제.
- 옵션 2: Test 5를 **unit test로 변환** (subprocess 없이). `translate_command` 직접 호출, `from_env_translate`와 `from_env_embedding`을 monkeypatch. mock LLM은 첫 block에 LLMPermanentError, 나머지 정상. embedding은 MockEmbeddingClient. 검증: stats.failed == 1, stats.translated > 0, block_embeddings에 성공 block만 indexed.
- **plan V2 결정**: 옵션 2. Test 5 + Test 8 모두 unit test (CliRunner 사용). 다른 6개는 subprocess.

## File-level changes

| Path | Action | Note |
| ---- | ------ | ---- |
| `src/ht_lens/embedding/factory.py` | NEW | `from_env_embedding()` |
| `src/ht_lens/translate/cli.py` | MODIFY | `--no-embed` flag, factory call + backfill in outer try/except, new `embed: ...` output line |
| `src/ht_lens/cli.py` | MODIFY | `embed_command` uses factory. `None` → exit 5 |
| `src/ht_lens/api/app.py` | MODIFY | `_lifespan` uses factory (동등 동작) |
| `tests/integration/test_translate_cli_auto_embed.py` | NEW | 6 subprocess tests (1-4, 6, 7) |
| `tests/unit/test_translate_command_unit.py` | NEW (또는 통합) | 2 unit tests (5: partial failure, 8: init failure) |

## Dependencies (new)
없음.

## Test strategy

### Subprocess integration (new, 6 tests)
1. `test_translate_cli_auto_embeds_with_mock_provider` (env: LLM_PROVIDER=mock, EMBEDDING_PROVIDER=mock). exit 0, stdout `embed: embedded=3`, DB rows=3.
2. `test_translate_cli_no_embed_flag_skips_embedding` (LLM_PROVIDER=mock + --no-embed). exit 0, `embed: skipped (--no-embed)`, rows=0.
3. `test_translate_cli_rag_disabled_env_skips_embedding` (RAG_DISABLED=1). exit 0, `embed: skipped (RAG_DISABLED)`, rows=0.
4. `test_translate_console_script_auto_embeds` (`ht-lens` not `python -m`). 동일 검증. console script 부재 시 pytest.skip.
5. (moved to unit) — partial failure.
6. `test_translate_cli_rerun_clean_output`. 두 번째 호출 시 `embed: embedded=0 skipped=N`, embeddings 변동 0.
7. `test_embed_command_uses_factory_RAG_DISABLED`. `ht-lens embed --doc-id N` with RAG_DISABLED=1. exit code 5 + stderr "RAG_DISABLED=1".

### Unit (new, 2 tests)
8. `test_translate_command_partial_failure_still_embeds_successful_blocks` (CliRunner + monkeypatch LLM + embedding). 5 blocks, 3 ok + 2 fail. stats.failed==2, stats.translated==3, block_embeddings has 3 rows.
9. `test_translate_command_handles_factory_raise` (CliRunner + monkeypatch `from_env_embedding` raises RuntimeError). Translate 정상 + stderr warning + exit 0.

### 회귀 (existing 521 tests)
- `tests/integration/test_translate_cli.py` 17 tests: stdout 기존 ok/partial lines unchanged → "ok:" substring check (line 119, 457) 통과. exact-line match 없음 (확인됨).
- `test_embed_command_*` tests (있다면): factory 호출이 동등 동작이라 통과 기대.
- `test_pipeline_auto_embed.py`: 영향 없음 (`jobs/pipeline.py` 변경 X). lifespan만 factory 사용으로 변경 → app.state.embedding_client 동작 동일.
- 모든 API tests: lifespan factory 사용 후도 `MockEmbeddingClient` override 가능 (기존 test infrastructure).

### Verify 단계 smoke (optional, manual)
- `EMBEDDING_PROVIDER=mock` + local 작은 doc + `ht-lens translate --doc-id 1`. embed: 라인 출력 확인.

## DoD mapping

| DoD item | How to satisfy | Evidence plan |
| -------- | -------------- | ------------- |
| CLI translate auto-embed (default) | `translate_command`에 backfill chain (Sub-goal 2) | test 1 |
| `--no-embed` opt-out | typer flag | test 2 |
| `RAG_DISABLED=1` skip | factory returns None | test 3 |
| Console script equivalence | `ht-lens translate` 정상 (Codex §3.4) | test 4 |
| Partial failure still embeds | unit test 5 | unit 5 |
| Rerun clean | idempotent backfill | test 6 |
| embed_command factory wire-up | inline → factory | test 7 |
| Init failure graceful (Codex §2.1 critical fix) | factory call inside try/except | unit 9 |
| API lifespan factory wire-up | inline → factory | 기존 API tests 통과 + smoke |
| 회귀 0 (521 tests) | substring stdout, signature 동일 | full pytest |
| 521 → 529 tests pass | 8 new tests | full pytest |

## Risk / 주의

### Critical (V1 hazards resolved)
1. ~~BgeM3Client init failure aborts CLI~~ → factory call inside try/except (Codex §2.1)
2. ~~`_FailingMockEmbeddingClient` prod pollution~~ → removed; failure injection via unit-level monkeypatch (Codex §1.2)
3. ~~Factory single-caller inconsistency~~ → 3 caller wire-up (Codex §1.1, §4.2)
4. ~~CLI output redesign churn~~ → new line only, ok/warning untouched (Codex §1.3)
5. ~~subprocess env leak~~ → helper filters EMBEDDING_/RAG_/HF_ (Codex §2.2)

### Medium
6. **2GB download on first user run**: `ht-lens translate --doc-id 1` 처음 시 BgeM3Client init이 sentence-transformers 모델 다운로드. opt-out: `--no-embed` or `RAG_DISABLED=1`. CLI help text에 명시.
7. **mock dim=32 vs prod 1024 mixing**: subprocess tests use `tmp_path` (fresh DB). Production usage `EMBEDDING_PROVIDER=mock`은 의도된 위험 (env 명시).
8. **embed_command exit code change**: factory가 None 반환 시 exit 5. 기존 embed_command 사용자가 RAG_DISABLED 환경에서 호출하면 exit 5. 단 기존 동작은 BgeM3Client init이 무엇이든 시도 → 본 phase에서 `RAG_DISABLED` 명시적 처리 (defensible).

### Low
9. **`--retry-failed` stale embeddings**: Codex §3.2 defer. summary known limitation. failed→translated 전환 시 backfill이 자연 cover. failed→여전히 failed는 backfill skip (정합).
10. **API lifespan factory 도입**: 기존 `BgeM3Client init failure → warn + None` 동작 유지. 단 factory가 raise하면 기존 try/except가 catch. 영향 없음.

### Debate에서 다시 다룰 잠재 항목 (verify-cross에서 다룰 가능)
- API lifespan factory 통합이 정말 "동등 동작"인지 (RAG_DISABLED 처리가 lifespan vs factory에서 어디서 일어나는지 명확화).
- Unit test 5/9가 subprocess test와 동등한 confidence 제공하는지.
- `embed_command` exit code 5 변경이 backward-compat OK인지.
