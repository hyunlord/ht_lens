# ht_lens — Development Roadmap

## Vision

PDF(한/영) 문서를 페이지 레이아웃과 이미지 위치를 유지하면서 번역하고,
블록 단위로 클릭해 AI 설명·질문·꼬리질문을 주고받으며, 그 대화를 핀과 함께
저장·관리할 수 있는 **로컬 도구**.

**v2.0 비전 (Phase 7)**: 사용자의 학습 히스토리를 활용한 personalization agent.
같은 PDF 안 ±2 block 외 cross-document RAG (Phase 7a 완료), user profile/persona,
memory system, learning progress 추적 → "내 학습 동반자".

---

## Architecture Overview

```
PDF ─► [Extractor] ─► page PNG + block JSON
                              │
                              ▼
                         [Ingest] ─► SQLite
                              │
                              ├──► [Embedding Service] ─► block_embeddings  ✅ Phase 7a
                              │     (bge-m3, 1024d, numpy brute-force)         │
                              ▼                                                │
                       [Translator] ─► translations                            │
                              │  (Phase 7a-2: concurrency 7, 5.66x)            │
                              ▼                              ▼                 │
              ┌──────────[FastAPI]──────────┐         [Cross-doc RAG]  ✅ 7a   │
              ▼                              ▼               │                 │
        [Static Viewer]              [LLMClient (split)]    │                 │
        - 배경 + 오버레이             - TranslateLLMClient    │                 │
        - 채팅 패널 + related_blocks  - ChatLLMClient ◄──────┤                 │
        - 핀 + 질문 리스트            (Phase 7a-2: stored vector reuse 0.18ms)│
        - 자동 요약                              [User Profile + Persona]  ←─ Phase 7b
                                                 [Memory System]          ←─ Phase 7c
                                                 [Learning Progress]      ←─ Phase 7d
                                      └─ qwen3.6-27b FP8 (prod, 2026-05)
                                         + v2_ko Korean-instruction prompt
```

핵심 단위는 **block**. block이 곧 번역 단위이자 클릭 단위이자 질문 단위이자
**embedding 단위**.

---

## Tech Stack

| 영역       | 선택                                                                  |
| ---------- | --------------------------------------------------------------------- |
| Backend    | Python 3.11, FastAPI, SQLAlchemy 2.0 async, SQLite                    |
| PDF        | PyMuPDF (fitz), Pillow                                                |
| LLM        | OpenAI-compatible 인터페이스 (sglang qwen3.6-27b FP8, 2026-05)        |
| Vector DB  | numpy brute-force (Phase 7a, ~16K block scale에 충분)                 |
| Embedding  | BAAI/bge-m3 (Phase 7a, 1024d, multilingual)                           |
| Frontend   | vanilla HTML/JS (Phase 4~5), 향후 Electron 옵션                       |
| Dev tools  | uv, ruff, mypy strict, pytest, GitHub Actions                         |

---

## Data Model

```text
documents     (id, filename, src_pdf_sha256, src_lang, tgt_lang, status, created_at)
pages         (id, doc_id, page_num, width, height, bg_image_path)
blocks        (id, page_id, type, bbox_json, order_idx, original_text)
                  type ∈ {text, image, header, table}
translations  (block_id PK, translated_text, model, status, cache_key, updated_at)
threads       (id, block_id, title, created_at)
messages      (id, thread_id, role, content, model, created_at)
jobs          (id, kind, status, progress, payload_json, created_at)
summaries     (doc_id PK, content, model, updated_at)
block_embeddings (block_id PK, model, dim, vector BLOB, source_hash, updated_at)  ✅ 7a

# Phase 7b/c/d 추가 예정
user_profile     (id PK, name, background, expertise_areas, persona_text)   ← 7b
memory_notes     (id, content, importance, source_thread_id, created_at)    ← 7c
learning_log     (id, doc_id, action, block_id, timestamp, ...)             ← 7d
```

---

## Phases — Completed

### Phase 0 — Skeleton & Harness ✅
- 디렉토리 구조, pyproject(uv), ruff, mypy strict, pytest markers
- GitHub Actions, pre-commit, Makefile

### Phase 1 — PDF Extractor ✅
- 페이지별 PNG (200dpi) + block JSON
- 한/영/혼재 fixture 회귀 테스트
- Known issues (Phase 6h): 멀티컬럼 reading order, header heuristic

