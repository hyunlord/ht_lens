# ht_lens — Development Roadmap

## Vision

PDF(한/영) 문서를 페이지 레이아웃과 이미지 위치를 유지하면서 번역하고,
블록 단위로 클릭해 AI 설명·질문·꼬리질문을 주고받으며, 그 대화를 핀과 함께
저장·관리할 수 있는 **로컬 도구**.

**v2.0 비전 (Phase 7)**: 사용자의 학습 히스토리를 활용한 personalization agent.
같은 PDF 안 ±2 block 외 cross-document RAG, user profile/persona, memory system,
learning progress 추적 → "내 학습 동반자".

---

## Architecture Overview (v2.0 비전)

```
PDF ─► [Extractor] ─► page PNG + block JSON
                              │
                              ▼
                         [Ingest] ─► SQLite
                              │
                              ├──► [Embedding Service] ─► vector index  ←─ Phase 7a
                              │                              │
                              ▼                              │
                       [Translator] ─► translations          │
                              │                              │
                              ▼                              ▼
              ┌──────────[FastAPI]──────────┐         [Cross-doc RAG]
              ▼                              ▼               │
        [Static Viewer]              [LLMClient (split)]    │
        - 배경 + 오버레이             - TranslateLLMClient    │
        - 채팅 패널                   - ChatLLMClient ◄──────┤
        - 핀 + 질문 리스트                                    │
        - 자동 요약                              [User Profile + Persona]  ←─ Phase 7b
                                                 [Memory System]          ←─ Phase 7c
                                                 [Learning Progress]      ←─ Phase 7d
                                      └─ qwen3.6-27b FP8 (prod, 2026-05)
                                         + v2_ko Korean-instruction prompt
```

핵심 단위는 **block**. block이 곧 번역 단위이자 클릭 단위이자 질문 단위이자
**embedding 단위** (Phase 7a부터).

---

## Tech Stack

| 영역      | 선택                                                              |
| --------- | ----------------------------------------------------------------- |
| Backend   | Python 3.11, FastAPI, SQLAlchemy 2.0 async, SQLite                |
| PDF       | PyMuPDF (fitz), Pillow                                            |
| LLM       | OpenAI-compatible 인터페이스 (sglang qwen3.6-27b FP8, 2026-05)    |
| Vector DB | (Phase 7a) sqlite-vec or chromadb                                 |
| Embedding | (Phase 7a) bge-m3 또는 multilingual-e5-large                      |
| Frontend  | vanilla HTML/JS (Phase 4~5), 향후 Electron 옵션                   |
| Dev tools | uv, ruff, mypy strict, pytest, GitHub Actions                     |

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

