# ht_lens 2.0 — Master Plan (MinerU + Reflow)

> 이 문서는 **마스터 플랜**이다. 단일 phase가 아니라 sub-phase 8a~8e의 우산.
> 코드 구현 없음 — 아키텍처/데이터모델/마이그레이션/자산매핑/sub-phase 분해 + 사용자 결정 항목.
> 각 sub-phase는 시작 시 자체 plan→debate→challenge→verify→verify-cross→summary 사이클을 돈다.
> ROADMAP/WORKFLOW/CLAUDE/AGENTS 및 1.x 코드는 이 플랜 확정 전까지 손대지 않는다.

작성일 2026-05-30. sandbox 검증 (`~/mineru_test/`) 근거.

---

## 0. 전환 근거 (검증 완료)

| 축 | 1.x (PyMuPDF + overlay) | 2.0 (MinerU + reflow) | 검증 |
| --- | --- | --- | --- |
| 추출 | 좌표 + 텍스트만. heading/수식/그림 구분 못 함 | 구조화 markdown. heading level, `$$`수식 통째, figure 분리 | §28.4 3p: PyMuPDF 165 block (수식 27 fragment, header 0) vs MinerU 71줄 (header 7, 수식 fragment 0, figure 3) |
| 렌더 | bbox 덮기 → 폰트 축소, 수식 깨짐 | 자연 흐름 reading view + KaTeX + figure inline | 사용자 확인 "훨씬 나은데" |
| 수식 | overlay에 raw 노출 | placeholder 보호 번역, byte-identical, KaTeX 에러 0 | v2 번역: inline 33→35, leftover placeholder 0 |
| Pattern A/B/C | PyMuPDF 한계라 영구 미해결 | 추출 단계에서 증발 | — |

**결론: 2.0 정식 진입.** 단 sub-phase 단계적, 1.x 보존(롤백 가능).

---

## 1. 목표 아키텍처

```
PDF
 │  ┌─ 8a ─────────────────────────────────────────────┐
 ▼  │                                                    │
[MinerU 추출] ─► content_list.json (typed, ordered)      │
 │   - type: text / header / equation / image / table     │
 │   - text_level (heading depth), text_format=latex      │
 │   - bbox + page_idx (★ PDF 좌표 보존 → 좌우비교 가능)  │
 │   - image_caption, img_path (figure 파일 분리)         │
 ▼                                                        │
[Ingest] ─► SQLite: chunks (markdown chunk 기반 신 schema)│
 └────────────────────────────────────────────────────────┘
 │  ┌─ 8b ─────────────────────────────────────────────┐
 ▼  │                                                    │
[Translator] ─► chunk 번역                                │
 │   - qwen3.6-27b + v2_ko (재사용)                       │
 │   - ★ 수식 placeholder 보호 (신규, 검증됨)             │
 │   - concurrency 7 / cache / dedup (Phase 7a-2 재사용)  │
 ├─► [Embedding] ─► chunk_embeddings (bge-m3, block→chunk)│
 └────────────────────────────────────────────────────────┘
 │  ┌─ 8c / 8d ────────────────────────────────────────┐
 ▼  │                                                    │
[FastAPI] ─► chunk API (routers 재작성)                   │
 ▼                                                        │
[Reflow Viewer] (신규)                                    │
 │   - 단일 reading view: header 강조 + 문단 + KaTeX     │
 │     + figure inline + caption 번역                     │
 │   - 클릭 → 채팅 (chunk + 주변 context, 텍스트 기반)    │
 │   - 핀 + 질문 리스트 (chunk 단위 재배치)               │
 │   - 좌우 비교 (원문 PDF page | reflow) — bbox로 가능   │
 └────────────────────────────────────────────────────────┘
        └─ 8e: 7 docs 마이그레이션 + cutover ─┘
```

---

## 2. 데이터 모델 (결정 A)

