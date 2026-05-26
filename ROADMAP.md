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
                              │                                                │
                              ▼                              ▼                 │
              ┌──────────[FastAPI]──────────┐         [Cross-doc RAG]  ✅ 7a   │
              ▼                              ▼               │                 │
        [Static Viewer]              [LLMClient (split)]    │                 │
        - 배경 + 오버레이             - TranslateLLMClient    │                 │
        - 채팅 패널 + related_blocks  - ChatLLMClient ◄──────┤                 │
        - 핀 + 질문 리스트                                    │                 │
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

## Phases — Completed (v0.1 ~ v1.5)

### Phase 0 — Skeleton & Harness ✅
- 디렉토리 구조, pyproject(uv), ruff, mypy strict, pytest markers
- GitHub Actions, pre-commit, Makefile

### Phase 1 — PDF Extractor ✅
- 페이지별 PNG (200dpi) + block JSON
- 한/영/혼재 fixture 회귀 테스트
- Known issues (Phase 6h): 멀티컬럼 reading order, header heuristic, samples.md determinism

### Phase 2a — DB + LLMClient + Ingest ✅
- SQLite + SQLAlchemy 2.0 async + Alembic
- `LLMClient` Protocol + `MockLLMClient`
- 97 tests pass

### Phase 2b — Translation Pipeline ✅
- `OpenAICompatibleClient` (sglang qwen3.6, `enable_thinking=false`)
- block 단위 번역 + cache, async + semaphore batch
- 147 tests pass, v0.1 마일스톤

### Phase 3 — FastAPI Server ✅
- REST API + 채팅 컨텍스트 자동 구성 (block ±2)

### Phase 4 — Viewer Frontend ✅
- 정적 뷰어 (vanilla HTML/JS), v0.2 마일스톤

### Phase 5 — Chat Panel + Pins + Question List ✅
- block 클릭 → 채팅 패널, 핀, 질문 사이드바
- 268 fast tests, vendor pattern (marked@11 + DOMPurify@3 ESM)
- v0.3 마일스톤

### Phase 6a — Critical UX gaps ✅
- Cmd+K 검색, 질문 export, block 재번역
- v0.4 마일스톤

### Phase 6b — Viewer Rework ✅
- 좌우 분할 비교, 자연 스크롤, View mode 토글
- v0.5 마일스톤

### Phase 6c — Viewer Polish ✅
- LLM env 로드, fit-to-width zoom, 사이드바 토글
- v0.6 마일스톤

### Phase 6d — File Management + Summary ✅
- 파일 업로드 + 자동 처리 체인, 자동 요약 (LLM)
- v0.7 마일스톤

### Phase 6e — LLMClient Infrastructure Split ✅
- TranslateLLMClient + ChatLLMClient 분리
- 환경 변수 분리, 1줄 변경으로 모델 swap 가능

### Phase 6e-2 — CLI .env Load + Fail-closed Provider ✅
- 🚨 Critical bug fix: CLI silent mock 위험 해결
- 442 tests pass (+12 신규), v0.8 마일스톤

### Phase 6f-1 → 6f-5 — Production Model 결정
- Phase 6f-1: qwen → Gemma 4 swap (Phase E1.5 결과 기반)
- 사용자 실 사용에서 번역 일관성 문제 발견 → 본문 KR 측정 누락 발견
- Phase 6f-5: qwen rollback + v2_ko Korean-instruction prompt
- 454 tests pass, E2E KR 0.96 (이전 0.755 대비 +27%)
- v0.8.5 마일스톤

### Phase 7a — Cross-document RAG ✅ (v1.5 마일스톤)
**Deliverable**
- `block_embeddings` 테이블 + numpy brute-force search
- bge-m3 embedding service (1024d, multilingual)
- `chat_context.py` cross-doc top-K retrieval
- `/blocks/{id}/related` API
- `/explain` + `/messages` 응답에 `related_blocks` 필드
- Frontend: message.js renderRelatedBlocks, state.js cache
- CLI: `ht-lens embed`
- Upload-chain auto-embed (jobs/pipeline.py)
- Alembic migration 0004

**DoD**
- 모든 기존 block embedding 완료 (485 vectors backfilled, docs 1-5)
- Chat 호출 시 cross-doc context 자동 포함
- E2E /explain: 5 cross-doc hits, top-1 score 1.00 (Open-Sora exact match)
- Latency 575ms (DoD <500ms 미충족 → Phase 7a-2 위임)

