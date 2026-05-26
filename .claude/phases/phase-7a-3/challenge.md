# Phase 7a-3 — Challenge (Worker response to Codex debate)

## Summary decision: **RE-PLAN**

Codex가 14개 항목을 raise. 그 중 1개는 critical bug (BgeM3Client init 실패 처리 누락 — §2a/§3a), 4개는 substantive design issue (factory scope, CLI output 과잉, test-fixture in production, subprocess env 격리). plan V2 재작성.

8 ACCEPT, 2 PARTIAL, 4 REJECT/DEFER.

## Debate responses

### 1. Over-engineering

#### §1.1 factory.py가 단일 caller에만 사용됨 — **PARTIAL → 통합 (alt §4.2 채택)**
- Codex 주장: `translate/cli.py`만 사용. `cli.py::embed_command`와 `api/app.py::_lifespan`은 여전히 inline `BgeM3Client()`. "single-caller factory + direct constructors elsewhere is the worst middle ground."
- 확인: 코드 4곳에서 BgeM3Client 직접 instantiate. CLI translate 한 곳만 factory 사용 시 일관성 X.
- **결론**: Codex §4.2 채택 — factory를 만들면 3 caller (translate/cli.py, cli.py::embed_command, api/app.py::_lifespan) 모두 사용. 단 본 phase scope 확대 risk 있음.
- **plan V2 결정**: factory는 만들되 3 caller 모두 wire-up. embed_command와 API lifespan 변경은 minimal (BgeM3Client() 한 줄을 from_env_embedding() 호출로 교체, `RAG_DISABLED` 처리는 lifespan이 이미 inline으로 함 → factory도 동일 logic 유지). 회귀 net으로 기존 API/embed 테스트 통과 확인.

#### §1.2 `_FailingMockEmbeddingClient` production code leak — **ACCEPT**
- Codex 주장: test scaffolding이 runtime surface area에 들어옴. ROADMAP DoD가 fake provider 요구 안 함.
- **결론**: V2에서 `_FailingMockEmbeddingClient` 제거. 대신 **실제 production-relevant 실패 경로**로 test 3 재구성 (§3.1과 결합):
  - **BgeM3Client init failure 시뮬레이션**: `EMBEDDING_PROVIDER=bgem3_force_init_fail` 같은 prod-pollution보다는 BgeM3Client 자체 init이 실패하는 환경 (예: `HF_HUB_OFFLINE=1 HF_HOME=/nonexistent`) 사용하면 real failure path test 가능.
  - **선택 알고리즘**: subprocess test에서 `EMBEDDING_PROVIDER=mock`이지만 backfill 호출 자체가 raise하도록 fixture 주입 어렵. 대안: `EMBEDDING_PROVIDER=mock`는 정상 동작, `RAG_DISABLED` 분리. Init failure는 별도 test로 HF_HOME 트릭 사용.
  - **plan V2 채택**: production factory는 단 2개 분기 — `RAG_DISABLED` → None, `EMBEDDING_PROVIDER=mock` → MockEmbeddingClient, default → BgeM3Client. `mock_fail` 제거. 실패 경로 test는 BgeM3Client init failure 강제 (HF_HOME unsetable → 트릭 어려움) 대신 **monkeypatch subprocess pattern**: test fixture python 스크립트가 `ht_lens.translate.cli` 를 import 해서 monkeypatch + asyncio.run. 또는 `from_env_embedding`이 raise하는 시나리오는 single test로 unit-level 분리.

