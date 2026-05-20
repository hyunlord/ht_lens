# Phase 2b — Challenge

## Debate responses

### 1. Over-engineering

**`translate/__main__.py` + CLI registration** — **PARTIAL accept**
Codex 주장: `python -m ht_lens.translate` 외에 `ht-lens translate` CLI까지 추가하면 wiring 부담.
응답: `ht-lens translate`는 Phase 2b DoD에서 사용자 인터페이스이고 일관성 필요. 단, CLI test는 핵심 경로만 커버하고 모든 flag subprocess test는 줄인다.
**결정**: 유지하되 CLI test 범위 최소화.

**LLMError 위계 5개** — **PARTIAL accept**
Codex 주장: 이 phase에서 3가지 동작만 필요 (retry / no-retry / empty guard).
응답: `LLMHealthCheckFailed`는 health_check 실패와 일반 LLM 실패를 구분하는 데 필요. 5개 유지. Phase 3에서 caller 추가될 때 위계가 이미 있으면 추가 cost 없음.
**결정**: 유지. 단 `LLMPermanentError` 세분화는 Phase 3+으로 미룸.

**`--dry-run` + tqdm** — **ACCEPT (partial defer)**
Codex 주장: DoD에 없음, 불안정.
응답: `--dry-run`은 실제 운영에서 필수 (GPU 비용 확인). 단 tqdm은 기본 progress log로 단순화. `--dry-run` 유지, tqdm 의존성 제거하고 `print`/`logging`으로 대체.
**결정**: `--dry-run` 유지, `tqdm` 제거. pyproject.toml에서 삭제.

### 2. Hidden assumptions

**Transaction 이야기 모순** — **ACCEPT**
Codex 주장: plan에서 "single commit + overall rollback"과 "failed block 마킹 후 계속"이 충돌.
응답: 이건 real bug. 명확화: **block 단위 commit** (각 block 처리 후 commit). 실패 block은 `status='failed'`로 commit, 나머지 계속. `--retry-failed`가 의미 있으려면 partial state가 DB에 남아야 함.
**결정**: block 단위 commit으로 수정. plan 업데이트.

**Protocol에서 모델명/reasoning_tokens 접근 불가** — **ACCEPT**
Codex 주장: `LLMClient.translate()` 반환값이 `str`뿐이라 모델명, finish_reason, reasoning_tokens를 side-channel 없이 알 수 없음.
응답: `OpenAICompatibleClient.translate()`는 Protocol 구현이므로 `str` 반환 유지. 대신:
- `model_name: str` attribute를 클라이언트에 두어 pipeline이 `llm.model_name`으로 DB에 저장
- `health_check()`에서 reasoning_tokens 확인 (batch 시작 전)
- `_extract_safe()`는 Protocol 외부 내부 메서드, 완전히 구현 가능
**결정**: `model_name` attribute 추가. LLMClient Protocol 시그니처 변경 없음.

**동일 run 내 중복 텍스트 in-memory dedupe 없음** — **ACCEPT**
Codex 주장: batch commit 전엔 같은 cache_key가 DB에 없어서 중복 호출 발생.
응답: in-memory dict `{cache_key: translated_text}`를 run 내에서 유지. DB hit과 in-memory hit 둘 다 체크. plan 업데이트.
**결정**: `pending_cache: dict[str, str]` in-memory 추가.

**`enable_thinking=False`의 provider 결합** — **PARTIAL accept**
Codex 주장: `extra_body`가 sglang 전용.
응답: 이 phase는 sglang 전용이고 그 결합은 의도적. `OpenAICompatibleClient` 이름은 유지 (Phase 3에서 Ollama 추가 시 `enable_thinking` optional로 변경 가능). Phase 2b scope 외.
**결정**: 유지.

**`cache_key=''` default의 lookup 취약성** — **ACCEPT**
Codex 주장: empty cache_key row가 잘못 hit될 수 있음.
응답: 두 가지 수정: (1) `cache_key` 컬럼을 `NOT NULL DEFAULT ''` 대신 nullable (`Optional[str]`)로, (2) cache lookup 시 `cache_key IS NOT NULL AND cache_key != ''` 조건. plan 업데이트.
**결정**: nullable cache_key + explicit filter.

### 3. Edge cases

**동시 실행 (concurrent translate runs)** — **REJECT**
Codex 주장: SQLite에서 duplicate LLM calls 위험.
응답: SQLite WAL mode도 없는 Phase 2b에서 concurrent run은 명시적 out-of-scope. ROADMAP Phase 3에서 FastAPI + connection pool 등장 시 처리. 단일 사용자 CLI tool.
**결정**: 미처리, 문서화.

**긴 block non-empty truncation** — **ACCEPT**
Codex 주장: `finish_reason="length"` + non-empty content → _extract_safe가 통과.
응답: `_extract_safe`에 `finish_reason="length"` → `LLMTransientError` 추가 (content 유무 상관없이). 이유: truncated translation은 오역보다 재시도가 낫다. test 추가.
**결정**: `finish_reason="length"` 자체를 `LLMTransientError`로 처리.