**완료 노트** (2026-05-26)
- 508 tests pass (+43 신규, 0 regression)
- 16 commits (plan → debate → feat → verify v1/R1/RE-CODE/v2/R2/summary → micro-fix v3)
- R2 micro-fix (Option B+): a frontend test + b /messages test + c auto-embed + e whitespace + f .gitignore
- CI green (run 26427252749)
- **v1.5 마일스톤 달성**

**Known debt → Phase 7a-2 / 7a-3**
- Latency 575ms (75ms over DoD) — Phase 7a-2
- CLI auto-embed (translate/cli.py에는 backfill chain 미적용, jobs만) — Phase 7a-3

---

## Phases — Pending (v0.9 / v1.0 / Phase 7 정리)

### Phase 6f-3 — Graceful Shutdown ⬜
- ht_lens FastAPI에 SIGTERM handler
- Lifespan teardown 정상 동작
- DoD: `kill <pid>`로 ~5초 안에 종료
- Versioning: v0.9 일부

### Phase 6f-6 — Prompt Policy Layer 분리 ⬜
- Transport-agnostic prompt management
- 모델별 prompt 분기 인프라
- Cache prompt-versioning
- Versioning: v0.9 일부

### Phase 6f-7 — Verification 자동화 ⬜
- Rollback runbook script
- CI 통합 강화 (PR마다 회귀 + coverage 임계값)
- E2E smoke test 자동화
- Versioning: v0.9 일부

### Phase 6e-3 — Status 마킹 Provider 인식 ⬜
- `_finalize_document_status`가 provider 종류 인식
- Mock provider 사용 시 status='translated' 마킹 skip
- Versioning: v0.9 일부 (low priority)

### Phase 6g — UI Polish Residual ⬜
**기존 항목**:
- 핀 표시 더 직관적, 사이드바 리사이즈
- 이미지 클릭 시 확대 모달
- streaming 응답 (SSE) — Phase 5 debt
- Playwright 자동 시나리오 — Phase 5 debt
- CI jsdom 설치 — Phase 5/6b debt
- LLM-driven thread title — Phase 5 debt

**추가 (사용자 발견)**:
- 페이지 간 공백 줄이기 (자연 스크롤 spacing)
- 채팅 패널 + 좌우 비교 동시 표시 (floating overlay 또는 narrow center)

Versioning: v0.9

### Phase 6h — Extraction Quality + 후처리 ⬜
- header heuristic 보강
- 멀티컬럼 reading order
- 표 cell + figure 안 텍스트 분리 (Phase E1.5 발견: 64.7% short fragment)
- samples.md determinism
- 회전 페이지 bbox→pixel 매핑
- Issue B 후처리: 번역 일관성 강화
- 자동 요약 hierarchical (Phase 6d debt)
- Versioning: v1.0

### Phase 6h-1 — Section-level Chat Context ⬜
(사용자 Issue C)
- Block ±2 → 같은 section 전체 확장
- Header 인식 + section boundary
- 선행 조건: Phase 6h header heuristic 보강
- Versioning: v1.0 일부

### Phase 6h-2 — 번역 언어 옵션 UI/API ⬜
(사용자 Issue A)
- Upload API에 src/tgt 파라미터
- UI에 lang selector (en→ko / ko→en / en→ja)
- Versioning: v1.0 일부

---

## Phase 7 — Personalization Agent 시리즈

**비전**: 사용자의 학습 히스토리를 활용한 personalization agent. Phase 7a (cross-doc RAG)
위에서 점진적 발달.

### Phase 7a — Cross-document RAG ✅ (v1.5 마일스톤, 위 참조)

### Phase 7a-2 — Latency Optimization ⬜
(Phase 7a (d) DoD 미충족 위임)

**Deliverable**
- 575ms → <500ms 달성
- Investigation:
  - bge-m3 CPU encode가 dominant cost — GPU offload 검토
  - Query embedding cache (반복 query 빠르게)
  - numpy brute-force → sqlite-vec/faiss swap 검토
  - Batch embedding (UI는 단발 query라 batch 안 됨, 단 backfill은 가능)

