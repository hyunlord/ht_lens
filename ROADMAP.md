# ht_lens — Development Roadmap

## Vision

PDF(한/영) 학술 문서를 **레이아웃 구조를 이해해서 한국어로 가장 잘 읽히게 재구성**하고,
수식·그림·표를 보존하며, 블록 단위로 클릭해 AI 설명·질문을 주고받고, 그 대화를
핀과 함께 저장·관리하는 **로컬 학술 번역 도구**.

**전환 (2026-05-28)**: ht_lens 1.x (PyMuPDF + overlay)의 근본 한계를 사용자 실사용으로
발견 → sandbox 검증 → **ht_lens 2.0 (MinerU + reflow) 재설계 진입**.

**v2.0 비전 (Phase 7)**: cross-document RAG (Phase 7a 완료) + user profile/persona,
memory system, learning progress → "내 학습 동반자". (Phase 8 reflow 토대 위에서.)

---

## ⚠️ 1.x → 2.0 전환 (2026-05-28)

### 1.x 근본 한계 (사용자 실사용 발견)
- 추출: PyMuPDF (좌표 + 텍스트만, 레이아웃 구조 이해 못 함)
- 렌더: bbox에 번역 overlay 덮기 → 욱여넣기
- 증상: Pattern A (multi-line bbox leak 15.5%), B (body missing 4.78%), C (figure caption), 폰트 축소, 수식 깨짐
- **근본 원인**: "PDF를 똑같이 재현 + 번역 덮기" 가정 자체

### 2.0 검증 (sandbox ~/mineru_test/, 완료)
- **MinerU 추출**: 7 headers, 수식 0 fragment, figure 분리 (PyMuPDF 압도)
- **번역 완성본**: 사용자 확인 "훨씬 나은데" (진짜 한국어 학술서)
- **inline 수식 placeholder 보호**: byte-identical, KaTeX 에러 0
- **reflow reading view**: header 강조 + 문단 + KaTeX + figure inline + caption 번역

### 2.0에서 폐기 (1.x)
- PyMuPDF 추출 → MinerU
- overlay 렌더 + bbox 정합 로직
- Pattern A/B/C fix (PyMuPDF 한계라 MinerU에서 증발)
- Phase 6h hot-fix A1 (warning border, overlay 안 씀)
- Phase 6h-1 backfill 나머지 (doc 5/6/7, overlay 시대 작업)

### 2.0에서 재사용 (1.x 자산)
- 번역: qwen3.6-27b + v2_ko prompt ✅ (+ placeholder 수식 보호 신규)
- KaTeX: Phase 6i ✅
- 채팅/핀: Phase 5 (chunk 단위 재anchor)
- RAG: Phase 7a 인프라 (block_id → chunk_id rename)
- Throughput: Phase 7a-2 (5.66x, chunk 번역에 적용)
- Auto-embed: Phase 7a-3

---

## Architecture Overview (2.0 목표)

```
PDF
 │
 ▼
[MinerU 추출] ─► content_list.json (item별 type/level/bbox/page/latex/caption)
 │              + figure 이미지 파일 분리
 ▼
[Ingest] ─► SQLite (chunk schema, item-level)
 │
 ▼
[Translator] ─► chunk 번역 (qwen + v2_ko + 수식 placeholder 보호)
 │              (Phase 7a-2 5.66x concurrency 재사용)
 ├──► [Embedding] ─► chunk_embeddings (bge-m3, block→chunk rename)
 │
 ▼
[FastAPI]
 │
 ▼
[Reflow Viewer]
 - 단일 reading view (학술 번역본): header 강조 + 문단 + KaTeX + figure inline + caption
 - 좌우 비교 토글 (원문 PDF | reflow, chunk bbox로 sync)
 - 클릭 → 채팅 (chunk + 이웃 context, figure는 caption+이웃 텍스트 기반 — vision 불필요)
 - 핀 + 질문 리스트
                                    └─ qwen3.6-27b FP8 (sglang 8081) + v2_ko
```