### 현행 (1.x)
```
documents(id, filename, src_lang, tgt_lang, status, sha256, summary, ...)
pages(id, doc_id, page_num, width, height, bg_image_path, rotation, render_dpi, pixel_w, pixel_h)
blocks(id, page_id, block_local_id, type, bbox_json, order_idx, original_text)
translations(block_id PK, translated_text, model, status, cache_key, updated_at)
block_embeddings(block_id PK, model, dim, vector BLOB, source_hash, updated_at)
threads(id, block_id, title) / messages(id, thread_id, role, content, model)
```

### 신규 (2.0) — 권장: **item-level chunk**
MinerU `content_list.json`의 한 항목 = 한 chunk. block→chunk는 거의 1:1 rename + 필드 확장.

```sql
-- documents: 재사용 + extractor 컬럼 추가
ALTER documents ADD extractor VARCHAR DEFAULT 'pymupdf'  -- 'mineru' for 2.0
ALTER documents ADD markdown_path VARCHAR NULL           -- MinerU .md 원본 보관

-- pages: 재사용 그대로 (page render PNG = 좌우비교 좌측 + figure crop fallback)

CREATE TABLE chunks (
    id            INTEGER PRIMARY KEY,
    doc_id        INTEGER NOT NULL REFERENCES documents(id),
    seq           INTEGER NOT NULL,             -- reflow 순서 (content_list index)
    type          VARCHAR NOT NULL,             -- text|header|equation|image|table|caption
    text_level    INTEGER NULL,                 -- heading depth (h2=2 ...), null=본문
    original_text TEXT NOT NULL,                -- markdown/latex 원문 (equation은 $$...$$)
    text_format   VARCHAR NULL,                 -- 'latex' for equations
    page_idx      INTEGER NOT NULL,             -- ★ 원본 PDF 페이지 (0-based)
    bbox_json     VARCHAR NOT NULL,             -- ★ [x0,y0,x1,y1] PDF pt
    img_path      VARCHAR NULL,                 -- figure/table 이미지 상대경로
    caption_text  TEXT NULL                     -- figure caption 원문
);
CREATE INDEX ix_chunks_doc_seq ON chunks(doc_id, seq);

CREATE TABLE chunk_translations (
    chunk_id        INTEGER PRIMARY KEY REFERENCES chunks(id) ON DELETE CASCADE,
    translated_text TEXT NOT NULL,
    caption_translated TEXT NULL,              -- figure caption 번역 (별도)
    model           VARCHAR NOT NULL,
    status          VARCHAR NOT NULL,
    cache_key       VARCHAR NULL,
    updated_at      DATETIME NOT NULL
);
CREATE INDEX ix_chunk_tr_cache ON chunk_translations(cache_key);

CREATE TABLE chunk_embeddings (   -- block_embeddings 와 동형, PK만 chunk_id
    chunk_id    INTEGER PRIMARY KEY REFERENCES chunks(id) ON DELETE CASCADE,
    model       VARCHAR NOT NULL, dim INTEGER NOT NULL,
    vector      BLOB NOT NULL, source_hash VARCHAR NOT NULL, updated_at DATETIME NOT NULL
);

-- threads: block_id → chunk_id. messages 그대로.
CREATE TABLE threads (id, chunk_id REFERENCES chunks(id), title, created_at)
```

### 옵션 비교
| | (a) item-level **[권장]** | (b) section-level | (c) hybrid |
| --- | --- | --- | --- |
| chunk 정의 | content_list 항목 1개 | heading 아래 묶음 | item 저장 + 번역시 묶음 |
| MinerU 매핑 | 1:1, 가장 단순 | 후처리 병합 필요 | 복잡 |
| bbox/page 보존 | ✅ chunk마다 | ✗ 섹션이 여러 페이지 걸침 | ✅ |
| figure inline 위치 | ✅ 정확 | △ | ✅ |
| 번역 문맥 | 항목이 이미 문단 단위 (MinerU가 병합). 부족하면 이웃 chunk를 context로 전달 (chat_context ±radius 패턴 재사용) | ✅ 섹션 통째 | ✅ |
| embedding 입도 | text chunk 단위 (필요시 섹션 rollup) | 섹션 | 유연 |
| 구현 비용 | 낮음 | 중 | 높음 |