### Phase 2a — DB + LLMClient + Ingest ✅
- SQLite + SQLAlchemy 2.0 async + Alembic
- `LLMClient` Protocol + `MockLLMClient`
- 97 tests pass

### Phase 2b — Translation Pipeline ✅ (Phase 7a-2에서 진정 완성)
- `OpenAICompatibleClient` (sglang qwen3.6, `enable_thinking=false`)
- block 단위 번역 + cache, async + semaphore batch
- 147 tests pass, v0.1 마일스톤
- ~~Known issue: outer loop sequential `for ... await`~~ → **Phase 7a-2에서 fix (asyncio.as_completed)**

### Phase 3 — FastAPI Server ✅
- REST API + 채팅 컨텍스트 자동 구성 (block ±2)

### Phase 4 — Viewer Frontend ✅
- 정적 뷰어 (vanilla HTML/JS), v0.2 마일스톤

### Phase 5 — Chat Panel + Pins + Question List ✅
- block 클릭 → 채팅 패널, 핀, 질문 사이드바
- 268 fast tests, v0.3 마일스톤

### Phase 6a — Critical UX gaps ✅
- Cmd+K 검색, 질문 export, block 재번역
- v0.4 마일스톤

### Phase 6b — Viewer Rework ✅
- 좌우 분할 비교, 자연 스크롤, v0.5 마일스톤

### Phase 6c — Viewer Polish ✅
- LLM env 로드, fit-to-width zoom, 사이드바 토글, v0.6 마일스톤

### Phase 6d — File Management + Summary ✅
- 파일 업로드 + 자동 처리 체인, 자동 요약, v0.7 마일스톤

### Phase 6e — LLMClient Infrastructure Split ✅
- TranslateLLMClient + ChatLLMClient 분리

### Phase 6e-2 — CLI .env Load + Fail-closed Provider ✅
- 442 tests pass, v0.8 마일스톤

### Phase 6f-1 → 6f-5 — Production Model 결정 ✅
- Phase 6f-1: qwen → Gemma 4 swap → 사용자 발견 본문 KR 측정 누락
- Phase 6f-5: qwen rollback + v2_ko prompt
- 454 tests pass, doc 4 KR 0.859, v0.8.5 마일스톤

### Phase 7a — Cross-document RAG ✅ (v1.5 마일스톤, 2026-05-26)
- `block_embeddings` + numpy brute-force search
- bge-m3 1024d multilingual
- chat_context.py cross-doc top-K
- `/explain` + `/messages` 응답에 `related_blocks` 필드
- CLI: `ht-lens embed`, Upload-chain auto-embed (jobs/pipeline.py)
- 508 tests pass, 16 commits, R2 Option B+ micro-fix
- E2E /explain: 5 cross-doc hits, top-1 score 1.00

### Phase 7a-2 — Throughput Optimization ✅ (2026-05-26)

**Deliverable**

**Sub-goal A — Translation concurrency fix**:
- `translate_document` outer loop: sequential `for ... await` → `asyncio.as_completed` + `Semaphore(7)` + db_lock (AsyncSession 동시사용 회피) + pending_futures (dedup race 해결)
- Retry sleep outside semaphore (sem hold time 최소화)
- `--concurrency` parameter 진짜 동작, default 7 (sglang effective_max_running_requests_per_dp)
- **Mock LLM benchmark: 5.66x speedup** (c=1 vs c=7, 30 blocks)
- Phase 2b부터 존재하던 design bug 해결

**Sub-goal B — RAG latency**:
- Codex Alt 1 채택: `block_embeddings.vector` 재사용 (DB stored vector hit)
- 첫 query (cache miss + DB hit): 0.18ms
- Fallback path (block_embeddings 없을 때): 575ms 그대로
- Helper-level p95: 0.18ms (end-to-end 아닌 helper만, integration test로 lock)
- DoD <500ms 충족

**Sub-goal C — DB batch commit**:
- 사용자 명시적 skip 결정 ("measure first")
- Verify에서 SQLITE_BUSY 0건 → contention 없음 입증
- Over-engineering 회피
- 미래 contention 발생 시 별도 phase (조건부)

