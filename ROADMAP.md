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

### Phase 5 — Chat Panel + Pins + Question List ✅
**Deliverable**
- block 클릭 → 우측 채팅 패널 (AI 설명 / 직접 질문 / 꼬리질문)
- 핀 표시 (thread 있는 block 우상단)
- 좌측 사이드바 "질문" 탭 (전체 thread 목록, 페이지 점프)

**DoD**
- 문서 한 권 읽으며 10개 이상 질문 자연스럽게 누적
- 닫았다 다시 열어도 핀/스레드 그대로
- 마크다운/코드블럭 렌더링

**완료 노트**
- 97/100 self-score, Round 2 REJECT → Planner-directed targeted fix (3건) → PASS
- 268 fast tests + 8 vendor/XSS node tests, mypy strict 0 위반
- 35 신규 회귀 테스트 (vendor + chat + state transitions + migration guard)
- vendor pattern: marked@11 ESM + DOMPurify@3 ESM (~166KB committed)
- 함수 분리 패턴 정립: closePanel / discardPanel / togglePanel + readPanelSnapshot()
- v0.3 마일스톤 달성 (Phase 0~5 완료, 일상 도구로 사용 가능)
- 잔여 debt (Phase 6 흡수):
  - Playwright 자동 시나리오 (현재 수동)
  - CI jsdom 미설치 (일부 노드 테스트 silent skip 가능성)
  - Streaming response (SSE)
  - LLM-driven thread title (현재 first user message 첫 30자)

---

### Phase 6a — Critical UX gaps ✅
**Deliverable**
- Cmd+K 전체 검색 (원문+번역 동시)
- 질문 → markdown export
- block 단위 재번역

**DoD**
- Cmd+K로 임의 문구 찾고 점프 가능 (latency < 200ms for 10K blocks)
- 질문 export markdown 한 파일로 받기 가능 + 사람이 읽기 좋음
- block 우클릭 → 재번역 → 캐시 무효화 + 새 번역 표시

**완료 노트**
- 96/100 Planner-adjusted (Worker 98 vs Codex R2 95 절충)
- 305 fast tests + 6 LLM tests + 7 screenshots + tracked scenario
- R1 4 substantive 결함 모두 fix (cache pollution / multiline export / whitespace search / confirm modal behavioural)
- R2 verify-scope critique 4건은 Phase 6d 위임
- v0.4 마일스톤 달성

---

### Phase 6b — Viewer Rework ⬜
**Deliverable**
- 좌우 분할 비교 뷰 (원문 | 번역 동시 표시)
- 자연 스크롤 페이지 네비 (PDF처럼 연속 스크롤)
- View mode 토글: `translation` / `original` / `both`
- 채팅 패널 + 좌우 비교 충돌 회피 (자동 single-pane)

**DoD**
- 200 페이지 PDF에서 스크롤 부드러움 (메모리 < 500MB)
- 좌우 비교에서 페이지/zoom/scroll 정확히 동기화
- block hover/click이 양쪽 pane에 동기 반영
- 검색/사이드바 점프가 자연 스크롤 위치로 정확히

**위험**
- intersection observer + lazy ±1 페이지 마운트 정확도
- side-by-side scroll 동기화
- 메모리 누수 (스크롤 멀어진 페이지의 DOM unmount)
- 검색/사이드바 점프 시 lazy mount 대기 race

**Versioning**: v0.5

---

### Phase 6c — Viewer Polish ⬜
**Deliverable**
- LLM env 로드 fix (`.env`가 `ht-lens serve` 진입 시 자동 반영)
- 페이지 진입 시 fit-to-width 자동 zoom
- 좌측 사이드바 토글 (열기/닫기 버튼)
- 자연 스크롤 버그 fix (스크롤 다운 시 다음 페이지 정확히 마운트)
- 메인 메뉴 / 문서 리스트 돌아가기 네비

**DoD**
- viewer에서 받은 AI 응답이 진짜 sglang 호출 (mock 아님)
- 새 페이지 진입 시 자동으로 viewport 폭 fit
- 사이드바 토글 동작 (좌측 200px → 0px → 200px)
- 자연 스크롤로 6 페이지 sample_mixed.pdf 끝까지 이동 가능
- viewer 좌상단 ht_lens 로고 클릭 → index.html 복귀
- localStorage에 사이드바 열림/닫힘 상태 저장

**위험**
- Phase 6b의 자연 스크롤 일부만 동작 (실 측정 후 확인)
- fit-to-width 시 zoom state localStorage 충돌
- 사이드바 토글 시 stage container width 재계산 비용

**Versioning**: v0.6

---