**권장 근거**: §28.4 검증에서 MinerU text 항목은 대부분 완결 문단. "where" 같은 fragment은 수식 사이 끼인 짧은 연결어뿐 — 이웃-context 전달로 해결. item-level이 bbox/figure/reflow 순서를 가장 깨끗이 보존.

---

## 3. 마이그레이션 (결정 B)

### 옵션
- **(a) clean 재추출**: 7 docs MinerU 재추출 + 재번역 + 재임베딩.
- **(b) translation 재활용**: cache_key = hash(text, src, tgt, model). MinerU segmentation ≠ PyMuPDF (병합/spacing 보정) → 대부분 cache miss. 일부 동일 문단만 우연 hit. **전용 마이그레이션 엔지니어링 가치 낮음** — 단, chunk 번역이 기존 `translations.cache_key` 테이블을 그대로 조회하면 *공짜 부분 재사용*은 자동으로 얻음.
- **(c) 병행 DB**: 1.x `ht_lens.db` 보존, 2.0 `ht_lens_v2.db` 신규. 전환기 두 viewer 공존.

### 권장: **(c) 병행 DB + (a) clean 재추출**, cache_key 기회적 조회
- 1.x DB 무손상 (롤백 안전망)
- 2.0는 빈 DB에서 시작, 신 schema, 신 alembic chain
- chunk 번역이 1.x translations 테이블의 cache_key를 cross-DB로 보거나(ATTACH), 또는 2.0 자체 캐시만 사용 — 둘 다 가능, 8b에서 결정
- cutover 시점에 viewer 기본 진입점을 2.0으로 전환, 1.x는 `/v1/` 경로로 유지

### 비용 (실측 기반)
- corpus: 7 docs / 1,946 pages / 49,850 blocks → chunk는 더 거칠어 추정 **~12-18K chunks**
- **추출** (CPU, born-digital): §28.4 3p ≈ 40s (모델 로드 후). born-digital PDF는 OCR 스킵 가능 → 페이지당 수 초. 1,946p ≈ **수 시간, 1회성 배치**. (스캔 PDF면 OCR 필요 → 느림, 현 corpus는 born-digital 추정)
- **번역**: chunk ~15K, concurrency 7 = 1.x 블록 번역과 동급 throughput (5.66x). 1.x가 44,607 translations 처리했으니 chunk는 그보다 적음 → **수 시간**
- **임베딩**: bge-m3, chunk ~15K → auto-embed chain (7a-3) 재사용, **수십 분**

---

## 4. GPU 노선 (결정 C) — 대부분 D로 해소

검증: GB10 Blackwell + CUDA 13에서
- ✅ sglang qwen3.6-27b (텍스트 번역) — **작동** (현 번역 서버)
- ✅ ollama/llama.cpp — 작동 (CPU)
- ❌ PyTorch/Paddle GPU vision (MinerU pipeline PaddleOCR, vLLM, Qwen2.5-VL) — `cublasLtGetVersion` abort

**사용자가 pre-computed vision을 뺐으므로 (결정 D) vision GPU 숙제 없음.** 남는 GPU 질문은 MinerU 추출뿐:
- **권장 (a) 하이브리드**: MinerU 추출 CPU (1회성 배치), 번역 sglang (작동), vision 없음.
- born-digital PDF는 OCR/layout GPU 의존 낮음 → CPU 충분.
- Blackwell sm_120 빌드(paddle/vLLM)는 *선택적 후속 최적화* — 재추출 빈도 낮으므로 우선순위 낮음.

---

## 5. 이미지 처리 (결정 D) — 사용자 확정

사용자 결정: **이미지 = 이미지 파일 + caption 번역만**. AI 설명 pre-compute 안 함. 클릭 → 채팅 on-demand.

채팅 시 figure 설명 방식 (sub-결정, 권장 명시):
- **(i) 텍스트 기반 [권장]**: caption + 주변 chunk 텍스트 → qwen (text-only). vision GPU 불필요, 오늘 작동, 가벼움.
- (ii) 이미지 → VLM: vision GPU 필요 (미해결 Blackwell 숙제 + 비용). 사용자 의도와 어긋남.