**`message.content` None 또는 list** — **ACCEPT**
Codex 주장: 일부 provider가 None 또는 content list 반환.
응답: `_extract_safe`에서 `content = choice.message.content` 시 None check + `if isinstance(content, list)` → join 또는 첫 번째 text part 추출 추가. unit test 추가.
**결정**: None/list 핸들링 추가.

**batch commit + SIGINT 데이터 손실** — **ACCEPT** (block 단위 commit으로 이미 해결됨)
Codex 주장: single commit이면 interruption 시 모두 손실.
응답: 이미 §2에서 block 단위 commit으로 변경함. 해결됨.

**`--retry-failed` + block_id PK 충돌** — **PARTIAL accept**
Codex 주장: 기존 `translations` row가 있을 때 versioning story 없음.
응답: `--retry-failed`는 기존 `status='failed'` row를 **update** (upsert). 새 row 만들지 않음. model/updated_at 갱신. Phase 2b 단일 모델 환경에서 충분.
**결정**: upsert (update existing row).

### 4. Alternative approaches

**별도 cache 테이블** — **REJECT**
Codex 주장: `translation_cache` 테이블이 더 명확.
응답: `translations.cache_key` 컬럼 approach는 Phase 2b prompt에서 고정된 결정사항. 별도 테이블은 Phase 6 리팩토링 시 논의. reject.

**SGLangClient로 이름 변경** — **REJECT**
Codex 주장: 더 정직한 이름.
응답: `OpenAICompatibleClient`는 Phase 2b prompt에서 고정. 이름 변경은 Phase 3 (Ollama 추가) 후 결정. reject.

**block 단위 commit** — **ACCEPT** (§2 모순 해결로 이미 반영됨)

### 5. Missing tests

**`test_translate_deduplicates_duplicate_blocks`** — **ACCEPT**
**결정**: in-memory cache + DB lookup 모두 테스트. 추가.

**`test_translate_skips_existing_translated_rows_by_default` + `test_retry_failed_only_requeues_failed_rows`** — **ACCEPT**
**결정**: 두 케이스 추가.

**`test_python_m_ht_lens_translate_exit_codes` (CLI subprocess)** — **ACCEPT**
**결정**: `tests/integration/test_translate_cli.py` 추가.

**`test_upgrade_0001_to_0002_preserves_existing_documents`** — **ACCEPT**
**결정**: `tests/integration/test_alembic.py`에 업그레이드 경로 테스트 추가.

**`test_safe_extract_rejects_truncated_nonempty_content` + `test_safe_extract_handles_none_or_list_content`** — **ACCEPT**
**결정**: `tests/unit/test_safe_extract.py`에 추가.

---

## Plan revisions (after debate)

1. **transaction 경계**: ~~batch 끝 single commit~~ → **block 단위 commit**
2. **tqdm 제거**: `tqdm` dependency 삭제, print/logging으로 progress 대체
3. **in-memory 중복 캐시**: `pending_cache: dict[str, str]` 추가
4. **`cache_key` nullable**: `NOT NULL DEFAULT ''` → `Optional[str]`
5. **`finish_reason="length"` → `LLMTransientError`**: content 유무 상관없이
6. **`_extract_safe` None/list 핸들링** 추가
7. **`model_name` attribute**: `OpenAICompatibleClient.model_name` (Protocol 변경 없음)
8. **추가 테스트**: 5개 항목 (dedup, skip existing, retry_failed, alembic upgrade path, safe_extract edge cases)
9. **`--retry-failed`**: upsert (update existing failed row)

---

## DoD checklist

| DoD item | 만족 방법 | Evidence 계획 |
|----------|-----------|---------------|
| short fixture 번역 가능 | sample_mixed.pdf CLI round-trip | live test |
| 재실행 캐시 hit 100% | cache_key lookup (DB + in-memory) | mock + live test |
| 실패 block 재시도 | --retry-failed + status='failed' update | mock fault injection test |
| reasoning_tokens == 0 회귀 체크 | health_check() at batch start | live health_check test |
| finish_reason='length' + empty 가드 | _extract_safe → LLMTransientError | unit test |
| mypy strict 0 | uv run mypy src/ | CI + verify |
| ruff clean | uv run ruff check . | CI + verify |
| 97 Phase 2a 테스트 무회귀 | uv run pytest -m "not llm" | verify |

---

## Risk register

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| sglang latency > 60s on shared GPU | Medium | block 단위 timeout | AsyncOpenAI timeout=60, LLMTransientError retry |
| content=None from provider | Low | silent empty translation | _extract_safe None check |
| block_id PK collision on retry | Low | data loss | upsert update |
| cache_key='' lookup false hit | Low | wrong translation | nullable + filter |
| SIGINT during batch | Medium | partial state | block 단위 commit (data survives) |

---

## Decision

- [x] PASS → proceed to code
- [ ] RE-PLAN (reason: )

7개 수용, 2개 부분 수용, 2개 거부. 거부된 항목(별도 cache 테이블, SGLangClient 이름)은 모두 prompt-fixed 결정사항. plan revision 9가지 적용.