**DoD**
- /explain latency p95 < 500ms (3 sample 측정)
- 회귀 0
- 메모리 영향 < 1GB 추가

**위험**
- GPU offload 시 qwen sglang과 메모리 경쟁
- sqlite-vec extension wheel 호환성

**Versioning**: v1.5 일부 또는 v1.6

### Phase 7a-3 — CLI Auto-embed 영구화 ⬜
(Phase 7a worker 발견 debt)

**Deliverable**
- `src/ht_lens/translate/cli.py`에 backfill chain 추가
- jobs/pipeline.py의 auto-embed 패턴 그대로 (graceful degradation)
- 단위 테스트 (CLI translate → embedding 자동)
- 미래 큰 PDF CLI 번역 시 shell chain 불필요

**DoD**
- `ht-lens translate --doc-id N` 호출 시 자동 embedding 트리거
- Embedding 실패 시 graceful degradation (translate는 성공)
- 회귀 0

**위험**: Phase 7a 패턴 그대로라 위험 작음

**Versioning**: v1.5 일부 또는 v1.6

### Phase 7b — User Profile + Persona Injection ⬜
- `user_profile` 테이블 (background, expertise_areas, persona_text)
- Chat system prompt 동적 구성 시 profile 주입
- Persona preset (학부생 / 연구자 / 엔지니어 / ...)
- 사용자가 자기 profile 편집 UI
- Versioning: v2.0 일부

### Phase 7c — Memory System ⬜
- `memory_notes` 테이블 (cross-thread 참조)
- "저번에 X 봤지" 형식의 메모리 retrieval
- 사용자 직접 메모 추가
- Time-based + Cross-doc 메모리 (7a RAG 연계)
- Versioning: v2.0 일부

### Phase 7d — Learning Progress ⬜
- `learning_log` 테이블
- 적응형 설명 깊이 (사용자가 익숙한 용어는 짧게)
- 진도 시각화
- Versioning: v2.0 일부

### Phase 7e — Persona UI ⬜
- Profile 편집 화면, Memory viewer
- Persona preset selector
- "잊어줘" 기능
- Versioning: v2.0 일부

---

## Evaluation Track

ht_lens 도메인 코드 영향 0. 외부 sandbox (`~/llm_eval/`)에서 prod 모델 결정용.

### Phase E1 — Baseline Translation Evaluation ✅
**완료** (2026-05-22)
- 평가셋 eval_v1.jsonl (~580 sample), 6 카테고리
- 비교 모델 5개: qwen3.6-27b, Hy-MT2-7B (BF16/4bit), NLLB-200-1.3B, M2M-100-1.2B
- 결과: qwen 5/6 카테고리 우세

### Phase E1.5 — Large Model Comparison ✅
**완료** (2026-05-23, **본문 KR 측정 누락 → Phase 6f-1 잘못된 결론**)
- 평가셋 확장 v2 (~739 sample)
- 비교 모델 7개 중 5개 성공
- chrF + LLM-judge: Gemma 4 26B-A4B 우세 → Phase 6f-1 swap 결정
- **사후 학습**: 본문 KR 누락 → Phase 6f-5 rollback

### Phase E1.5 보완 — qwen A/B Re-measurement ✅
**완료** (2026-05-23)
- block 분류 (15 카테고리)
- 본문 일관성 측정: qwen 78.9% vs gemma 42.9%
- qwen A/B root cause fix (chat_template_kwargs top-level)
- Matched-block 14/0 qwen 우세 → Phase 6f-5 rollback 결정

### Phase E2 — LoRA Fine-tune (Conditional) ⬜
**Entry condition**: 실 PDF 번역 사용 시 부족 영역 명확히 식별.

**ROI 재평가**: qwen baseline 0.867 강함. doc 4 KR 0.859, doc 6 검증 대기. Fine-tune 효과 작을 가능성.

**Deliverable** (보존): qwen3.6-27b 또는 다른 모델, AI Hub corpus + 합성 reference + arXiv abstract.

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
| v1.6 ⬜  | Phase 7a-2 + 7a-3           | Latency optimization + CLI auto-embed 영구화          |
| **v2.0 ⬜** | **Phase 7b/c/d/e 완료**   | **Personalization agent (profile + memory + progress + UI)** |

---

## Risks & Open Questions

