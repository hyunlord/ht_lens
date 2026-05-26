# Phase 7a-3 — Plan

## Goal
`ht-lens translate --doc-id N` 명령이 `block_embeddings` 자동 backfill을 실행하도록 한다. `jobs/pipeline.py` (Phase 7a Fix c)가 upload chain에 적용한 패턴을 CLI 경로에도 영구화. v1.6 마일스톤 (Phase 7a-2 + 7a-3) 완료.

## Context
- **Phase 7a Fix c**: API upload chain (`jobs/pipeline.py::process_upload_job`)이 translate 직후 `backfill(session, embedding_client, doc_id=...)` 호출. RAG_DISABLED=1 또는 model init 실패 시 graceful skip.
- **CLI 경로 미적용**: `src/ht_lens/translate/cli.py::translate_command`는 `translate_document` 만 호출. embed는 별도 명령 (`ht-lens embed --doc-id N`)으로 수동 chain 필요.
- **doc 6 (2026-05-26) 실제 ops 경험**: `nohup bash -c 'ht-lens translate ... && ht-lens embed ...' & disown` 워크어라운드. 그 도중 HF_HOME 환경변수 상속 사고 발생 (settings.json 영구 fix 별도 완료).
- **doc 7 (Murphy PML, 36K) 준비**: Phase 7a-2 fix로 c=7 throughput 5~7x. 이제 단일 명령 `nohup ht-lens translate --doc-id 7 --concurrency 7 & disown`이면 충분.

사용자 결정 3개 (Stage 1):
- **A**: `--no-embed` flag (기본 자동, 명시적 skip)
- **B**: Embed 실패 시 warning log + exit code 0 (jobs/pipeline.py 패턴)
- **C**: Mock embedding client subprocess test (`EMBEDDING_PROVIDER=mock` env 도입)

## Scope

**In**:

### Sub-goal 1 — CLI auto-embed chain
- `src/ht_lens/translate/cli.py::translate_command`:
  - 새 typer option `no_embed: bool = typer.Option(False, "--no-embed/--embed", ...)`. default False (auto-embed on).
  - `_run()` 안에서 `translate_document(...)` 완료 후, `no_embed=False`이고 `dry_run=False`이면 `backfill(session, embedding_client, doc_id=doc_id)` 호출.
  - Embedding client 생성: 새 helper `from_env_embedding()` (factory 패턴, LLM과 동일 디자인).
    - `RAG_DISABLED=1/true/yes` env → `None` 반환 (CLI는 skip + log).
    - `EMBEDDING_PROVIDER=mock` env → `MockEmbeddingClient(dim=32)` (test/dev).
    - `EMBEDDING_PROVIDER=mock_fail` env → failure-injection variant (test).
    - 그 외 → `BgeM3Client()` (default, 2GB 다운로드 가능).
  - Graceful degradation: embed 실패 시 `typer.echo(f"warning: auto-embed failed: {exc}. Run 'ht-lens embed --doc-id {doc_id}' manually.", err=True)` + exit code 0 유지.
  - dry_run 모드에서는 embed skip (translate가 LLM call 안 함 → translation row 없음 → embed 대상도 없음).
  - 부분 실패 (`stats.failed > 0`) 시: 기존 동작 (warning + exit 1) 유지하되 embed 시도. translate 성공 block은 embed 되어야 함. **단** exit code 1 유지 → caller가 부분 실패 인지 가능.
- 출력 메시지에 embed 결과 포함:
  - 성공: `ok: doc_id=... translated=... cached=... skipped=... failed=... embedded=... embed_skipped=...`
  - skip (--no-embed / RAG_DISABLED): `... (embed skipped: <reason>)` 추가.
  - 실패: 기존 ok line + stderr warning.