**DoD**
- Translation throughput 5.66x (mock benchmark) ✅
- /explain RAG latency p95 < 500ms ✅ (helper-level)
- 회귀 0 ✅ (508 → 521 tests, +13)
- ruff / mypy strict / format clean ✅

**완료 노트** (2026-05-26)
- 13 commits (plan → debate → challenge RE-PLAN → plan v2 → feat A/B → verify → cross R1 → fix R1 → verify v2 → cross R2 → summary → Planner-directed micro-fix)
- R2 DOWNGRADE → Planner Option B+ micro-fix (process fix + docstring + test rigor + summary)
- CI green (run 26456451873)
- Verify v3 정직한 verdict: "FAIL → RE-CODE applied (R1) + Planner-directed micro-fix (R2)"

**미래 가치 (Live benchmark는 doc 7에서)**
- doc 7 (Murphy PML, 36K blocks): 18h → **~5h** 예상
- 모든 미래 PDF 번역에 5.66x 효과
- v1.6 마일스톤은 Phase 7a-3 완료 후 확정

---

## Phases — Pending (v1.6)

### Phase 7a-3 — CLI Auto-embed 영구화 ⬜
(Phase 7a worker 발견 + doc 6 nohup chain workaround로 입증)

**Deliverable**
- `src/ht_lens/translate/cli.py`에 backfill chain 추가 (jobs/pipeline.py 패턴 그대로)
- `ht-lens translate --doc-id N` 호출 시 자동 embedding 트리거
- Embedding 실패 시 graceful degradation (translate는 성공)
- 단위 + 통합 테스트

**DoD**
- CLI translate 완료 후 자동 embed (shell chain 불필요)
- Embed 실패가 translate 실패로 전파 안 됨
- 회귀 0 (521 tests 유지)

**가치**
- doc 7 진행 시 깔끔한 명령 (`nohup ht-lens translate --doc-id 7 --concurrency 7 & disown`)
- 미래 모든 CLI translate 작업
- v1.6 마일스톤 완료

**예상 시간**: 30분~1h 작업 (Phase 7a 패턴 그대로)

**Versioning**: v1.6 일부

---

## Phases — Pending (v0.9 / v1.0)

### Phase 6f-3 — Graceful Shutdown ⬜
- ht_lens FastAPI에 SIGTERM handler
- Versioning: v0.9 일부

### Phase 6f-6 — Prompt Policy Layer 분리 ⬜
- Transport-agnostic prompt management
- Versioning: v0.9 일부

### Phase 6f-7 — Verification 자동화 ⬜
- Rollback runbook script
- CI 통합 강화
- Versioning: v0.9 일부

### Phase 6e-3 — Status 마킹 Provider 인식 ⬜
- Versioning: v0.9 일부 (low priority)

### Phase 6g — UI Polish Residual ⬜
**기존 항목**:
- 핀 표시, 사이드바 리사이즈, 이미지 모달
- streaming 응답 (SSE), Playwright, CI jsdom
- LLM-driven thread title

**추가 (사용자 발견)**:
- 페이지 간 공백 줄이기
- 채팅 패널 + 좌우 비교 동시 표시

Versioning: v0.9

### Phase 6h — Extraction Quality + 후처리 ⬜
- header heuristic 보강
- 멀티컬럼 reading order
- 표 cell + figure 안 텍스트 분리 (64.7% short fragment)
- Issue B 후처리: 번역 일관성 강화
- 자동 요약 hierarchical
- Versioning: v1.0

### Phase 6h-1 — Section-level Chat Context ⬜
- Block ±2 → 같은 section 전체 확장
- Versioning: v1.0 일부

### Phase 6h-2 — 번역 언어 옵션 UI/API ⬜
- Upload API에 src/tgt 파라미터, UI lang selector
- Versioning: v1.0 일부

---

## Phase 7 — Personalization Agent 시리즈

### Phase 7a — Cross-document RAG ✅ (v1.5 마일스톤, 위 참조)

### Phase 7a-2 — Throughput Optimization ✅ (위 참조)

### Phase 7a-3 — CLI Auto-embed 영구화 ⬜ (위 참조)

### Phase 7b — User Profile + Persona Injection ⬜
- `user_profile` 테이블 (background, expertise_areas, persona_text)
- Chat system prompt 동적 구성 시 profile 주입
- Persona preset (학부생 / 연구자 / 엔지니어)
- Versioning: v2.0 일부

