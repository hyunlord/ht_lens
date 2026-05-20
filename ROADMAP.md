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
        [Static Viewer]              [LLMClient]
        - 배경 + 오버레이             - OpenAI-compatible
        - 채팅 패널                   - sglang / Ollama / OpenRouter
        - 핀 + 질문 리스트            - Mock (test)
```

핵심 단위는 **block**. block이 곧 번역 단위이자 클릭 단위이자 질문 단위.

---

## Tech Stack

| 영역      | 선택                                                  |
| --------- | ----------------------------------------------------- |
| Backend   | Python 3.11, FastAPI, SQLAlchemy 2.0 async, SQLite    |
| PDF       | PyMuPDF (fitz), Pillow                                |
| LLM       | OpenAI-compatible 인터페이스 (sglang Qwen3.6 기본)    |
| Frontend  | vanilla HTML/JS (Phase 4~5), 향후 Electron 옵션       |
| Dev tools | uv, ruff, mypy strict, pytest, GitHub Actions         |

---

## Data Model (Phase 2a 확정 예정)

```text
documents     (id, filename, src_lang, tgt_lang, status, created_at)
pages         (id, doc_id, page_num, width, height, bg_image_path)
blocks        (id, page_id, type, bbox_json, order_idx, original_text)
                  type ∈ {text, image, header, table}