### Sub-goal 2 — Embedding factory
- 새 파일: `src/ht_lens/embedding/factory.py`
  - `from_env_embedding() -> EmbeddingClient | None`:
    - `RAG_DISABLED in (1,true,yes)` → None.
    - `EMBEDDING_PROVIDER=mock` → `MockEmbeddingClient(dim=32)`.
    - `EMBEDDING_PROVIDER=mock_fail` → `_FailingMockEmbeddingClient(dim=32)` (encode raise).
    - default → `BgeM3Client()`.
- API lifespan refactor는 out of scope (현재 inline `BgeM3Client()` 유지). 향후 별도 phase에서 통합 가능.

### Sub-goal 3 — Tests (subprocess pattern, 결정 C)
- 새 파일: `tests/integration/test_translate_cli_auto_embed.py`
  - **Test 1 — auto-embed**: `LLM_PROVIDER=mock EMBEDDING_PROVIDER=mock`. exit 0, stdout `embedded=3`, DB rows = 3.
  - **Test 2 — `--no-embed`**: `LLM_PROVIDER=mock` + `--no-embed` flag. exit 0, stdout `embed skipped: --no-embed`, DB rows = 0.
  - **Test 3 — embed failure**: `LLM_PROVIDER=mock EMBEDDING_PROVIDER=mock_fail`. **exit 0** (translate ok), stderr "auto-embed failed", DB translations 정상, embeddings = 0.
  - **Test 4 — `RAG_DISABLED=1`**: `LLM_PROVIDER=mock RAG_DISABLED=1`. exit 0, stdout `embed skipped: RAG_DISABLED`, embeddings = 0.

**Out**:
- API lifespan refactor to use `from_env_embedding()`.
- ROADMAP §C (DB batch commit) — Phase 7a-2 사용자 결정으로 deferred.
- bge-m3 live download in CI (mock만 사용).
- doc 7 강제 retranslate trigger (별도 ops).
- 새 exit code (결정 B로 기존 체계 유지).
- ROADMAP / CHANGELOG 갱신 (사람).

## Approach

### 1. `from_env_embedding()` helper
```python
# src/ht_lens/embedding/factory.py (NEW)
"""Embedding client factory — mirrors llm/factory.py pattern.

CLI translate auto-embed (Phase 7a-3) uses this to construct an
EmbeddingClient from env. Returns None when RAG is disabled so the
caller can short-circuit without instantiating BgeM3Client.
"""

from __future__ import annotations

import os
from typing import Any

from ht_lens.embedding.service import (
    BgeM3Client,
    EmbeddingClient,
    MockEmbeddingClient,
)


def from_env_embedding() -> EmbeddingClient | None:
    """Build an embedding client from env. Returns ``None`` when disabled.

    - ``RAG_DISABLED=1|true|yes`` → ``None`` (caller skips embed).
    - ``EMBEDDING_PROVIDER=mock`` → ``MockEmbeddingClient(dim=32)``.
    - ``EMBEDDING_PROVIDER=mock_fail`` → failure-injection client whose
      ``encode()`` raises. Used by CLI test 3 to lock the graceful
      degradation path.
    - default → ``BgeM3Client()`` (may download ~2 GB on first run).
    """
    if os.environ.get("RAG_DISABLED", "").lower() in ("1", "true", "yes"):
        return None
    provider = os.environ.get("EMBEDDING_PROVIDER", "").lower()
    if provider == "mock":
        return MockEmbeddingClient(dim=32)
    if provider == "mock_fail":
        return _FailingMockEmbeddingClient(dim=32)
    return BgeM3Client()


class _FailingMockEmbeddingClient(MockEmbeddingClient):
    """Failure-injection variant for ``EMBEDDING_PROVIDER=mock_fail``.

    Test-only fixture: kept in the factory module (not under tests/) so
    subprocess tests can select it via env var without packaging tests/
    into the runtime. Production code paths never reach this class
    unless ``EMBEDDING_PROVIDER=mock_fail`` is explicitly set.
    """

    def encode(self, texts: Any) -> Any:  # noqa: ARG002 — failure stub
        raise RuntimeError("simulated embedding failure (EMBEDDING_PROVIDER=mock_fail)")


__all__ = ["from_env_embedding"]
```