### Phase 7c — Memory System ⬜
- `memory_notes` 테이블 (cross-thread 참조)
- "저번에 X 봤지" 형식 retrieval
- Time-based + Cross-doc 메모리 (7a RAG 연계)
- Versioning: v2.0 일부

### Phase 7d — Learning Progress ⬜
- `learning_log` 테이블
- 적응형 설명 깊이
- Versioning: v2.0 일부

### Phase 7e — Persona UI ⬜
- Profile 편집, Memory viewer
- "잊어줘" 기능
- Versioning: v2.0 일부

---

## Evaluation Track

ht_lens 도메인 코드 영향 0. 외부 sandbox (`~/llm_eval/`)에서 prod 모델 결정용.

### Phase E1 — Baseline Translation Evaluation ✅ (2026-05-22)
- 평가셋 eval_v1.jsonl (~580 sample), 6 카테고리
- 비교 모델 5개, qwen 5/6 카테고리 우세

### Phase E1.5 — Large Model Comparison ✅ (2026-05-23)
- 평가셋 v2 (~739 sample), 7 모델 중 5개 성공
- chrF + LLM-judge: Gemma 4 26B-A4B 우세 → Phase 6f-1 swap 결정
- **사후 학습**: 본문 KR 측정 누락 → Phase 6f-5 rollback

### Phase E1.5 보완 — qwen A/B Re-measurement ✅ (2026-05-23)
- block 분류 (15 카테고리)
- pure_text 일관성: qwen 78.9% vs gemma 42.9%
- Matched-block 14/0 qwen 우세

### Phase E2 — LoRA Fine-tune (Conditional) ⬜
**ROI 재평가**: qwen baseline 0.867 강함. Fine-tune 효과 작을 가능성.
**Versioning**: v1.0 일부 (conditional)

---

## Versioning

| 버전     | 시점                        | 의미                                                  |
| -------- | --------------------------- | ----------------------------------------------------- |
| v0.1 ✅  | Phase 2a + 2b 완료          | CLI로 번역 가능                                       |
| v0.2 ✅  | Phase 3 + 4 완료            | 브라우저에서 읽기 가능                                |
| v0.3 ✅  | Phase 5 완료                | Q&A 동작, 핀                                          |
| v0.4 ✅  | Phase 6a 완료               | 검색 + export + 재번역                                |
| v0.5 ✅  | Phase 6b 완료               | 좌우 비교 + 자연 스크롤                               |
| v0.6 ✅  | Phase 6c 완료               | Viewer polish                                         |
| v0.7 ✅  | Phase 6d 완료               | 파일 업로드 + 자동 요약                               |
| v0.8 ✅  | Phase 6e + 6e-2 완료        | LLMClient 분리 + CLI .env fix                         |
| v0.8.5 ✅| Phase 6f-1 → 6f-5 완료      | prod swap → rollback + v2_ko prompt                   |
| v0.9 ⬜  | Phase 6f-3 + 6f-6 + 6f-7 + 6e-3 + 6g | 운영 polish                                  |
| v1.0 ⬜  | Phase 6h + 6h-1 + 6h-2      | 추출 품질 + UX 완성                                   |
| **v1.5 ✅** | **Phase 7a 완료**         | **Cross-doc RAG (다른 책 관련 부분 자동 참조)**        |
| **v1.6 ⬜** | **Phase 7a-2 ✅ + 7a-3 완료** | **Throughput 5.66x + CLI auto-embed 영구화**  |
| **v2.0 ⬜** | **Phase 7b/c/d/e 완료**   | **Personalization agent (profile + memory + progress + UI)** |

---

## Risks & Open Questions

- **Block grouping 정확도**: Phase 6h.

- **표/figure fragment 처리**: 64.7% fragment. Phase 6h.

- **공유 GPU 환경**: DGX Spark sglang 다른 user 영향.

- **Reasoning model의 thinking 토글**: qwen3.6 `enable_thinking=false` 명시.

- **번역 일관성 (Issue B)**: qwen + v2_ko로 doc 4 KR 0.859, doc 6 검증 대기.

- **Chat context 큰 틀 grouping (Issue C)**: Phase 6h-1 (section), Phase 7a (cross-doc) 둘 다 보완.