핵심 단위: **chunk** (1.x의 block을 item-level로 일반화). 번역·표시·임베딩·질문 단위.

---

## Tech Stack

| 영역       | 선택                                                                  |
| ---------- | --------------------------------------------------------------------- |
| Backend    | Python 3.11, FastAPI, SQLAlchemy 2.0 async, SQLite                    |
| PDF 추출   | **MinerU** (content_list.json, 레이아웃 이해) — 2.0 (CPU 1회성)       |
| LLM        | sglang qwen3.6-27b FP8 + v2_ko prompt                                |
| Vector DB  | numpy brute-force (chunk scale 충분)                                  |
| Embedding  | BAAI/bge-m3 (1024d, multilingual)                                    |
| 수식 렌더  | KaTeX (Phase 6i 재사용) + placeholder 보호                            |
| Frontend   | vanilla HTML/JS (reflow viewer 신규)                                 |
| Dev tools  | uv, ruff, mypy strict, pytest, GitHub Actions                        |

**GPU 노선**: 하이브리드. 텍스트 LLM (sglang) 작동, MinerU 추출은 CPU 1회성
(GB10 Blackwell sm_120에서 paddle/torch GPU vision 전부 abort → vision 제외로 우회).

---

## Data Model

### 1.x (현행, 병행 보존)
```text
documents, pages, blocks (bbox, type, original_text), translations (block_id),
threads, messages, jobs, summaries, block_embeddings
→ 1.x DB 무손상 롤백 보존
```

### 2.0 (신규, Phase 8a)
```text
documents     (id, filename, src_pdf_sha256, src_lang, tgt_lang, status, created_at)
pages         (id, doc_id, page_num, width, height, bg_image_path)
chunks        (id, doc_id, page_idx, order_idx, type, text_level,
               bbox_json, content, text_format, image_path, image_caption)
                  type ∈ {text, title, equation, image, table, ...}  ← MinerU content_list
chunk_translations (chunk_id PK, translated_text, model, status, cache_key, updated_at)
threads       (id, chunk_id, title, created_at)        ← block_id → chunk_id
messages      (id, thread_id, role, content, model, created_at)
jobs, summaries
chunk_embeddings (chunk_id PK, model, dim, vector BLOB, source_hash, updated_at)
```

병행 DB 전략: 1.x DB 보존 + 2.0 새 DB. cutover 후 1.x는 롤백 자산.

---

## Phases — Completed 1.x (v0.1 ~ v1.6)

### Phase 0 — Skeleton & Harness ✅
### Phase 1 — PDF Extractor ✅ (PyMuPDF — 2.0에서 MinerU로 폐기)
- Known issues가 2.0 전환 근거가 됨 (multi-line bbox, body missing, reading order)
### Phase 2a — DB + LLMClient + Ingest ✅
### Phase 2b — Translation Pipeline ✅ (v0.1)
- ~~sequential bug~~ → Phase 7a-2 fix
### Phase 3 — FastAPI Server ✅
### Phase 4 — Viewer Frontend ✅ (v0.2, overlay — 2.0에서 reflow로 폐기)
### Phase 5 — Chat Panel + Pins + Question List ✅ (v0.3) — 2.0 재사용
### Phase 6a — Critical UX gaps ✅ (v0.4)
### Phase 6b — Viewer Rework ✅ (v0.5, overlay 좌우비교)
### Phase 6c — Viewer Polish ✅ (v0.6)
### Phase 6d — File Management + Summary ✅ (v0.7)
### Phase 6e — LLMClient Infrastructure Split ✅
### Phase 6e-2 — CLI .env Load + Fail-closed Provider ✅ (v0.8)
### Phase 6f-1 → 6f-5 — Production Model 결정 ✅ (v0.8.5)
- qwen rollback + v2_ko prompt. doc 4 KR 0.859.