### 2. CLI translate auto-embed chain (sketch)
```python
# src/ht_lens/translate/cli.py — translate_command modified

def translate_command(
    doc_id: int = typer.Option(..., "--doc-id", ...),
    concurrency: int = typer.Option(7, "--concurrency", ...),
    max_retries: int = typer.Option(3, "--max-retries", min=0),
    retry_failed: bool = typer.Option(False, "--retry-failed/--no-retry-failed", ...),
    dry_run: bool = typer.Option(False, "--dry-run/--no-dry-run", ...),
    no_embed: bool = typer.Option(  # NEW
        False,
        "--no-embed/--embed",
        help=(
            "Skip the post-translate auto-embed step (Phase 7a-3). "
            "Auto-embed runs by default; this flag opts out."
        ),
    ),
    db: Path | None = typer.Option(None, "--db", ...),
) -> None:
    from ht_lens.dotenv_loader import load_repo_dotenv
    load_repo_dotenv()

    from ht_lens.db.session import make_engine, make_session_factory
    from ht_lens.embedding.backfill import backfill
    from ht_lens.embedding.factory import from_env_embedding
    from ht_lens.llm.errors import LLMConfigurationError
    from ht_lens.llm.factory import from_env_translate
    from ht_lens.translate.pipeline import translate_document

    db_path = db if db is not None else _db_path_from_env()
    try:
        llm = from_env_translate()
    except LLMConfigurationError as exc:
        typer.echo(f"error: LLM not configured: {exc}", err=True)
        raise typer.Exit(code=5) from exc

    async def _run() -> None:
        if not dry_run:
            await llm.health_check()

        engine = make_engine(db_path)
        factory = make_session_factory(engine)
        try:
            async with factory() as session:
                stats = await translate_document(
                    doc_id, session, llm,
                    concurrency=concurrency,
                    max_retries=max_retries,
                    retry_failed=retry_failed,
                    dry_run=dry_run,
                )

            # Phase 7a-3: post-translate auto-embed (skip on dry_run/--no-embed)
            embed_summary = ""
            if dry_run:
                pass  # no translation rows produced; nothing to embed
            elif no_embed:
                embed_summary = " (embed skipped: --no-embed)"
            else:
                embedding_client = from_env_embedding()
                if embedding_client is None:
                    embed_summary = " (embed skipped: RAG_DISABLED)"
                else:
                    try:
                        async with factory() as session:
                            ek = await backfill(
                                session, embedding_client, doc_id=doc_id
                            )
                        embed_summary = (
                            f" embedded={ek['embedded']} "
                            f"embed_skipped={ek['skipped']}"
                        )
                    except Exception as exc:
                        typer.echo(
                            f"warning: auto-embed failed: {exc}. "
                            f"Run 'ht-lens embed --doc-id {doc_id}' manually.",
                            err=True,
                        )
                        embed_summary = " (embed failed: see stderr)"

            if not dry_run and stats.failed > 0:
                typer.echo(
                    f"warning: {stats.failed} block(s) failed translation",
                    err=True,
                )
                typer.echo(
                    f"partial: doc_id={stats.document_id} "
                    f"translated={stats.translated} cached={stats.cached} "
                    f"skipped={stats.skipped} failed={stats.failed}"
                    f"{embed_summary}"
                )
                raise typer.Exit(code=1)
            if dry_run:
                total = stats.translated + stats.cached
                typer.echo(
                    f"dry_run: doc_id={stats.document_id} total={total} "
                    f"cache_hits={stats.cached} "
                    f"estimated_llm_calls={stats.translated}"
                )
            else:
                typer.echo(
                    f"ok: doc_id={stats.document_id} "
                    f"translated={stats.translated} cached={stats.cached} "
                    f"skipped={stats.skipped} failed={stats.failed}"
                    f"{embed_summary}"
                )
        finally:
            await engine.dispose()

    try:
        asyncio.run(_run())
    except typer.Exit:
        raise
    # ... rest of existing exception handlers unchanged
```