translations  (block_id PK, translated_text, model, status, updated_at)
threads       (id, block_id, title, created_at)
messages      (id, thread_id, role, content, model, created_at)
```

---

## Phases

각 Phase는 한 Claude Code/Codex 세션 단위에 맞도록 잘랐다. 다음 Phase로
넘어가기 전 반드시 DoD를 만족해야 한다.

### Phase 0 — Skeleton & Harness ✅
**Deliverable**: 빈 골격 + CI green.
- 디렉토리 구조, pyproject(uv), ruff, mypy strict, pytest markers(`llm`, `slow`)
- GitHub Actions, pre-commit, Makefile
- conftest fixture placeholder (sample_*_pdf, llm_mock)

**DoD**
- `make check` 로컬 green
- push 후 GitHub Actions green
- `src/ht_lens/` 하위에 도메인 코드 없음

---

### Phase 1 — PDF Extractor ✅
**Deliverable**: `python -m ht_lens.extract <pdf> -o <out>` CLI.
- 페이지별 PNG (200dpi)
- block JSON: `{id, type, bbox, order, text}`
- 한/영/혼재 fixture로 회귀 테스트

**DoD**
- 3종 sample PDF 모두 block JSON이 사람이 봐도 합리적
- snapshot test 통과
- `extract` 의존성은 `pymupdf`, `pillow`, `langdetect` 정도로 제한

**완료 노트**
- 88/100 self-score, cross-verify DOWNGRADE→PASS
- Known issues: 멀티컬럼 reading order, header heuristic 정확도, samples.md determinism — Phase 4/6에서 다룸
- v5 RE-CODE로 stale verify + subprocess CLI 3-fixture + plan stale 정리

---

### Phase 2a — DB + LLMClient + Ingest ✅
**Deliverable**
- SQLite + SQLAlchemy 2.0 async + Alembic migration
- `LLMClient` Protocol + `MockLLMClient` (실제 LLM 호출 0건)
- `python -m ht_lens.ingest <extract_dir>` — Phase 1 산출물을 DB로 적재
- Phase 0의 `llm_mock` placeholder를 실제 mock 구현으로 교체

**DoD**
- 3종 fixture extract 산출물을 ingest 가능, DB 행 합리적
- `LLMClient` interface 정의 + `MockLLMClient`로 unit test 통과
- mypy strict (SQLAlchemy 2.0 typed 포함), ruff clean
- end-to-end ingest 1회 동작 (CLI exit 0)
- Alembic migration 1개 생성, 적용 가능

**위험**
- SQLAlchemy 2.0 async + mypy strict 호환 (typed Mapped[...] 작성)
- Phase 1의 ExtractResult가 ingest와 정합한지
- DB schema가 Phase 2b/3 워크로드에 충분한지

**Out of scope**
- 실제 LLM 호출 (Phase 2b)
- 캐시 (Phase 2b)
- 번역 파이프라인 (Phase 2b)

**완료 노트**
- 89/100 self-score, cross-verify Round 2 DOWNGRADE → Planner PASS
- 97 tests pass (unit + integration), mypy strict 0 위반
- Known debt: `documents.src_pdf_sha256` 미저장 → Phase 2b에서 migration 0002로 추가, `translations.cache_key` 컬럼도 같이 추가
- Round 2 상한이 의도대로 작동 (Phase 1의 4라운드 → 2라운드 종결)

---

### Phase 2b — Translation Pipeline ✅
**Deliverable**
- `OpenAICompatibleClient` (sglang Qwen3.6 기본, `enable_thinking=false`)
- `python -m ht_lens.translate --doc-id <id>` — block 단위 번역 + 캐시
- 캐시 키: `hash(text + src + tgt + model)` 기반
- async + semaphore batch (concurrent N, 기본 5)
- 실패 block 재시도 (`--retry-failed`)

**DoD**
- short fixture (5~10 페이지) 실제 sglang 호출로 번역 가능
- 재실행 시 캐시 hit으로 비용 0
- 실패 block 재시도 동작
- `reasoning_tokens == 0` 회귀 체크 (chat template 변경 감지)
- `finish_reason == "length" + content == ""` 가드 (thinking 토글 깨졌을 때)

**위험**
- 공유 GPU 환경에서 sglang latency 변동
- rate limit / 동시성 (batch 부하)
- block 경계를 넘는 문장 처리
- LLM-호출 테스트가 `make test`에서 자동 skip (marker `llm`)

**Versioning**
- **v0.1 달성**: Phase 2a + 2b 완료 시점

**완료 노트**
- 88/100 self-score, Round 2 REJECT → Planner-directed targeted fix → PASS
- 147 tests pass (unit + integration), mypy strict 0 위반
- exit code 체계 정립: 0=success / 1=block failure / 2=invalid input / 3=DB error / 4=health check failed
- v0.1 마일스톤 달성 (Phase 2a + 2b 완료)
- Known debt:
  - Sequential translate loop → Phase 3에서 asyncio.gather 병렬화
  - Live sglang DoD evidence → `@pytest.mark.llm` (CI endpoint 부재로 강제 skip)

---

### Phase 3 — FastAPI Server ⬜
**Deliverable**: REST API.
- `GET /documents`, `/documents/{id}`, `/documents/{id}/pages/{n}`
- `/documents/{id}/pages/{n}/image` (PNG stream)
- `/threads`, `/threads/{id}`, `/threads/{id}/explain`, `/threads/{id}/messages`
- 채팅 컨텍스트 자동 구성 (원문 + 번역 + 주변 ±2 block)

**DoD**
- httpie/curl로 시나리오 통과: 문서 조회 → 스레드 생성 → AI 응답
- async 일관, pydantic schema 분리
- 정적 파일 마운트 (`/static`, Phase 4용)

---

### Phase 4 — Viewer Frontend ⬜
**Deliverable**: 정적 뷰어 (vanilla HTML/JS).
- 페이지 배경 PNG + block absolute 오버레이
- 키보드 네비(←→), 원본/번역 토글(T), 줌
- block hover/click (패널은 자리만)

**DoD**
- 실제 문서 한 권을 자연스럽게 읽을 수 있음
- 한/영 폰트 fitting 80% 이상 만족
- 줌·이동 부드러움

**위험**
- bbox 기반 폰트 크기 자동 조정 (특히 한글)
- 이미지 위 텍스트 z-index
- 회전 페이지 bbox-to-pixel 매핑 (Phase 1 known issue)

---

### Phase 5 — Chat Panel + Pins + Question List ⬜
**Deliverable**
- block 클릭 → 우측 채팅 패널 (AI 설명 / 직접 질문 / 꼬리질문)
- 핀 표시 (thread 있는 block 우상단)
- 좌측 사이드바 "질문" 탭 (전체 thread 목록, 페이지 점프)

**DoD**
- 문서 한 권 읽으며 10개 이상 질문 자연스럽게 누적
- 닫았다 다시 열어도 핀/스레드 그대로
- 마크다운/코드블럭 렌더링

---

### Phase 6 — Polish ⬜
**Deliverable**
- Cmd+K 전체 검색 (원문+번역 동시)
- 질문 → markdown export
- 백그라운드 작업 패널 (ingest/translate 진행 상태)
- 모델 빠른 토글 (Qwen ↔ Gemma ↔ OpenRouter ↔ 기타)
- block 단위 재번역
- header heuristic 보강 (Phase 1 known issue)
- 멀티컬럼 reading order (Phase 1 known issue)
- samples.md determinism 검증 (Phase 1 known issue)

**DoD**
- 실사용 일주일 사이클에서 막히는 지점 없음
- README에 사용 예시 캡처 추가

---

## Versioning

| 버전 | 시점               | 의미                              |
| ---- | ------------------ | --------------------------------- |
| v0.1 ✅ | Phase 2a + 2b 완료 | CLI로 번역 가능                   |
| v0.2 | Phase 3~4 완료     | 브라우저에서 읽기 가능            |
| v0.3 | Phase 5 완료       | Q&A 동작, 핀                      |
| v1.0 | Phase 6 완료       | 일상 도구로 사용 가능             |

---

## Risks & Open Questions

- **Block grouping 정확도**: 멀티컬럼/표/캡션에서 휴리스틱이 자주 깨진다.
  Phase 1에서 80% 잡고 진행, Phase 6에서 보강.
- **공유 GPU 환경**: DGX Spark의 sglang은 다른 사용자/세션과 공유. latency
  변동 가능. Phase 2b에서 부하 테스트 필요.
- **Reasoning model의 thinking 토글**: Qwen3.6은 hybrid. `enable_thinking=false`
  가 작동함을 확인 (pre-Phase-2 exploration). chat template 변경 시 회귀 체크 필수.
- **폰트 fitting**: bbox에 텍스트 욱여넣기. 한글은 영문 대비 폭/높이가
  다르다. `fitty` 류 또는 CSS `clamp()` 검토.
- **Reading order**: 채팅 맥락 품질에 직결. 컬럼 인식 실패 시 엉뚱한
  context가 들어간다.
- **이미지 위 텍스트**: 다이어그램 라벨이 텍스트로 잡힐 때 오버레이가
  깨진다. z-index/투명도 별도 처리.
- **로컬 모델 품질**: 실데이터 풀번역 후 부족하면 OpenRouter / 다른 모델
  추가. 인터페이스 swap 가능.

---

## Workflow Conventions

- 각 Phase는 별도 브랜치(`phase-N-<short-name>`)에서 작업, PR로 머지
- 커밋: Conventional Commits (`feat:`, `fix:`, `chore:`, `refactor:`)
- Phase 종료 시: ROADMAP의 해당 Phase ⬜ → ✅ 갱신, README 상태 갱신
- 위에 명시되지 않은 dependency 추가 시 ROADMAP에 근거 기록
- Cross-verify는 phase당 max 2회 (WORKFLOW.md Stage 5-B 참조)