**(i) 권장.** (ii)는 Blackwell vision 빌드를 하게 되면 같은 트랙에서 후속으로.

---

## 6. Viewer 재작성 (결정 E)

### 폐기 (overlay/bbox 결합 — 1.x)
`viewer.js`, `stage_container.js`, `pane.js`, `page_view.js`, `block.js`, `viewport.js`, `font_fit.js` — reflow는 스크롤 article이라 zoom/stage/IO 머신 불필요.

### 재사용 (chunk 재anchor)
`message.js`(Phase 5+6i KaTeX), `chat_panel.js`, `message_input.js`, `thread_list.js`, `render_markdown.js`(applyMath/placeholder), `search_modal.js`, `sidebar.js`, `summary_banner.js` — anchor만 block_id→chunk_id, overlay-click→chunk-click.

### 신규
- reflow reading view (`result_v2.html` 프로토타입이 seed): header/문단/KaTeX/figure inline/caption
- 좌우 비교: chunk가 page_idx+bbox 보유 → 좌측 원본 PDF page render(`pages.bg_image_path` 재사용) + 우측 reflow. **유지 권장** (bbox로 chunk↔원문 하이라이트 sync 가능).

---

## 7. 자산 매핑 (1.x → 2.0)

| 1.x 모듈 | LOC | 2.0 운명 | 작업량 |
| --- | --- | --- | --- |
| `extract/` (PyMuPDF) | 755 | **폐기**, MinerU 추출 신규 (`extract_mineru/`) | 신규 中 |
| `translate/pipeline.py` | 680 | **재사용** + Block→Chunk 일반화 + placeholder 수식 보호 | 小 (검증됨) |
| `embedding/` (block_id-keyed) | 605 | **재사용** + block_id→chunk_id 기계적 rename. in-memory cosine matrix 그대로 (chunk ↓ block) | 小 |
| `api/routers/` | 2,549 | blocks/pages/threads/messages → chunk API **재작성**. uploads/jobs/search 재사용 | 中 |
| `api/chat_context.py` | — | **재사용** + ±radius를 chunk seq 기준 + figure caption context | 小 |
| frontend overlay (7 files) | ~2,000 | **폐기** | — |
| frontend chat/md/search (8 files) | ~1,800 | **재사용** + chunk 재anchor | 中 |
| KaTeX vendor (6i) | — | **재사용 그대로** | 0 |
| v2_ko prompt | — | **재사용** + placeholder 확장 (검증됨) | 0 |
| `jobs/`, `summarize/`, `llm/`, `db/session` | — | **재사용** (chunk 모델 추가만) | 小 |

---

## 8. Sub-phase 분해 (결정 F)

```
8a ─► 8b ─┬─► 8c ─┐
          └─► 8d ─┴─► 8e
```

| Phase | 범위 | DoD (요지) | 의존 |
| --- | --- | --- | --- |
| **8a** | MinerU 추출 파이프라인 + chunk schema + ingest (content_list.json → chunks) + alembic + CLI `ht-lens extract-mineru` | doc 1개 (예 doc7 한 챕터) chunks 적재, type/level/bbox/img 보존, 회귀 green | — |
| **8b** | chunk 번역 (translate 재사용 + 수식 placeholder 보호) + chunk_embeddings (block→chunk rename) + auto-embed chain | chunk 번역 status=translated, leftover placeholder 0, embeddings 생성, RAG search 동작 | 8a |
| **8c** | reflow viewer (reading view, read-only): header/문단/KaTeX/figure inline/caption 번역 | doc7 챕터 단일 화면 렌더, KaTeX 에러 0, figure inline, headless 검증 | 8b |
| **8d** | chat/핀/RAG chunk 재anchor + figure on-demand 채팅(텍스트 기반) + 좌우비교 | 클릭→채팅, 핀 CRUD, cross-doc RAG, PDF\|reflow sync | 8b (8c와 병행 가능) |
| **8e** | 7 docs 마이그레이션 (재추출+재번역+재임베딩) + cutover (2.0 기본 진입, 1.x `/v1/`) | 7 docs 2.0 DB 적재, 양 viewer 공존, 롤백 경로 | 8a~8d |