#### Design notes
- **Order**: translate → embed. Same as jobs/pipeline.py.
- **Session separation**: translate가 자체 session, embed는 새 session (factory()). 명확한 transaction 분리.
- **Partial success**: `stats.failed > 0`여도 embed 시도. backfill은 idempotent + `status='translated'` rows만 처리하므로 실패한 block은 자연 skip. Exit 1은 유지 (translate failure signal).
- **dry_run**: translate가 LLM call 안 함 + Translation row 안 생김 → embed 시도해도 candidates 0. 명시적 skip해서 incidental BgeM3Client init (2GB) 회피.
- **Backward compat**: 기존 사용자 `ht-lens translate --doc-id 1` 호출 시 추가로 embed 실행. 첫 use 시 2GB download. 명시적 skip은 `--no-embed`. CLI help text에 명시.

### 3. Existing test format check
`tests/integration/test_translate_cli.py`의 17 tests 중 stdout format match 검증하는 곳:
- `f"translated=` substring check가 다수. 추가된 `embedded=` 토큰은 영향 없음 (substring 끝부분만 추가).
- exact-line match는 없음 (확인 필요).
- **Plan finalize 전 확인**: implementation 직전 `grep "translated=" tests/integration/test_translate_cli.py` 로 재확인. 회귀가 있으면 fix.

## File-level changes

| Path | Action | Note |
| ---- | ------ | ---- |
| `src/ht_lens/embedding/factory.py` | NEW | `from_env_embedding()` + `_FailingMockEmbeddingClient` |
| `src/ht_lens/translate/cli.py` | MODIFY | `--no-embed` flag + auto-embed chain + ok-line `embed_summary` |
| `tests/integration/test_translate_cli_auto_embed.py` | NEW | 4 subprocess tests (auto, --no-embed, embed-fail, RAG_DISABLED) |
| `tests/integration/test_translate_cli.py` | MAYBE | 기존 17 tests stdout 검증 영향 시 minor update |

## Dependencies (new)
없음. 기존 `MockEmbeddingClient`, `BgeM3Client`, `backfill`, `typer` 모두 재사용.

## Test strategy

### Subprocess integration (new, 4 tests)
1. **`test_translate_cli_auto_embeds_with_mock_provider`**:
   - DB seed: 1 doc, 1 page, 3 text blocks (each ≥ 30 chars to pass backfill filter).
   - env: `LLM_PROVIDER=mock EMBEDDING_PROVIDER=mock HT_LENS_DB_URL=sqlite+aiosqlite:///<tmp>`.
   - subprocess: `python -m ht_lens translate --doc-id 1 --concurrency 2`.
   - assert: exit 0, stdout contains `embedded=3`, post-run DB has 3 `block_embeddings` rows.
2. **`test_translate_cli_no_embed_flag_skips_embedding`**:
   - 동일 seed.
   - env: `LLM_PROVIDER=mock` (no EMBEDDING_PROVIDER).
   - subprocess: `... --no-embed`.
   - assert: exit 0, stdout contains `embed skipped: --no-embed`, `block_embeddings` empty.
3. **`test_translate_cli_embed_failure_does_not_fail_translate`**:
   - 동일 seed.
   - env: `LLM_PROVIDER=mock EMBEDDING_PROVIDER=mock_fail`.
   - subprocess.
   - assert: **exit 0** (translate ok), stderr contains `auto-embed failed`, stdout contains `embed failed`, DB translations rows = 3, `block_embeddings` empty.
4. **`test_translate_cli_rag_disabled_env_skips_embedding`**:
   - 동일 seed.
   - env: `LLM_PROVIDER=mock RAG_DISABLED=1`.
   - subprocess.
   - assert: exit 0, stdout contains `embed skipped: RAG_DISABLED`, `block_embeddings` empty.