### Phase 6d — File Management + Summary ⬜
**Deliverable**
- 파일 업로드 UI (드래그 앤 드롭 + 파일 선택 버튼)
- 백엔드 PDF upload → extract → ingest → translate 자동 체인
- 백그라운드 작업 상태 추적 (jobs 테이블 + 진행 polling)
- 업로드된 문서의 자동 요약 생성 (LLM)
- 업로드된 PDF는 `data/uploads/` 보관 + sha256 dedup
- index.html에 작업 진행 현황 (active jobs)

**DoD**
- 사용자가 브라우저에서 PDF 드롭 → 자동 처리 → viewer 진입까지 한 흐름
- 200 페이지 PDF 처리 1~2시간 안에 완료 + 진행 표시
- 자동 요약은 적절한 길이 (300~500 단어), 한국어 자연스러움, 문서 첫 페이지에 thread로 자동 attach (또는 별도 영역)
- 같은 sha256 PDF 재업로드 시 dedup (기존 doc_id 반환)
- 작업 실패 시 명확한 에러 표시

**위험**
- 동시 업로드 시 race condition
- 큰 PDF (>100MB) 업로드 시 메모리/HTTP timeout
- 진행 polling vs SSE 선택
- 요약 LLM prompt 설계
- 업로드된 PDF의 file system 보안 (path traversal)

**Versioning**: v0.7

---

### Phase 6e — Polish Pack ⬜
**Deliverable**
- 핀 표시 더 직관적 (색깔/크기/위치 개선, 멀티 thread 표시)
- 사이드바 리사이즈 (좌우 드래그)
- 작은 이미지/도표 클릭 시 확대 모달
- streaming 응답 (SSE)
- 모델 빠른 토글 (Qwen ↔ Gemma ↔ OpenRouter)
- 백그라운드 작업 패널 (Phase 6d 기반 확장)
- Playwright 자동 시나리오 (Phase 5 debt)
- CI jsdom 설치 (Phase 5/6b debt)
- LLM-driven thread title (Phase 5 debt)
- + Phase 6a R2 위임 (multiline translated test, search 200ms 엄격 단언, LLM live re-run after RE-CODE)

**DoD**
- 핀 시각 만족도 (사용자 spot check)
- 사이드바 리사이즈 부드러움 (200px ~ 500px)
- 이미지 확대 단축키 + 클릭
- streaming 1자씩 표시 (체감 latency 절반 이하)
- 모델 env 1줄 변경으로 swap, viewer 재시작 불필요 정도
- README 일주일 실사용 캡처

**Versioning**: v0.8

---

### Phase 6f — Extraction Quality Debt ⬜
**Deliverable**
- header heuristic 보강 (Phase 1 known issue)
- 멀티컬럼 reading order (Phase 1 known issue)
- samples.md determinism 검증
- 회전 페이지 bbox→pixel 정밀 매핑 (Phase 4 known issue)
- + sample_ko.pdf 같은 큰 fixture (52+ 페이지) 추가 (Phase 6b R2 위임)

**DoD**
- 3 fixture에서 header 정확도 ≥ 90% (수동 spot check)
- 멀티컬럼 PDF에서 reading order 시각적 검증
- samples.md 두 번 생성 시 diff 0
- 회전 페이지 viewer에서 정확한 block 위치
- 52+ 페이지 fixture로 자연 스크롤 메모리 실측

**위험**
- Phase 1 코드 회귀
- snapshot test 다수 갱신 필요
- 시각적 검증 어려움 (자동화 부족)

**Versioning**: v1.0

---

## Versioning

| 버전 | 시점               | 의미                              |
| ---- | ------------------ | --------------------------------- |
| v0.1 ✅ | Phase 2a + 2b 완료 | CLI로 번역 가능                   |
| v0.2 ✅ | Phase 3 + 4 완료   | 브라우저에서 읽기 가능            |
| v0.3 ✅ | Phase 5 완료       | Q&A 동작, 핀                      |
| v0.4 ✅ | Phase 6a 완료      | 검색 + export + 재번역            |
| v0.5 ✅ | Phase 6b 완료      | 좌우 비교 + 자연 스크롤           |
| v0.6 ⬜ | Phase 6c 완료      | Viewer polish (env fix, 사이드바, 메인 메뉴) |
| v0.7 ⬜ | Phase 6d 완료      | 파일 업로드 + 자동 요약            |
| v0.8 ⬜ | Phase 6e 완료      | UI polish (리사이즈, 확대, streaming, 모델 토글) |
| v1.0 ⬜ | Phase 6f 완료      | 추출 품질 (일상 도구 polish 완료) |

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