### Phase 7a — Cross-document RAG ✅ (v1.5)
- block_embeddings + numpy brute-force, bge-m3, cross-doc top-K
- 508 tests, E2E /explain top-1 1.00

### Phase 7a-2 — Throughput Optimization ✅
- Sequential bug fix → asyncio.as_completed + Semaphore(7)
- **Mock 5.66x → Live 4.5x** (doc 7 36K block 4h 20m)
- RAG stored vector reuse 0.18ms, 521→533 tests

### Phase 7a-3 — CLI Auto-embed 영구화 ✅ (v1.6)
- factory.from_env() 3 caller 통합, --no-embed flag
- doc 7 live 검증 (single command auto-embed chain)
- 533 tests, **v1.6 마일스톤**

### Phase 6g (일부) — Viewer 페이지 공백 hot-fix ✅
- 48px → 17px + 페이지 경계 border (overlay 시대, 2.0에서 무관)

### Phase 6h — Extraction Quality (1.x overlay 시대, 2.0에서 대부분 폐기)
- **전수조사 (2026-05-27)**: Pattern A 6,912 blocks (15.5%), B 93 pages (4.78%), C 5,243 image blocks
- **이 audit이 2.0 전환의 데이터 근거** (overlay 근본 한계 증명)

#### Phase 6h hot-fix A1 — Warning border ⬜ → ❌ 폐기 (2.0 overlay 안 씀)
#### Phase 6h-1 — Pattern A Fix (multi-line bbox) ✅ → 2.0에서 무관
- doc 4 backfill: Severe Pattern A 15→0, translation/embedding 보존
- 552 tests. **단 2.0 reflow에선 bbox overlay 안 써서 이 fix 자체가 불필요해짐**
- doc 5/6/7 backfill ⬜ → ❌ 폐기 (2.0 전환)

### Phase 6i — LaTeX Rendering (KaTeX) ✅ — 2.0 재사용
- KaTeX 0.16.22 vendored, viewer + chat 렌더
- currency $5.00 skip, throwOnError graceful
- Cache-Control no-cache fix (StaticFiles stale cache regression)
- 575 tests. **2.0 reflow + placeholder 수식 보호의 토대**

---

## Phases — ht_lens 2.0 (Phase 8 시리즈)

마스터 플랜: `.claude/phases/phase-8/MASTER-PLAN.md` (286줄, 실측 인벤토리 근거).
확정 결정: A item-level / B 병행DB clean 재추출 / C 하이브리드 CPU 추출 /
D figure 텍스트 기반 채팅 / E 좌우비교 토글 유지 / F 8a→8b→(8c∥8d)→8e.

### Phase 8a — MinerU 추출 + Chunk Schema + Ingest ⬜ (착수)
**Deliverable**
- MinerU 추출 파이프라인 (content_list.json 소스)
- chunk schema (item-level: type/level/bbox/page/latex/caption)
- ingest (content_list → chunks)
- figure 이미지 파일 분리 저장
- CPU 추출 (Blackwell GPU 우회)

**DoD**
- doc 7 한 챕터 MinerU 추출 → chunk DB ingest 성공
- chunk가 bbox/page/type/latex/caption 보존
- figure 이미지 분리 + 경로 저장
- 1.x DB 무손상 (병행)

**위험**: MinerU CPU 추출 속도 (1370p ~5h), content_list 스키마 안정성

**예상**: ~3-5일

**Versioning**: v2.0-a

### Phase 8b — Chunk 번역 + Embeddings ⬜
**Deliverable**
- chunk 번역 (qwen + v2_ko + **placeholder 수식 보호** 신규)
- Phase 7a-2 concurrency 머신 재사용 (block→chunk 일반화)
- chunk_embeddings (block_id→chunk_id rename)
- 이웃 chunk를 번역 context로 (item-level 문맥 보강)

**DoD**
- chunk 번역 + 수식 placeholder byte-identical 보존
- embedding 생성
- Phase 7a-2 5.66x 적용