- **Block grouping 정확도**: 멀티컬럼/표/캡션에서 휴리스틱 자주 깨짐. Phase 6h.

- **표/figure fragment 처리**: book2.pdf의 text block 중 64.7%가 1~30 char fragment.
  Phase 6h.

- **공유 GPU 환경**: DGX Spark의 sglang은 다른 사용자/세션과 공유.

- **Reasoning model의 thinking 토글**: qwen3.6 prod 운영 시 `enable_thinking=false` 명시 필수.

- **번역 일관성 (사용자 Issue B)**: qwen + v2_ko로 doc 4 KR 0.859, doc 6 검증 대기.

- **Chat context 큰 틀 grouping (사용자 Issue C)**: Phase 6h-1 (section), Phase 7a (cross-doc) 둘 다 보완.

- **번역 언어 옵션 (사용자 Issue A)**: Phase 6h-2.

- **폰트 fitting**: bbox에 텍스트 욱여넣기.

- **Reading order**: 채팅 맥락 품질에 직결. Phase 6h.

- **로컬 모델 품질**: qwen3.6-27b prod 안정. baseline 강함 (KR 0.867).

- **평가 framework 한계 (Phase 6f-1 → 6f-5 학습)**: chrF + LLM-judge만으로 부족.
  본문 KR 측정 의무.

- **자동 요약 hierarchical**: Phase 6d debt. Phase 6h.

- **Phase 7a Latency**: 575ms vs DoD <500ms. 75ms 초과, Phase 7a-2 위임.

- **Phase 7a Retrieval quality**: 현재 threshold + top-K default 안정적 (E2E top-1 1.00).
  doc 6 추가 후 cross-doc 효과 재측정 필요.

- **Phase 7b Persona 디자인**: 어디까지 사용자가 직접 입력 vs 자동 학습? Plan 단계 결정.

---

## Workflow Conventions

- 각 Phase는 별도 브랜치(`phase-N-<short-name>`)에서 작업, PR로 머지
- 커밋: Conventional Commits (`feat:`, `fix:`, `chore:`, `refactor:`)
- Phase 종료 시: ROADMAP의 해당 Phase ⬜ → ✅ 갱신, README 상태 갱신
  - **주의**: Worker는 ROADMAP 수정 금지 (CLAUDE.md 규정). 사용자가 직접.
- Cross-verify는 phase당 max 2회 (WORKFLOW.md Stage 5-B 참조)
  - R2 후 Planner-directed micro-fix는 허용 (Phase 6e / 6e-2 / 6f-5 / 7a 선례)
- Evaluation Track은 ht_lens 도메인 코드 변경 0, 외부 sandbox 작업.
- **평가 protocol 의무 (Phase 6f-1 → 6f-5 학습)**:
  새 모델 평가 시 chrF + LLM-judge + **본문 KR (pure_text 카테고리)** 모두 측정.

---

## prod 운영 메모 (2026-05-26 현재)

- **prod 모델**: qwen3.6-27b FP8 (sglang docker 8081)
  - speculative decoding NEXTN (4 steps, eagle-topk 1)
  - context 32768, mem-fraction-static 0.70 → ~90GB GPU
- **prompt**: v2_ko Korean-instruction (en→ko 분기)
- **embedding 모델**: bge-m3 (BAAI, 1024d, CPU, ~2GB) — Phase 7a
- **vector search**: numpy brute-force (block_embeddings 테이블)
- **rollback 자산**: Gemma 4 26B-A4B-IT weights 49GB + sglang Docker image
  → re-swap 시간 ~3분
- **ht_lens 서버**: 8080
- **DB**: `data/ht_lens.db`
  - 7 documents (doc 1-5 번역 완료 qwen+v2_ko, doc 6 진행 중, doc 7 대기)
  - block_embeddings: 485 baseline + doc 6 진행 중 추가
  - Translations: qwen3.6-27b (대부분, Phase 6f-5 이후)
- **doc 6 (Aggarwal RecSys textbook)**: 2026-05-26 12:51 KST 시작, ETA 8~15시간
  + auto-embed chain (shell &&)
- **평가 sandbox**: `~/llm_eval/`
  - eval_v1.jsonl, eval_v2.jsonl (739 sample)
  - block_classification.json (15 카테고리)
  - prompt A/B 결과 (Gemma 4 × 3 + qwen × 3 fixed pattern)