# Phase 7 추가 예정
block_embeddings (block_id PK, vector BLOB, model, dim, updated_at)        ← 7a
user_profile     (id PK, name, background, expertise_areas, persona_text)  ← 7b
memory_notes     (id, content, importance, source_thread_id, created_at)   ← 7c
learning_log     (id, doc_id, action, block_id, timestamp, ...)            ← 7d
```

---

## Phases — Completed (v1.0 path)

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
- block 단위 번역 + cache (`hash(text + src + tgt + model)`)
- async + semaphore batch
- 147 tests pass, v0.1 마일스톤

### Phase 3 — FastAPI Server ✅
- REST API + 채팅 컨텍스트 자동 구성 (block ±2, **Phase 6h-1에서 확장 예정**)

### Phase 4 — Viewer Frontend ✅
- 정적 뷰어 (vanilla HTML/JS), v0.2 마일스톤

### Phase 5 — Chat Panel + Pins + Question List ✅
- block 클릭 → 채팅 패널, 핀, 질문 사이드바
- 268 fast tests, vendor pattern (marked@11 + DOMPurify@3 ESM)
- v0.3 마일스톤

### Phase 6a — Critical UX gaps ✅
- Cmd+K 검색, 질문 export, block 재번역 (manual-retranslate provenance)
- v0.4 마일스톤

### Phase 6b — Viewer Rework ✅
- 좌우 분할 비교, 자연 스크롤, View mode 토글
- v0.5 마일스톤

### Phase 6c — Viewer Polish ✅
- LLM env 로드 (단 CLI는 Phase 6e-2에서 별도 fix)
- fit-to-width zoom, 사이드바 토글, 자연 스크롤 버그 fix
- v0.6 마일스톤

### Phase 6d — File Management + Summary ✅
- 파일 업로드 + 자동 처리 체인 (extract → ingest → translate)
- 자동 요약 (LLM)
- v0.7 마일스톤
- Known debt: 자동 요약 hierarchical 미적용 → Phase 6h

### Phase 6e — LLMClient Infrastructure Split ✅
- `LLMClient` Protocol → `TranslateLLMClient` + `ChatLLMClient` 분리
- 환경 변수 분리: `TRANSLATE_LLM_*` + `CHAT_LLM_*` (with `LLM_*` legacy fallback)
- max_tokens: translate=2048, chat=4096 / temperature: 0.0 vs 0.2
- 회귀 0 (403 → 427 tests), coverage 68% → 71%
- 환경 변수 1줄로 모델 swap 가능 (Phase 6f-1, 6f-5에서 두 번 검증)

### Phase 6e-2 — CLI .env Load + Fail-closed Provider ✅
- 🚨 Critical bug fix: CLI `ht-lens translate` 진입 시 `.env` 자동 load
- 공유 모듈 `src/ht_lens/dotenv_loader.py`
- Factory `_resolve_provider()` fail-closed (LLMConfigurationError 신규)
- 442 tests pass (+12 신규), 회귀 0
- v0.8 마일스톤 (Phase 6e + 6e-2)

### Phase 6f-1 → 6f-5 — Production Model 결정 흐름

#### Phase 6f-1 — Gemma 4 26B-A4B prod swap ✅ → 6f-5에서 Reverse
**진행 결과** (2026-05-23)
- prod 모델 qwen3.6-27b → Gemma 4 26B-A4B-IT
- 평가 근거: Phase E1.5 chrF +3.7, LLM-judge 3/3 우세
- 디스크 218GB 회복

**🚨 Reverse 사유** (Phase 6f-5에서)
- 사용자 실 사용에서 번역 일관성 문제 발견 (영어/한국어 섞임)
- Phase E1.5 평가가 chrF/LLM-judge만 측정 → **본문 한국어 일관성 누락**
- 정교한 재진단: pure_text 본문 KR qwen 0.789 vs gemma 0.429
- A/B test: qwen baseline 0.867 vs gemma_tuned_v2 0.755
- Matched-block 14/0 qwen 압도

**학습 (미래 평가 protocol에 반영)**
- 자동 metric + LLM-judge 외 **본문 KR** 측정 필수
- Cross-prompt comparison (model × prompt matrix) 필요

#### Phase 6f-2 — MoE Kernel Tuning ❌ (취소)
6f-5 rollback으로 prod 모델이 qwen3.6-27b. MoE kernel 대상 prod 아님.

#### Phase 6f-4 — Gemma 4 Prompt 재튜닝 ❌ (취소)
6f-5 rollback으로 의미 없음.

#### Phase 6f-5 — qwen Rollback + v2_ko Prompt ✅
**Deliverable**
- prod 모델 Gemma 4 → **qwen3.6-27b** 복귀
- v2_ko Korean-instruction prompt 적용 (en→ko 분기)
- Translate + chat 둘 다 qwen 통일

**DoD**
- E2E retranslate 평균 KR **0.96** (이전 Gemma 4 0.755 → +27%)
- 회귀 0 (442 → 454 tests, +12 신규)
- ht_lens 다운타임 ~6분

**완료 노트** (2026-05-23)
- Score: v1 91 / v2 84 / R2 79 → Planner-directed micro-fix → push + CI green
- src_lang/tgt_lang 분기 lock (en→ko만 v2_ko)
- **v0.8.5 마일스톤** — prod swap → reverse 학습 완료

**평가 근거** (Phase E1.5 보완 + qwen A/B 재측정)
- 본문 KR: qwen 0.874 vs gemma_v2 0.755 (+16%)
- AllKor>85%: qwen 65% vs gemma 25% (2.6x)
- Matched-block 14/20 qwen 우세, gemma 우세 0건
- Latency 비용 +1.4s (5.8s vs 4.4s) — 수용

---

## Phases — Pending (v1.0 path)

### Phase 6f-3 — Graceful Shutdown ⬜
- ht_lens FastAPI에 SIGTERM handler (현재 SIGTERM 무시 → SIGKILL 필요)
- Lifespan teardown 정상 동작
- DoD: `kill <pid>`로 ~5초 안에 종료, 진행 중 job 'interrupted' 마킹
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
- 핀 표시 더 직관적
- 사이드바 리사이즈 (200px ~ 500px)
- 이미지 클릭 시 확대 모달
- streaming 응답 (SSE) — Phase 5 debt
- Playwright 자동 시나리오 — Phase 5 debt
- CI jsdom 설치 — Phase 5/6b debt
- LLM-driven thread title — Phase 5 debt
- (선택) 모델 빠른 토글 UI

**추가 (사용자 발견)**:
- 페이지 간 공백 줄이기 (자연 스크롤 spacing)
- 채팅 패널 + 좌우 비교 동시 표시 (floating overlay 또는 narrow center)

Versioning: v0.9

### Phase 6h — Extraction Quality + 후처리 ⬜
**기존 (Phase 1 known issues)**:
- header heuristic 보강
- 멀티컬럼 reading order
- 표 cell + figure 안 텍스트 분리 (Phase E1.5 발견: 64.7% short fragment)
- samples.md determinism
- 회전 페이지 bbox→pixel 매핑

**추가 (사용자 Phase 6f-5 발견)**:
- Issue B 후처리: 번역 일관성 강화 (영어 leak 검출 + 자동 재시도)
- 자동 요약 hierarchical (Phase 6d debt)

Versioning: v1.0

### Phase 6h-1 — Section-level Chat Context ⬜
(사용자 Issue C)
- Block ±2 → 같은 section 전체 확장
- Header 인식 + section boundary
- Cross-page lookup
- 선행 조건: Phase 6h header heuristic 보강
- Versioning: v1.0 일부

### Phase 6h-2 — 번역 언어 옵션 UI/API ⬜
(사용자 Issue A)
- Upload API에 src/tgt 파라미터
- UI에 lang selector (en→ko / ko→en / en→ja)
- langdetect ko/en 외 확장 (ja/zh)
- Versioning: v1.0 일부

---

## Phases — v2.0 Personalization Agent (Phase 7 series)

**비전**: 사용자의 학습 히스토리를 활용한 personalization agent.
같은 PDF의 ±2 block 외 cross-document RAG, user profile/persona, memory system,
learning progress 추적. 점진적으로 "내 학습 동반자"로 발달.

### Phase 7a — Cross-document RAG ⬜
**핵심 가치**: 같은 PDF 안에서만이 아니라 **다른 PDF의 관련 부분도 chat context로**.

**Deliverable**
- `block_embeddings` 테이블 (block_id PK, vector BLOB, model, dim, updated_at)
- Embedding service (bge-m3 또는 multilingual-e5-large)
- Vector DB integration (sqlite-vec 권장 — ht_lens DB와 통합)
- 모든 block embedding 인덱싱 (~50K block × 1024d = ~200MB)
- `chat_context.py` 확장: block ±2 외 cross-doc top-K (5~10) 검색 추가
- 새 PDF 업로드 시 자동 embedding (extract → ingest → translate → embed chain)

**DoD**
- 모든 기존 block embedding 완료 (backfill)
- Chat 호출 시 cross-doc context 자동 포함
- Latency 영향 < +500ms (vector search)
- "다른 책의 관련 부분" 시각적 표시 (UI에서)

**위험**
- Embedding model GPU 사용 — qwen sglang과 동시 운영 시 메모리
- bge-m3 BF16 ~2GB, multilingual-e5-large ~2GB → CPU도 가능
- 검색 quality (irrelevant block이 chat 품질 떨어뜨릴 가능성)

**Versioning**: v1.5 또는 v2.0 일부 (다른 7 phase와 묶음)

### Phase 7b — User Profile + Persona Injection ⬜
- `user_profile` 테이블 (background, expertise_areas, persona_text)
- Chat system prompt 동적 구성 시 profile 주입
- Persona preset (학부생 / 연구자 / 엔지니어 / ...)
- 사용자가 자기 profile 편집 UI
- Versioning: v2.0 일부

### Phase 7c — Memory System ⬜
- `memory_notes` 테이블 (cross-thread 참조)
- "저번에 X 봤지" 형식의 메모리 retrieval
- 사용자 직접 메모 추가 ("이 부분 중요")
- Time-based ("일주일 전에 본 내용")
- Cross-doc 메모리 (Phase 7a RAG와 연계)
- Versioning: v2.0 일부

### Phase 7d — Learning Progress ⬜
- `learning_log` 테이블 (어느 챕터까지, 어떤 용어가 자주 막혔나)
- 적응형 설명 깊이 (사용자가 익숙한 용어는 짧게)
- 진도 시각화
- Versioning: v2.0 일부

### Phase 7e — Persona UI ⬜
- Profile 편집 화면
- Memory viewer ("내 메모리 보기")
- Persona preset selector
- "잊어줘" 기능 (memory delete)
- Versioning: v2.0 일부

---

## Evaluation Track

ht_lens 도메인 코드 영향 0. 외부 sandbox (`~/llm_eval/`)에서 prod 모델 결정용.

### Phase E1 — Baseline Translation Evaluation ✅
**완료** (2026-05-22)
- 평가셋 eval_v1.jsonl (~580 sample), 6 카테고리
- 비교 모델 5개: qwen3.6-27b, Hy-MT2-7B (BF16/4bit), NLLB-200-1.3B, M2M-100-1.2B
- 결과: qwen 5/6 카테고리 우세, NLLB/M2M ML 도메인 부적합

### Phase E1.5 — Large Model Comparison ✅
**완료** (2026-05-23, **본문 KR 측정 누락 → Phase 6f-1 잘못된 결론**)
- 평가셋 확장 v2 (~739 sample)
- 비교 모델 7개 중 5개 성공
- chrF + LLM-judge: Gemma 4 26B-A4B 우세 → Phase 6f-1 swap 결정
- **사후 학습**: 본문 KR 누락 → Phase 6f-5 rollback

### Phase E1.5 보완 — qwen A/B Re-measurement ✅
**완료** (2026-05-23)
- block 분류 (15 카테고리: pure_text / fragment / author_list / arxiv_meta / 등)
- 본문 (pure_text) 일관성 측정: qwen 78.9% vs gemma 42.9%
- Prompt A/B test: gemma_v2_ko 0.755 vs qwen_v2_ko 0.874
- qwen A/B broken (raw HTTP에서 thinking mode 활성) → root cause fix
- Matched-block 14/0 qwen 우세 → Phase 6f-5 rollback 결정

### Phase E2 — LoRA Fine-tune (Conditional) ⬜
**Entry condition**: 실 PDF 번역 사용 시 부족 영역 명확히 식별. 만족 시 skip.

**ROI 재평가**: qwen baseline 0.867 이미 강함. Fine-tune 효과 작을 가능성.

**Deliverable** (보존)
- Base: qwen3.6-27b 또는 다른 모델
- 데이터: AI Hub Tech-Science, ht_lens 4 PDF 합성 reference, arXiv abstract
- Framework: Unsloth + LLaMA-Factory 또는 PEFT

**Versioning**: v1.0 일부 (conditional)

---

## Versioning

| 버전 | 시점 | 의미 |
| ---- | ---- | ---- |
| v0.1 ✅ | Phase 2a + 2b 완료 | CLI로 번역 가능 |
| v0.2 ✅ | Phase 3 + 4 완료 | 브라우저에서 읽기 가능 |
| v0.3 ✅ | Phase 5 완료 | Q&A 동작, 핀 |
| v0.4 ✅ | Phase 6a 완료 | 검색 + export + 재번역 |
| v0.5 ✅ | Phase 6b 완료 | 좌우 비교 + 자연 스크롤 |
| v0.6 ✅ | Phase 6c 완료 | Viewer polish |
| v0.7 ✅ | Phase 6d 완료 | 파일 업로드 + 자동 요약 |
| v0.8 ✅ | Phase 6e + 6e-2 완료 | LLMClient 분리 + CLI .env fix |
| v0.8.5 ✅ | Phase 6f-1 → 6f-5 완료 | prod swap → rollback + v2_ko prompt |
| v0.9 ⬜ | Phase 6f-3 + 6f-6 + 6f-7 + 6e-3 + 6g | 운영 polish |
| v1.0 ⬜ | Phase 6h + 6h-1 + 6h-2 (+ E2 conditional) | 추출 품질 + UX 완성 |
| **v1.5** ⬜ | **Phase 7a 완료** | **Cross-doc RAG (다른 책 관련 부분 자동 참조)** |
| **v2.0** ⬜ | **Phase 7b/c/d/e 완료** | **Personalization agent (profile + memory + progress + UI)** |

---

## Risks & Open Questions

- **Block grouping 정확도**: 멀티컬럼/표/캡션에서 휴리스틱이 자주 깨진다.
  Phase 1에서 80% 잡고 진행, Phase 6h에서 보강.

- **표/figure fragment 처리**: Phase E1.5 발견 — book2.pdf의 text block 중 64.7%가
  1~30 char fragment. cost만 늘리고 의미 부정확. Phase 6h.

- **공유 GPU 환경**: DGX Spark의 sglang은 다른 사용자/세션과 공유. latency 변동.

- **Reasoning model의 thinking 토글**: qwen3.6 prod 운영 시 `enable_thinking=false` 명시.
  raw HTTP에선 `chat_template_kwargs` top-level. ht_lens는 OpenAI SDK 사용 → 정상.

- **번역 일관성 (사용자 발견 Issue B)**: qwen + v2_ko로 본문 KR 0.96 달성.
  Phase 6h에서 후처리 강화 (영어 leak 검출 + 자동 재시도).

- **Chat context 큰 틀 grouping (사용자 발견 Issue C)**: 현재 block ±2 + page boundary.
  Phase 6h-1에서 section-level 확장. **Phase 7a Cross-doc RAG로 cross-document 확장**.

- **번역 언어 옵션 (사용자 발견 Issue A)**: 현재 en→ko 단일. UI 토글.
  Phase 6h-2.

- **폰트 fitting**: bbox에 텍스트 욱여넣기. 한글은 영문 대비 폭/높이 다르다.

- **Reading order**: 채팅 맥락 품질에 직결. Phase 6h.

- **로컬 모델 품질**: qwen3.6-27b prod 운영 중. baseline 강함 (본문 KR 0.867).
  Phase E2 fine-tune ROI 신중 평가.

- **평가 framework 한계 (Phase 6f-1 → 6f-5 학습)**: chrF + LLM-judge만으로 부족.
  본문 KR 측정 의무. fragment 분리 + pure_text 통계.

- **자동 요약 hierarchical**: Phase 6d debt. 1000+ 페이지 PDF는 첫 N pages만 요약.
  Phase 6h.

- **Phase 7a Vector DB 선택**: sqlite-vec (간단, 통합) vs chromadb (별도, prod-grade).
  Plan 단계에서 결정.

- **Phase 7a Embedding 모델**: bge-m3 vs multilingual-e5-large vs jina-embeddings-v3.
  한/영 bilingual 성능 + GPU 메모리 비용 trade-off.

- **Phase 7a Retrieval quality**: Cross-doc 검색 결과가 irrelevant이면 chat 품질 저하.
  Threshold + ranking 신중.

---

## Workflow Conventions

- 각 Phase는 별도 브랜치(`phase-N-<short-name>`)에서 작업, PR로 머지
- 커밋: Conventional Commits (`feat:`, `fix:`, `chore:`, `refactor:`)
- Phase 종료 시: ROADMAP의 해당 Phase ⬜ → ✅ 갱신, README 상태 갱신
  - **주의**: Worker는 ROADMAP 수정 금지 (CLAUDE.md 규정). 사용자가 직접.
- 위에 명시되지 않은 dependency 추가 시 ROADMAP에 근거 기록
- Cross-verify는 phase당 max 2회 (WORKFLOW.md Stage 5-B 참조)
  - R2 후 Planner-directed micro-fix는 허용 (Phase 6e / 6e-2 / 6f-5 선례)
- Evaluation Track (E1, E1.5, E2)는 ht_lens 도메인 코드 변경 0,
  외부 sandbox 작업. plan/debate/verify 워크플로우 적용 안 함.
- **평가 protocol 의무 (Phase 6f-1 → 6f-5 학습)**:
  새 모델 평가 시 chrF + LLM-judge + **본문 KR (pure_text 카테고리)** 모두 측정.
  Cross-prompt comparison (model × prompt matrix) 필요.

---

## prod 운영 메모 (2026-05-23 현재)

- **prod 모델**: qwen3.6-27b FP8 (sglang docker 8081)
  - speculative decoding NEXTN (4 steps, eagle-topk 1)
  - context 32768
  - mem-fraction-static 0.70 → ~90GB GPU
- **prompt**: v2_ko Korean-instruction (en→ko 분기, 다른 방향 generic 보존)
- **rollback 자산**: Gemma 4 26B-A4B-IT weights 49GB (`~/hf_models/gemma-4-26b-a4b-it/`)
  + sglang Docker image (qwen 공유)
  + `.env.backup.gemma4_*`
  → re-swap 시간 ~3분
- **ht_lens 서버**: 8080
- **DB**: `data/ht_lens.db`
  - 7 documents ingest됨 (sample_mixed, phase6d_demo 2개, Open-Sora arXiv,
    2603.03482v1, Aggarwal RecSys textbook 518p, Murphy PML 1370p)
  - Translations: qwen3.6-27b (대부분) + Gemma 4 26B-A4B-IT 일부 (보존)
- **평가 sandbox**: `~/llm_eval/`
  - eval_v1.jsonl, eval_v2.jsonl (739 sample)
  - block_classification.json (15 카테고리)
  - prompt A/B 결과 (Gemma 4 × 3 + qwen × 3, fixed pattern)