**예상**: ~2-3일 (재사용이라 짧음)

**Versioning**: v2.0-b

### Phase 8c — Reflow Viewer ⬜
**Deliverable**
- 단일 reading view (학술 번역본)
- header 강조 + 문단 + KaTeX 수식 + figure inline + caption 번역
- 좌우 비교 토글 (원문 PDF | reflow, chunk bbox sync)
- sandbox result_v2.html seed 활용

**DoD**
- doc 7 챕터 reflow 읽기 자연스러움 (sandbox 품질)
- 좌우 비교 hilight sync (chunk bbox)
- KaTeX 렌더 (Phase 6i 재사용)

**예상**: ~4-6일 (frontend 신규)

**Versioning**: v2.0-c

### Phase 8d — Chat/핀/RAG Chunk 재anchor ⬜
**Deliverable**
- 채팅/핀 chunk 단위 재배치 (Phase 5 재사용)
- RAG chunk_embeddings (Phase 7a 재사용)
- figure on-demand 채팅 (caption + 이웃 chunk → qwen, vision 불필요)

**DoD**
- chunk 클릭 → 채팅 (context 자동)
- figure 클릭 → caption+이웃 기반 설명
- 핀 chunk anchor
- cross-doc RAG (chunk)

**예상**: ~4-6일

**Versioning**: v2.0-d

### Phase 8e — 7 docs 마이그레이션 + Cutover ⬜
**Deliverable**
- 7 docs MinerU 재추출 + 재번역 + 재임베딩
- 1.x → 2.0 cutover
- 1.x DB 롤백 자산 보존

**DoD**
- 7 docs 2.0 DB 완료
- reflow viewer에서 전체 읽기
- 1.x 롤백 가능

**예상**: ~2-3일 + 배치 (CPU 추출 시간)

**Versioning**: **v2.0 마일스톤**

---

## Phases — Pending (1.x 잔여, 2.0과 무관하게 유효)

### Phase 6f-3 — Graceful Shutdown ⬜ (v0.9)
### Phase 6f-6 — Prompt Policy Layer ⬜ (v0.9)
### Phase 6f-7 — Verification 자동화 (rollback runbook, CI) ⬜ (v0.9)
### Phase 6e-3 — Status 마킹 Provider 인식 ⬜ (v0.9, low)

---

## Phase 7 — Personalization Agent (Phase 8 reflow 토대 위)

### Phase 7a — Cross-document RAG ✅ (v1.5)
### Phase 7a-2 — Throughput ✅ / Phase 7a-3 — Auto-embed ✅ (v1.6)
### Phase 7b — User Profile + Persona ⬜ (v2.x)
### Phase 7c — Memory System ⬜ (v2.x)
### Phase 7d — Learning Progress ⬜ (v2.x)
### Phase 7e — Persona UI ⬜ (v2.x)
- Phase 8 (2.0 reflow) 완료 후 진입

---

## Evaluation Track

### Phase E1 / E1.5 / E1.5 보완 ✅ — qwen + v2_ko 확정
### Phase E2 — LoRA Fine-tune (Conditional) ⬜ — ROI 신중

---

## Versioning

| 버전     | 시점                        | 의미                                                  |
| -------- | --------------------------- | ----------------------------------------------------- |
| v0.1~0.8.5 ✅ | Phase 2a~6f-5          | (1.x: CLI→브라우저→Q&A→검색→비교→polish→업로드→모델)  |
| **v1.5 ✅** | **Phase 7a**            | Cross-doc RAG                                         |
| **v1.6 ✅** | **Phase 7a-2 + 7a-3**   | Throughput 5.66x + auto-embed (live 검증)             |
| (1.x 완) | Phase 6g/6h-1/6i        | overlay polish + Pattern A fix + LaTeX (KaTeX 2.0 재사용) |
| **v2.0-a ⬜** | **Phase 8a**          | MinerU 추출 + chunk schema                            |
| v2.0-b ⬜ | Phase 8b                | chunk 번역 + embeddings                               |
| v2.0-c ⬜ | Phase 8c                | reflow viewer                                         |
| v2.0-d ⬜ | Phase 8d                | chat/핀/RAG chunk 재anchor                            |
| **v2.0 ⬜** | **Phase 8e**            | **7 docs 마이그레이션 + cutover (학술 번역 도구 완성)** |
| v2.x ⬜  | Phase 7b/c/d/e          | Personalization agent (reflow 토대 위)                |