#### §1.3 CLI output redesign 과잉 — **ACCEPT**
- Codex 주장: `embedded=` / `embed_skipped=` / new `partial:` line 모두 churn. minimal suffix or warning이면 충분.
- 확인: 기존 ok line은 `f"ok: doc_id={doc_id} translated=... cached=... skipped=... failed=..."`. 새 `partial:` line 도입은 기존 test 회귀 risk.
- **결론**: V2에서 minimal — 기존 ok / partial 구분 유지하지 말고 단순히 stderr/stdout에 별도 줄로 embed 결과 echo:
  - 성공: stdout에 `ok: doc_id=...` 그대로 + 추가 줄 `embed: embedded=N skipped=M`
  - skip: `embed: skipped (--no-embed)` 또는 `embed: skipped (RAG_DISABLED)`
  - 실패: stderr `warning: auto-embed failed: <exc>. Run 'ht-lens embed --doc-id {id}' manually.`
  - **이 형태로는 기존 ok line 회귀 0** (별도 줄로 분리).

### 2. Hidden assumptions

#### §2.1 BgeM3Client init failure not handled — **ACCEPT (CRITICAL bug)**
- Codex 주장: plan sketch에서 `from_env_embedding()` 호출이 try/except 바깥. BgeM3 import/download/init 실패 시 CLI abort. API lifespan의 fail-soft 동작과 비대칭.
- 확인: plan V1 §2 sketch 그대로면 `embedding_client = from_env_embedding()` 가 raise하면 outer except도 못 잡고 `_run` 자체가 abort.
- **결론 V2**: factory 호출 전체를 try/except로 감싸기. init 실패 시 stderr warning + exit 0 (translate는 이미 성공):
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
              embed_summary = f"embed: embedded={ek['embedded']} skipped={ek['skipped']}"
      except Exception as exc:
          typer.echo(f"warning: auto-embed failed: {exc}. Run 'ht-lens embed --doc-id {doc_id}' manually.", err=True)
          embed_summary = "embed: failed (see stderr)"
  ```
  Factory call + backfill call 모두 같은 except에 들어감. init failure + encode failure 모두 fail-soft.

#### §2.2 subprocess env 격리 부족 — **ACCEPT**
- Codex 주장: `_run_translate` helper가 `LLM_*` 만 filter. `EMBEDDING_PROVIDER` / `RAG_DISABLED` 미filter.
- **결론 V2**: `_run_translate` (또는 본 phase 신규 test의 env build)에서 `EMBEDDING_*` / `RAG_*` / `HF_*` prefix도 filter. 결정적 test 환경 보장.

#### §2.3 `stats.failed > 0` + auto-embed가 partial doc surface — **PARTIAL**
- Codex 주장: `_finalize_document_status`가 `partial_translated`로 mark, `search` 는 status filter 안 함. 부분 문서가 RAG에 surface 가능.
- 확인: `backfill._candidate_blocks` 가 `Translation.status='translated'` filter — 실패 row는 자연 제외. 단 성공 block들은 embed 되어 RAG에 노출. 이는 **올바른 동작** — 사용자가 부분 번역된 doc도 retrieve 가능.
- **결론 V2**: 정합. 단 test로 lock (Codex §5c). summary에 명시.

#### §2.4 mock dim=32 vs prod 1024-dim mixed-dim risk — **REJECT**
- Codex 주장: `MockEmbeddingClient` 가 32-dim 저장 → prod 1024-dim row와 혼재 시 `load_all` majority-dim heuristic으로 일부 무시.
- 확인: subprocess test는 `tmp_path`에 fresh DB 생성. 본 phase test가 prod DB에 dim=32 row 저장하는 시나리오 없음. `EMBEDDING_PROVIDER=mock`은 dev/test only, prod에서 절대 설정 안 됨.
- **결론**: V2에서 ENV docs에 명시. `EMBEDDING_PROVIDER=mock`은 test/dev only. prod DB에서 사용 금지. README/CHANGELOG 변경 안 함 (사용자가 ROADMAP에서 처리).

### 3. Edge cases

#### §3.1 Constructor-time failure가 real ops 이슈 — **ACCEPT (§2.1과 결합)**
- 위 §2.1 V2 sketch가 init failure 처리.

#### §3.2 `--retry-failed` stale embeddings 미정리 — **DEFER**
- Codex 주장: `--retry-failed` 후 fail로 remain한 block의 stale embedding 안 지움.
- 확인: 본 phase scope는 auto-embed chain. 기존 embedding GC 동작 (delete-on-text-change는 source_hash로 자동 refresh됨)과 별개. Stale embedding cleanup은 별도 phase.
- **결론**: defer. summary에 known limitation.

#### §3.3 재실행 시 noisy output — **ACCEPT**
- Codex 주장: 이미 번역된 doc에 `ht-lens translate` 재실행 시 `embedded=0 skipped=N` 출력 noisy.
- 확인: 기존 사용자가 cache hit 시 비슷한 패턴 (`translated=0 cached=N`). 새 embed line도 같은 conventions.
- **결론**: test로 lock (§5e). 별도 quiet flag 안 만듦.

#### §3.4 `python -m ht_lens.translate` vs `ht-lens` 비호환 — **ACCEPT**
- Codex 주장: 기존 test는 `python -m ht_lens.translate`. ROADMAP 명령은 `ht-lens translate`. Phase 6e-2 학습.
- **결론**: V2에서 test 5번 추가 — `ht-lens` console script로 동일 동작 검증. 단 venv 에서 `ht-lens` 가용성 보장.

### 4. Alternative approaches

#### §4.1 Reuse `embed_command` 본문을 helper로 추출 — **PARTIAL**
- Codex 주장: factory 대신 `cli.py::embed_command` 본문을 helper로 빼고 translate_command가 call.
- 확인: 두 caller 가 BgeM3Client + backfill 같은 패턴 사용. 하지만 helper의 책임 (engine 생성, session 관리, 출력 메시지)이 다름. factory는 client 생성 책임만 분리하면 깔끔.
- **결론**: V2에서 factory 패턴 유지 (`from_env_embedding`). 단 §4.2처럼 3 caller 모두 wire-up하여 consistency 확보.

#### §4.2 Factory를 모든 caller에 적용 — **ACCEPT**
- §1.1 결론대로 3 caller 모두 wire-up.

#### §4.3 Failure injection은 monkeypatch — **PARTIAL**
- Codex 주장: subprocess test에서 monkeypatch 패턴 사용.
- 확인: subprocess는 child process. monkeypatch는 parent process scope. subprocess에서 monkeypatch 효과 안 봄.
- **결론**: V2에서 `_FailingMockEmbeddingClient` 는 제거. Init-failure test는 `EMBEDDING_PROVIDER=mock` + sentence-transformers를 통한 정상 동작만 test. **별도 unit test (subprocess 없이)** 로 `from_env_embedding()` raise 시나리오 + outer try/except 동작 검증.

### 5. Missing tests

| Codex 제안 test | plan V2 채택 |
| --------------- | ------------ |
| `test_translate_cli_auto_embed_init_failure_is_non_fatal` (§5a) | ✅ subprocess test 5: `EMBEDDING_PROVIDER=mock` 으로는 init fail 모사 불가. **unit-level**로 변경: `translate_command` 함수를 직접 호출하면서 `from_env_embedding`을 monkeypatch (raise) → translate stats 정상 + stderr warning + exit 0 |
| `test_ht_lens_console_script_translate_auto_embeds_with_mock_provider` (§5b) | ✅ subprocess test 6: `ht-lens translate` (console script) 사용. venv에 설치된 entry point |
| `test_translate_cli_partial_failure_still_embeds_successful_blocks` (§5c) | ✅ subprocess test 7: `TRANSLATE_LLM_PROVIDER=mock_fail` (일부 block fail) + `EMBEDDING_PROVIDER=mock` (auto-embed). 1 doc, mock_fail은 첫 block fail, 나머지 ok. Embed가 성공 block만 처리 |
| 환경 격리 test (§5d) | ✅ `_run_translate_with_embed` helper에 `EMBEDDING_*`/`RAG_*`/`HF_*` filter. test 1-4 모두 격리됨을 가정 |
| `test_translate_cli_existing_translations_skip_auto_embed_cleanly` (§5e) | ✅ subprocess test 8: 이미 번역된 doc 두 번째 translate 호출. `embedded=0 skipped=N` 출력 + DB embeddings 변동 없음 |

V2 test 총 8개 (V1 4개 → 8개): mock auto + --no-embed + RAG_DISABLED + (드롭: prod fixture pollution) + console-script + partial-fail + rerun-clean + init-failure unit.

## Plan revisions (V1 → V2)

1. **CRITICAL fix**: `from_env_embedding()` 호출도 outer try/except 안. Init failure가 fail-soft.
2. **CLI output minimal**: 기존 ok/partial line 변경 X. 새 줄 `embed: ...` 추가.
3. **`_FailingMockEmbeddingClient` 제거**: production code clean. failure injection은 unit-level monkeypatch.
4. **Factory를 3 caller에 wire-up**: `translate/cli.py`, `cli.py::embed_command`, `api/app.py::_lifespan`. 일관성 확보.
5. **subprocess env 격리 강화**: helper에서 `EMBEDDING_*`/`RAG_*`/`HF_*` filter.
6. **Test 4 → 8개**: console script + partial-fail + rerun-clean + init-failure unit 추가.
7. **`stats.failed > 0` + auto-embed 정합 명시**: Codex §2c에 대한 답변 (test 7로 lock).
8. **defer**: `--retry-failed` stale embedding GC (Codex §3.2). summary known limitation.
9. **defer**: mock dim mixing in prod DB (§2.4) — env docs 명시.

## DoD checklist (V2 기준)

| DoD item | Status | Evidence |
| -------- | ------ | -------- |
| CLI translate auto-embed (default) | Open | test 1 |
| `--no-embed` opt-out | Open | test 2 |
| Embed failure graceful (encode-level) | Open | (mock_fail 제거, init-failure unit test로 변경) test 5 (unit) |
| `RAG_DISABLED=1` skip | Open | test 3 |
| BgeM3Client init failure graceful | Open | test 5 (unit, monkeypatched factory raise) |
| Console script `ht-lens translate` 동등 | Open | test 6 |
| Partial-failure 시 성공 block embed | Open | test 7 |
| Rerun clean output | Open | test 8 |
| Factory 3 caller wire-up (consistency) | Open | 기존 embed_command + API lifespan 테스트 통과 |
| Backward compat | Open | 기존 17 translate_cli tests + 모든 API tests 통과 |
| 521 → 529 tests pass | Open | `uv run pytest -m "not llm and not slow" -q --no-cov \| tail -3` |

## Risk register (V2)

| Risk | Likelihood | Impact | Mitigation |
| ---- | ---------- | ------ | ---------- |
| BgeM3Client init failure aborts CLI (V1 bug) | Eliminated | High | factory call 도 outer try/except 안 |
| `_FailingMockEmbeddingClient` prod 노출 | Eliminated | Low | factory에서 제거. failure injection은 unit-level monkeypatch |
| Factory 단일 caller로 inconsistency | Eliminated | Low | 3 caller (translate/cli, cli::embed, api/lifespan) 모두 wire-up |
| CLI output 변경으로 기존 test 회귀 | Low | Medium | 기존 ok/partial line 변경 X. 새 줄 추가 only |
| subprocess env 누수 (EMBEDDING_*/RAG_*) | Eliminated | Medium | env filter prefix 확장 |
| Partial-success + auto-embed가 RAG pollution | Low | Low | test 7로 lock + summary 명시. 성공 block만 embed, 자연 정합 |
| `--retry-failed` stale embedding GC 미구현 | Known | Low | scope 외 (defer, summary known limitation) |
| mock dim 32 vs prod 1024 mixing | Very Low | Low | test only env. `EMBEDDING_PROVIDER` 환경 변수 docs 명시 |

## Decision
- [x] PASS → proceed to RE-PLAN (V2) → code
- [ ] PASS → directly to code
- [ ] RE-PLAN

다음 단계: plan.md V2 재작성 → commit `chore(phase-7a-3): plan v2` → Stage 4 코드 진입.