각 sub-phase는 ROADMAP에 항목 추가(사용자) + 자체 워크플로 사이클.

---

## 9. 위험 + 완화

| 위험 | 영향 | 완화 |
| --- | --- | --- |
| MinerU born-digital이 아닌 스캔 PDF면 OCR 느림/GPU 필요 | 추출 시간 폭증 | 현 corpus born-digital 확인됨. 스캔 문서는 별도 트랙 |
| chunk 번역 문맥 부족 (fragment) | 번역 품질 | item-level + 이웃 chunk context 전달 (chat_context 패턴) |
| 데이터모델 전환 마이그레이션 | 복잡/리스크 | 병행 DB (1.x 무손상), clean 재추출, sub-phase 단계 |
| frontend 대규모 재작성 | 시간 | 채팅/md/검색 재사용, overlay만 폐기. reflow seed = result_v2.html |
| MinerU 수식 spacing (`p ( z )`) | 검색/embedding 토큰화 | KaTeX 렌더는 정상. embedding 전 normalize 후처리 |
| Blackwell GPU (추출/vision) | 미해결 | 추출 CPU 1회성. vision 사용자가 제외 (텍스트 기반 채팅) |

---

## 10. 사용자 결정 항목 (✅ 2026-05-30 전원 확정)

| | 질문 | worker 권장 | **확정** |
| --- | --- | --- | --- |
| **A** | chunk 입도: item-level / section-level / hybrid | item-level | ✅ **item-level** |
| **B** | 마이그레이션: 병행DB+clean / in-place / 캐시재활용 | 병행 DB + clean | ✅ **병행 DB + clean 재추출** |
| **C** | GPU: 하이브리드(추출 CPU) / Blackwell 빌드 | 하이브리드 | ✅ **하이브리드** (D로 vision 숙제 소멸) |
| **D** | figure 채팅: 텍스트 기반 / VLM | 텍스트 기반 | ✅ **텍스트 기반** (사용자 선결정) |
| **E** | 좌우 비교(PDF\|reflow) 유지? | 유지 | ✅ **유지 — 토글** |
| **F** | sub-phase 순서/묶음 | 8a→8b→(8c∥8d)→8e | ✅ **8a 착수**, 분해 채택 |

모든 권장안 채택. 이 표가 sub-phase 설계의 구속 기준.

---

## 11. 예상 일정 (plan 확정 후 구현)

| Phase | 작업 시간 (구현) | 비고 |
| --- | --- | --- |
| 8a | ~3-5일 | MinerU 통합 + schema + ingest |
| 8b | ~2-3일 | translate 재사용이라 짧음 (placeholder만 신규) |
| 8c | ~4-6일 | reflow viewer 신규 frontend |
| 8d | ~4-6일 | chat/핀/RAG 재anchor |
| 8e | ~2-3일 + 배치시간 | 7 docs 재처리 (추출 수 시간 + 번역 수 시간) |
| **합** | **~3-4주** | sub-phase 순차, 1.x 무중단 |

마일스톤: **v2.0** = 8a~8e 완료 + 7 docs cutover.

---

## 12. 다음 액션

1. ✅ 결정 A~F 확정 (2026-05-30, §10).
2. ⬜ **사용자**: ROADMAP v10에 Phase 8a~8e 항목 + 각 DoD 추가 (worker는 ROADMAP 못 건드림 — CLAUDE.md).
   - §8 표의 DoD 요지를 출발점으로 사용 가능.
3. ⬜ **worker**: 사용자가 ROADMAP 추가 + `phase_8a_prompt.md` 전달 시 → `codex --version` 확인 → `.claude/phases/phase-8a/`를 `_template/`에서 복사 → plan.md → run_debate.sh 8a → … 워크플로 사이클.

### Phase 8a 착수 게이트 (worker 자가 점검)
- [ ] ROADMAP v10에 Phase 8a DoD 존재 (사용자)
- [ ] Codex 가용 (`codex --version`)
- [ ] 이 마스터플랜 §2 schema + §8 8a 범위가 8a plan.md의 입력