---

## Risks & Open Questions

### 2.0 전환
- **MinerU CPU 추출 속도**: GB10 Blackwell GPU 미작동 (paddle/torch abort). CPU 1회성 (1370p ~5h). 7 docs 배치.
- **MinerU content_list 스키마**: type/level/bbox/latex 안정성. 버전 변경 대비.
- **chunk 번역 문맥**: item-level이라 단락 단독. 이웃 chunk context로 보강 (검증됨).
- **reflow viewer 신규**: frontend 큰 작업 (~4-6일).
- **좌우 비교 sync**: chunk bbox 정확도 의존 (MinerU 정확 → 1.x보다 쉬움).
- **figure 채팅**: caption + 이웃 텍스트 기반 (vision 불필요). 품질은 텍스트 context에 의존.

### Blackwell GPU (별도 트랙, 선택)
- paddle/vLLM sm_120 빌드 (2-3일) → MinerU GPU 가속 가능. 단 vision 뺐으므로 추출만, 우선순위 낮음.

### 보존 (1.x 학습)
- 평가 protocol: chrF + LLM-judge + 본문 KR
- sglang effective_max_running_requests_per_dp = 7
- HF_HOME fix (2026-05-26)

---

## Workflow Conventions

- Phase 브랜치 + PR, Conventional Commits
- Phase 종료: ROADMAP ⬜→✅ (Worker 금지, 사용자 직접)
- Cross-verify phase당 max 2회, R2 후 Planner micro-fix 허용
  (선례: 6e/6e-2/6f-5/7a/7a-2/7a-3/6h-1/6i)
- Hot-fix: 작은 ops는 정식 phase 우회 (6g page spacing 선례)
- Evaluation Track은 도메인 코드 0
- **2.0 전환 원칙**: 1.x DB 무손상 병행 보존, sub-phase 단계적, sandbox 검증 완료 자산 인계

---

## prod 운영 메모 (2026-05-28 현재)

### 1.x (현행 운영)
- prod 모델: qwen3.6-27b FP8 (sglang docker 8081) + v2_ko
  - speculative decoding NEXTN (EAGLE 4 steps, 51% accept)
  - context 32768, mem 0.70 → ~90GB, effective_max_running 7
- embedding: bge-m3 (1024d, CPU)
- translation concurrency 7 (Phase 7a-2, live 4.5x)
- ht_lens 8080
- DB: `data/ht_lens.db` — 7 docs / 1,946 pages / 49,850 blocks / 44,607 translations / 17,257 embeddings / 17 threads
  - doc 4: Phase 6h-1 backfill 적용 (단 2.0에서 무관)
- rollback: Gemma 4 26B-A4B-IT weights 49GB → ~3분

### 2.0 (재설계 진행)
- 마스터 플랜: `.claude/phases/phase-8/MASTER-PLAN.md`
- sandbox: `~/mineru_test/` — MinerU 추출 + 번역 + figure 파이프라인 검증 완료
  - output_body/doc7_body_ko_v2.md (수식 보호 번역)
  - figure_desc.json, result_v2.html (reflow seed)
- 착수: Phase 8a (MinerU 추출 + chunk schema)
- GB10 Blackwell: 텍스트 LLM OK, GPU vision abort → 추출 CPU 1회성

### 평가 sandbox
- `~/llm_eval/`: eval_v1/v2.jsonl, block_classification.json, prompt A/B