- **번역 언어 옵션 (Issue A)**: Phase 6h-2.

- **폰트 fitting**: bbox에 텍스트 욱여넣기.

- **Reading order**: Phase 6h.

- **로컬 모델 품질**: qwen3.6-27b prod 안정. baseline 강함 (KR 0.867).

- **평가 framework 한계 (Phase 6f-1 → 6f-5 학습)**: 본문 KR 측정 의무.

- **자동 요약 hierarchical**: Phase 6d debt. Phase 6h.

- **~~Translation pipeline sequential bug~~**: ✅ Phase 7a-2에서 fix (5.66x speedup).

- **sglang effective_max_running_requests_per_dp = 7**:
  설정 48이지만 실제 7. concurrency 7로 fix됨. 더 늘릴 수 있는지 별도 조사 (Phase 7a-2 후속).

- **Phase 7a Retrieval quality**: doc 6 추가로 6 docs / 4,692 vectors 확보. Cross-doc 효과 doc 7 추가 후 재측정.

- **Phase 7a-2 Live LLM benchmark**: Mock 5.66x speedup. Doc 7 (36K) 진행 시 자연 측정.

- **Phase 7b Persona 디자인**: 어디까지 사용자 직접 입력 vs 자동 학습? Plan 단계 결정.

- **HF_HOME 영구 fix 완료** (2026-05-26): `~/.claude/settings.json` `/home/user/...` → `/home/hyunlord/...` 정정. 다음 Claude session부터 적용.

---

## Workflow Conventions

- 각 Phase는 별도 브랜치(`phase-N-<short-name>`)에서 작업, PR로 머지
- 커밋: Conventional Commits
- Phase 종료 시: ROADMAP 해당 Phase ⬜ → ✅, README 갱신
  - **주의**: Worker는 ROADMAP 수정 금지 (CLAUDE.md 규정). 사용자가 직접.
- Cross-verify는 phase당 max 2회 (WORKFLOW.md Stage 5-B)
  - R2 후 Planner-directed micro-fix는 허용 (Phase 6e / 6e-2 / 6f-5 / 7a / 7a-2 선례)
- Evaluation Track은 ht_lens 도메인 코드 변경 0.
- **평가 protocol 의무 (Phase 6f-1 → 6f-5 학습)**:
  새 모델 평가 시 chrF + LLM-judge + **본문 KR (pure_text 카테고리)** 모두 측정.

---

## prod 운영 메모 (2026-05-26 현재)

- **prod 모델**: qwen3.6-27b FP8 (sglang docker 8081)
  - speculative decoding NEXTN (EAGLE, 4 steps, 51% accept rate)
  - context 32768, mem-fraction-static 0.70 → ~90GB GPU
  - **sglang effective_max_running_requests_per_dp = 7** (설정 48 무시)
- **prompt**: v2_ko Korean-instruction (en→ko 분기)
- **translation concurrency**: 7 (Phase 7a-2 fix, 5.66x baseline 대비)
- **embedding 모델**: bge-m3 (BAAI, 1024d, CPU, ~2GB)
- **vector search**: numpy brute-force + Phase 7a-2 stored vector reuse (helper p95 0.18ms)
- **rollback 자산**: Gemma 4 26B-A4B-IT weights 49GB → re-swap ~3분
- **ht_lens 서버**: 8080
- **DB**: `data/ht_lens.db`
  - 7 documents (doc 1-6 번역 완료, doc 7 대기)
  - block_embeddings: **4,692** vectors (485 baseline + doc 6 4,207)
  - Translations: qwen3.6-27b (Phase 6f-5 이후, doc 6은 v2_ko 적용)
- **doc 6 (Aggarwal RecSys textbook)** 완료 (2026-05-26 22:03 KST):
  - 8,900 translate (text/header 100%), failed 0
  - 4,207 embed (auto-embed chain via shell &&)
- **HF_HOME**: `~/.claude/settings.json` fix 완료 (2026-05-26)
- **평가 sandbox**: `~/llm_eval/`
  - eval_v1.jsonl, eval_v2.jsonl (739 sample)
  - block_classification.json (15 카테고리)
  - prompt A/B 결과 (Gemma 4 × 3 + qwen × 3 fixed pattern)