### 회귀 (existing 521 tests)
- `tests/integration/test_translate_cli.py`의 기존 17 tests: stdout format 변경 (ok line에 `embed_summary` 추가) 영향 확인. 대부분 substring 검증이라 OK 예상. 정확한 영향은 implementation 직전 grep 으로 확인 후 필요 시 update.
- `jobs/pipeline.py` 경로 (`test_pipeline_auto_embed.py`): 영향 없음 (이 파일 변경 안 함).

### Verify 단계 smoke test (manual, 선택)
- `EMBEDDING_PROVIDER=mock` + local 작은 doc 강제 retranslate. log 출력 확인. CI는 자동 test 4개로 충분하므로 optional.

## DoD mapping

| DoD item | How to satisfy | Evidence plan |
| -------- | -------------- | ------------- |
| CLI translate auto-embed (default) | `translate_command`에 backfill chain | test 1 (`embedded=N` 토큰 + DB rows) |
| `--no-embed` opt-out | typer flag | test 2 (skip log + 0 rows) |
| Graceful degradation on embed failure | try/except, exit code 0 | test 3 (exit 0 + stderr warning) |
| `RAG_DISABLED=1` skip | factory return None | test 4 |
| Backward compat | flag default False = auto, signature 동일 (새 flag만 추가) | 기존 17 tests 통과 |
| 521 → 525 tests pass | 새 4 tests | `uv run pytest -m "not llm and not slow" -q --no-cov \| tail -3` |
| Documentation | CLI help text + module docstring | summary.md |

## Risk / 주의

### Medium
1. **기존 stdout format 변경**: ok line에 `embed_summary` 추가. 기존 test가 substring 검증이면 OK. exact-line match면 update. implementation 직전 grep 으로 확인.
2. **첫 use 시 2GB download**: 기존 사용자 `ht-lens translate --doc-id 1` 처음 실행 시 BgeM3Client → sentence-transformers 모델 다운로드. 명시적 skip 원하면 `--no-embed`. CLI help text에 명시.
3. **dry_run + --no-embed**: 양쪽 다 OK (둘 다 embed skip). dry_run 우선 처리. 충돌 없음.

### Low
4. **`_FailingMockEmbeddingClient`을 production 패키지에 두는 design choice**: factory.py에 `_` prefix + docstring 명시. test fixture가 packaged code에 있어도 `EMBEDDING_PROVIDER=mock_fail` 환경 변수가 없으면 절대 reach 안 됨. trade-off: 더 명확한 분리는 `tests/fixtures/` 같은 경로지만 subprocess test에서 import 가능하려면 sys.path manipulation 필요. 본 plan은 factory.py 안에 두기로.
5. **subprocess 환경 격리 (HF_HOME doc 6 사고)**: 본 phase 직접 관련 없음 (HF_HOME은 sentence-transformers cache 경로). settings.json 영구 fix 완료. Subprocess test는 `MockEmbeddingClient`라 HF_HOME 무관.
6. **API lifespan refactor 안 함**: API는 기존 inline BgeM3Client 유지. 향후 별도 phase. 본 phase에서 통합 안 하는 이유: scope 확대 회피 + 영향 범위 격리.

### Debate에서 다룰 질문
- `from_env_embedding()` 위치: `embedding/factory.py` 별도 파일 vs `cli.py` inline. 어느 쪽이 깔끔? (현 plan: factory.py)
- `_FailingMockEmbeddingClient`: production 코드 (factory.py) 에 두는 것이 OK? `tests/fixtures/` 같은 곳이 더 깔끔? (현 plan: factory.py + `_` prefix + docstring)
- Partial success (`stats.failed > 0`) 시 embed 시도: 정합? (실패 block은 status≠'translated' → backfill 자연 skip — 정합)
- Backfill log volume: backfill 자체가 `_log.info("embedded %d/%d ...")` 출력. CLI 사용 시 verbose? `--quiet` flag 필요?
