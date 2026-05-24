# ht_lens — Development Roadmap

## Vision
PDF(한/영) 문서를 페이지 레이아웃과 이미지 위치를 유지하면서 번역하고,
블록 단위로 클릭해 AI 설명·질문·꼬리질문을 주고받으며, 그 대화를 핀과 함께
저장·관리할 수 있는 **로컬 도구**.

---

## Architecture Overview

```
PDF ─► [Extractor] ─► page PNG + block JSON
                              │
                              ▼
                         [Ingest] ─► SQLite
                              │
                              ▼
                       [Translator] ─► translations (cached)
                              │
                              ▼
              ┌──────────[FastAPI]──────────┐
              ▼                              ▼
        [Static Viewer]              [LLMClient (split)]
        - 배경 + 오버레이             - TranslateLLMClient
        - 채팅 패널                   - ChatLLMClient
        - 핀 + 질문 리스트            - sglang / Ollama / OpenRouter
        - 자동 요약                   - Mock (test)
                                      └─ qwen3.6-27b FP8 (prod, 2026-05)
                                         + v2_ko Korean-instruction prompt
```

핵심 단위는 **block**. block이 곧 번역 단위이자 클릭 단위이자 질문 단위.

---

## Tech Stack

| 영역      | 선택                                                              |
| --------- | ----------------------------------------------------------------- |
| Backend   | Python 3.11, FastAPI, SQLAlchemy 2.0 async, SQLite                |
| PDF       | PyMuPDF (fitz), Pillow                                            |
| LLM       | OpenAI-compatible 인터페이스 (sglang qwen3.6-27b FP8, 2026-05)    |
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
```

---

## Phases

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
**Deliverable**
- `LLMClient` Protocol → `TranslateLLMClient` + `ChatLLMClient` 분리
- `factory.from_env_translate()` + `factory.from_env_chat()`
- 환경 변수 분리: `TRANSLATE_LLM_*` + `CHAT_LLM_*` (with `LLM_*` legacy fallback)
- max_tokens: translate=2048, chat=4096 / temperature: 0.0 vs 0.2

**완료 노트**
- 회귀 0 (403 → 427 tests), coverage 68% → 71%
- 환경 변수 1줄로 모델 swap 가능 (Phase 6f-1, 6f-5에서 두 번 검증)
- legacy `LLM_*` env 100% backward compat

---

### Phase 6e-2 — CLI .env Load + Fail-closed Provider ✅
**Deliverable**
- 🚨 Critical bug fix: CLI `ht-lens translate` 진입 시 `.env` 자동 load
  (이전엔 누락 → silent mock 사용 위험, doc 4/5에서 654건 mock 오염 발생, 정리됨)
- 공유 모듈 `src/ht_lens/dotenv_loader.py` (api/app.py + CLI 둘 다 사용)
- Factory `_resolve_provider()` fail-closed (provider env unset이면 `LLMConfigurationError`)
- LLMConfigurationError 신규 (exit code 5)

**DoD**
- 442 tests pass (+12 신규), 회귀 0
- subprocess로 console-script launcher path 검증
- missing-file branch + file-exists branch 양쪽 lock
- mypy strict 0 위반

**완료 노트** (2026-05-23)
- Score: v1 91 / v2 84 / cross R2 79 → Planner-directed micro-fix → push + CI green
- Round 2 DOWNGRADE는 prod 코드 결함 0, evidence presentation only
- 직전 mock 오염 사건의 root cause 해결

**Known debt → Phase 6e-3**
- Status 마킹 provider 인식 (`_finalize_document_status`가 mock도 'translated'로 마킹 가능)
- .env fix로 root cause 해결되어 발생 빈도 0이지만 fail-safe 강화 필요

---

### Phase 6f — Production Model 영역 (다층)

prod 모델 swap + 운영 최적화. Phase 6e 인프라 활용으로 도메인 코드 변경 최소.

#### Phase 6f-1 — Gemma 4 26B-A4B prod swap ✅ → Phase 6f-5에서 Reverse

**진행 결과** (2026-05-23)
- prod 모델 qwen3.6-27b → Gemma 4 26B-A4B-IT
- sglang docker 8082, qwen 8081 정지 (weights KEEP)
- 디스크 218GB 회복
- 평가 근거: Phase E1.5 chrF +3.7, LLM-judge 3/3 우세
- Latency +22% (4.78s), 메모리 -45% (49GB BF16)

**🚨 Reverse 사유** (Phase 6f-5에서)
- 사용자 실 사용에서 번역 일관성 문제 발견 (영어/한국어 섞임)
- Phase E1.5 평가가 chrF/LLM-judge만 측정 → **본문 한국어 일관성 누락**
- 정교한 재진단: pure_text 본문 KR qwen 0.789 vs gemma 0.429
- A/B test: qwen baseline 0.867 vs gemma_tuned_v2 0.755
- Matched-block 14/0 qwen 압도
- → Phase 6f-5로 rollback

**학습 (미래 평가 protocol에 반영)**
- 자동 metric + LLM-judge 외 **본문 KR (한국어 일관성)** 측정 필수
- 평가셋 카테고리에 fragment 포함하면 통계 왜곡 (pure_text 분리)
- Cross-prompt comparison (model × prompt matrix) 필요

#### Phase 6f-2 — MoE Kernel Tuning ❌ (취소)
**취소 사유**: Phase 6f-5 rollback으로 prod 모델이 qwen3.6-27b (dense FP8).
MoE kernel tuning 대상 (Gemma 4 26B-A4B MoE) prod 아님.

미래 Gemma 4 또는 다른 MoE 모델 prod 진입 시 재검토.

#### Phase 6f-3 — Graceful Shutdown ⬜
**Deliverable**
- ht_lens FastAPI에 SIGTERM handler (현재 SIGTERM 무시 → SIGKILL 필요)
- Lifespan teardown 정상 동작 (DB 연결 정리, 진행 중 job 안전 종료)

**DoD**
- `kill <pid>`로 graceful shutdown, SIGKILL 없이 ~5초 안에 종료
- 진행 중 job은 status 'interrupted'로 마킹

**위험**: async cleanup race condition, sglang/LLM 호출 중 connection cleanup

**Versioning**: v0.9 일부

#### Phase 6f-4 — Gemma 4 Prompt 재튜닝 ❌ (취소)
**취소 사유**: Phase 6f-5 rollback으로 prod 모델이 qwen 복귀. Gemma 4 prompt 변경 의미 없음.

#### Phase 6f-5 — qwen Rollback + v2_ko Prompt ✅

**Deliverable**
- prod 모델 Gemma 4 → **qwen3.6-27b** 복귀 (Phase 6f-1 reverse)
- v2_ko Korean-instruction prompt 적용 (en→ko 분기, 다른 방향은 generic 보존)
- Translate + chat 둘 다 qwen 통일
- Gemma 4 sglang docker stopped, weights 49GB + Docker image KEEP (re-swap 보험)

**DoD**
- E2E retranslate 평균 KR 0.96 (이전 Gemma 4 0.755 → +27% 개선)
- 회귀 0 (442 → 454 tests, +12 신규)
- ht_lens 다운타임 ~6분
- chat E2E model=qwen3.6-27b, KR 0.82, 한국어 정상

**완료 노트** (2026-05-23)
- Score: v1 91 / v2 84 / R2 79 → Planner-directed micro-fix → push + CI green (208s)
- 10 commits (plan → debate → feat → verify v1 → cross R1 → RE-CODE → verify v2 → cross R2 → summary → R2 micro-fix)
- src_lang/tgt_lang 분기 lock (en→ko만 v2_ko, 미래 ko→en/en→ja 대비)
- manual-retranslate provenance prefix `qwen3.6-27b:<ts>` 검증

**평가 근거** (Phase E1.5 보완 + qwen A/B 재측정)
- 본문 KR: qwen 0.874 vs gemma_v2 0.755 (+16%)
- AllKor>85%: qwen 65% vs gemma 25% (2.6x)
- Matched-block 14/20 qwen 우세, gemma 우세 0건
- qwen baseline (no prompt fix) 0.867조차 gemma_v2 0.755 초과
- Latency 비용 +1.4s (5.8s vs 4.4s) — 수용

**Versioning**: v0.8.5 (v0.8 Phase 6e + 6f-1의 reverse + v2_ko prompt)

---

### Phase 6f-6 — Prompt Policy Layer 분리 ⬜
(Phase 6f-5 Codex debate §4 alternative, follow-up)

**Deliverable**
- Transport-agnostic prompt management layer (OpenAICompatibleClient에서 분리)
- 모델별 prompt 분기 인프라 (Gemma 4 / qwen / 미래 모델별 prompt template)
- Cache prompt-versioning (prompt 변경 시 cache_key 자동 invalidate)
- Phase 6f-5에서 import path / 함수 안 hardcode 결정 미룬 영역 정리

**DoD**
- Prompt 변경 → cache miss 자동
- 모델별 prompt template 명시적 분리
- LLMClient interface clean (transport vs prompt 분리)

**Versioning**: v0.9 일부

---

### Phase 6f-7 — Verification 자동화 ⬜
(Phase 6f-5 Option B (e) 위임)

**Deliverable**
- Rollback runbook script (.env backup + sglang docker swap + ht_lens restart 자동화)
- CI 통합 강화 (PR마다 회귀 + coverage 임계값)
- E2E smoke test 자동화 (현재 manual curl)

**DoD**
- `./scripts/rollback.sh <model_name>` 실행으로 rollback 자동
- CI에서 coverage 임계값 강제
- E2E test가 pytest로 실행 가능 (LLM mock 또는 live)

**Versioning**: v0.9 일부

---

### Phase 6e-3 — Status 마킹 Provider 인식 ⬜
(Phase 6e-2 scope-out)

**Deliverable**
- `_finalize_document_status`가 provider 종류 인식
- mock provider 사용 시 status='translated_mock' 또는 'translated' 마킹 skip
- 일부 block만 성공한 case 정확 status (실패 block 비율 기반)

**DoD**
- Mock provider run → documents.status 'translated' 안 됨
- 부분 실패 → status='partial' 새 값 또는 명확한 의미
- 회귀 0

**위험**: 기존 documents 데이터의 status 호환성

**Versioning**: v0.9 일부 (low priority, .env fix로 root cause 해결됨)

---

### Phase 6g — UI Polish Residual ⬜
(이전 Phase 6e Polish Pack의 잔여)

**Deliverable**
- 핀 표시 더 직관적 (색깔/크기/위치, 멀티 thread 표시)
- 사이드바 리사이즈 (좌우 드래그, 200px ~ 500px)
- 작은 이미지/도표 클릭 시 확대 모달
- streaming 응답 (SSE) — Phase 5 debt
- 백그라운드 작업 패널 (Phase 6d 기반 확장)
- Playwright 자동 시나리오 — Phase 5 debt
- CI jsdom 설치 — Phase 5/6b debt
- LLM-driven thread title — Phase 5 debt
- (선택) 모델 빠른 토글 UI — Phase 6e 인프라 활용

**Versioning**: v0.9

---

### Phase 6h — Extraction Quality + 후처리 ⬜

**Deliverable**

기존 (Phase 1 known issues):
- header heuristic 보강 (49,738 block 중 190만 header)
- 멀티컬럼 reading order
- 표 cell + figure 안 텍스트 분리 (Phase E1.5 발견: 64.7% short fragment)
- samples.md determinism 검증
- 회전 페이지 bbox→pixel 정밀 매핑
- + 큰 fixture (52+ 페이지) 추가

추가 (사용자 Phase 6f-5 발견 issues):
- **Issue B 후처리**: 번역 일관성 강화 (영어 leak 검출 + 자동 재시도 rule)
- 자동 요약 hierarchical (Phase 6d debt, 1000+ 페이지 PDF)

**DoD**
- 3 fixture에서 header 정확도 ≥ 90%
- 멀티컬럼 PDF에서 reading order 시각적 검증
- 표 cell fragment skip/grouping (cost ↓, 품질 ↑)
- 자동 요약이 첫 N pages 아닌 전체 문서 반영
- 영어 leak 자동 검출 + 재번역 rule 동작

**위험**: Phase 1 코드 회귀, snapshot test 다수 갱신

**Versioning**: v1.0

---

### Phase 6h-1 — Section-level Chat Context ⬜
(사용자 Phase 6f-5 발견 Issue C)

**Deliverable**
- 현재 chat context (block ±2, page boundary 고정) 확장
- header 인식 + section boundary detect
- "same_section" 옵션 (radius 외)
- Cross-page lookup 가능
- UI에서 "이 section 선택" 멀티 block 가능 (선택)

**DoD**
- 사용자가 "이 section 전체에 대해 설명" 질문 가능
- 1000+ 페이지 PDF에서 section grouping 정확
- chat 응답이 본 block 외 같은 section context 반영

**선행 조건**: Phase 6h header heuristic 보강

**Versioning**: v1.0 일부

---

### Phase 6h-2 — 번역 언어 옵션 UI/API ⬜
(사용자 Phase 6f-5 발견 Issue A)

**Deliverable**
- Upload API에 src/tgt 파라미터 추가
- UI에 lang selector (en→ko / ko→en / en→ja 등)
- 사후 retranslate 시 방향 override
- `extract/language.py` langdetect ko/en 외 확장 (ja/zh)
- Phase 6f-5의 src_norm 분기 인프라 사용

**DoD**
- 한국어 PDF 업로드 → 영어로 번역 옵션 동작
- UI에서 명시적 lang 토글
- documents row의 src/tgt 변경 API (선택)

**Versioning**: v1.0 일부

---

## Evaluation Track

ht_lens 도메인 코드 영향 0. 외부 sandbox (`~/llm_eval/`)에서 prod 모델 결정용.

### Phase E1 — Baseline Translation Evaluation ✅
**완료** (2026-05-22)
- ~/llm_eval/ sandbox + Python venv 분리
- 평가셋 eval_v1.jsonl (~580 sample), 6 카테고리
- 비교 모델 5개: qwen3.6-27b, Hy-MT2-7B (BF16/4bit), NLLB-200-1.3B, M2M-100-1.2B
- 결과: qwen 5/6 카테고리 우세, NLLB/M2M ML 도메인 부적합

### Phase E1.5 — Large Model Comparison ✅
**완료** (2026-05-23, **본문 KR 측정 누락 → Phase 6f-1 잘못된 결론**)
- 평가셋 확장 v2 (~739 sample)
- 큰 PDF 4개 ingest: Murphy PML 1370p, Aggarwal RecSys 518p, Open-Sora arXiv, 2603.03482v1
- 비교 모델 7개 중 5개 성공: qwen3.6-27b (baseline), Hy-MT2-30B-A3B 4bit, Gemma-4-31B-IT 4bit, Gemma-4-26B-A4B-IT BF16, Gemma 4 E2B/E4B
- 실패: Qwen3.6-35B-A3B-FP8 (deep-gemm 의존성), TranslateGemma-27B (gated), DeepSeek-V4-Flash (149GB > 85GB GPU)
- chrF + LLM-judge: Gemma 4 26B-A4B 우세 → Phase 6f-1 swap 결정
- **사후 학습**: 본문 KR 누락 → Phase 6f-5 rollback

### Phase E1.5 보완 — qwen A/B Re-measurement ✅
**완료** (2026-05-23)
- block 분류 (15 카테고리: pure_text / fragment / author_list / arxiv_meta / 등)
- 본문 (pure_text) 일관성 측정: qwen 78.9% vs gemma 42.9%
- Prompt A/B test: gemma_v2_ko 0.755 vs qwen_v2_ko 0.874
- qwen A/B broken (raw HTTP에서 thinking mode 활성) → root cause fix (chat_template_kwargs top-level)
- Matched-block 14/0 qwen 우세 → Phase 6f-5 rollback 결정

### Phase E2 — LoRA Fine-tune (Conditional) ⬜
**Entry condition**: 실 PDF 번역 사용 시 부족 영역 명확히 식별. 만족 시 skip.

**ROI 재평가**: qwen baseline 0.867 이미 강함. Fine-tune 효과 작을 가능성. 진입 결정 신중.

**Deliverable** (보존)
- Base: qwen3.6-27b 또는 다른 모델
- 데이터 4 소스 통합:
  - AI Hub Tech-Science 한-영 corpus (~1.6M, 회원가입 필요)
  - ht_lens 4 PDF + Claude/GPT 합성 reference
  - arXiv abstract bilingual
  - ufal/bilingual-abstracts-corpus
- Framework: Unsloth + LLaMA-Factory 또는 PEFT

**DoD**
- 부족 영역 카테고리에서 chrF ≥ +3 개선
- 회귀 카테고리 없음
- LLM-judge: base 대비 우세 카테고리 ≥ 2/3

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
| v0.8.5 ✅ | Phase 6f-1 → 6f-5 완료 | prod swap Gemma 4 → qwen rollback + v2_ko prompt |
| v0.9 ⬜ | Phase 6f-3 + 6f-6 + 6f-7 + 6e-3 + 6g 완료 | Graceful shutdown + prompt policy + 자동화 + status fix + UI polish |
| v1.0 ⬜ | Phase 6h + 6h-1 + 6h-2 (+ E2 conditional) 완료 | 추출 품질 + section context + lang UI |

---

## Risks & Open Questions

- **Block grouping 정확도**: 멀티컬럼/표/캡션에서 휴리스틱이 자주 깨진다.
  Phase 1에서 80% 잡고 진행, Phase 6h에서 보강.

- **표/figure fragment 처리**: Phase E1.5 발견 — book2.pdf의 text block 중 64.7%가
  1~30 char fragment. 현재는 다 번역하지만 cost만 늘리고 의미 부정확. Phase 6h.

- **공유 GPU 환경**: DGX Spark의 sglang은 다른 사용자/세션과 공유. latency 변동 가능.

- **Reasoning model의 thinking 토글**: qwen3.6 prod 운영 시 `enable_thinking=false` 명시 필요.
  raw HTTP에선 `chat_template_kwargs` top-level (extra_body 안 nested 아님).
  ht_lens는 OpenAI SDK 사용 → 정상.

- **번역 일관성 (사용자 발견 Issue B)**: qwen + v2_ko로 본문 KR 0.96 달성.
  Phase 6h에서 후처리 강화 (영어 leak 검출 + 자동 재시도).

- **Chat context 큰 틀 grouping (사용자 발견 Issue C)**: 현재 block ±2 + page boundary.
  Phase 6h-1에서 section-level 확장.

- **번역 언어 옵션 (사용자 발견 Issue A)**: 현재 en→ko 단일. UI 토글 + 다른 방향 지원.
  Phase 6h-2.

- **폰트 fitting**: bbox에 텍스트 욱여넣기. 한글은 영문 대비 폭/높이 다르다.

- **Reading order**: 채팅 맥락 품질에 직결. Phase 6h.

- **로컬 모델 품질**: qwen3.6-27b prod 운영 중. baseline 강함 (본문 KR 0.867).
  Phase E2 fine-tune ROI 신중 평가 (효과 작을 가능성).

- **평가 framework 한계 (Phase 6f-1 → 6f-5 학습)**: chrF + LLM-judge만으로 부족.
  본문 KR (한국어 일관성) 측정 의무. fragment 분리 + pure_text 통계.

- **자동 요약 hierarchical**: Phase 6d debt. 1000+ 페이지 PDF는 첫 N pages만 요약이라 부정확.
  Phase 6h.

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
  + sglang Docker image (qwen 공유, 정리 안 함)
  + `.env.backup.gemma4_*` (Phase 6f-5 진행 중 자동 생성)
  → re-swap 시간 ~3분
- **ht_lens 서버**: 8080
- **DB**: `data/ht_lens.db`
  - 7 documents ingest됨 (sample_mixed, phase6d_demo 2개, Open-Sora arXiv, 2603.03482v1, Aggarwal RecSys textbook 518p, Murphy PML 1370p)
  - Translations: qwen3.6-27b (대부분, Phase 6f-5 이후) + Gemma 4 26B-A4B-IT 654건 (Phase 6f-1 시기, 보존)
- **평가 sandbox**: `~/llm_eval/`
  - eval_v1.jsonl (Phase E1, 580 sample)
  - eval_v2.jsonl (Phase E1.5, 739 sample)
  - block_classification.json (15 카테고리)
  - prompt A/B 결과 (Gemma 4 × 3 + qwen × 3, fixed pattern)
