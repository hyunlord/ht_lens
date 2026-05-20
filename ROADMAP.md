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
        - 배경 + 오버레이             - Anthropic
        - 채팅 패널                   - OpenAI
        - 핀 + 질문 리스트            - Ollama (Qwen)
```

핵심 단위는 **block**. block이 곧 번역 단위이자 클릭 단위이자 질문 단위.

---

## Tech Stack

| 영역      | 선택                                                  |
| --------- | ----------------------------------------------------- |
| Backend   | Python 3.11, FastAPI, SQLAlchemy 2.0 async, SQLite    |
| PDF       | PyMuPDF (fitz), Pillow                                |
| LLM       | 추상 `LLMClient` → Anthropic / OpenAI / Ollama swap   |
| Frontend  | vanilla HTML/JS (Phase 4~5), 향후 Electron 옵션       |
| Dev tools | uv, ruff, mypy strict, pytest, GitHub Actions         |

---

## Data Model (Phase 2 확정 예정)

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

### Phase 0 — Skeleton & Harness ⬜
**Deliverable**: 빈 골격 + CI green.
- 디렉토리, pyproject(uv), ruff, mypy strict, pytest markers(`llm`, `slow`)
- GitHub Actions, pre-commit, Makefile
- conftest fixture placeholder (sample_*_pdf, llm_mock)

**DoD**
- `make check` 로컬 green
- push 후 GitHub Actions green
- `src/ht_lens/` 하위에 도메인 코드 없음

---

### Phase 1 — PDF Extractor ⬜
**Deliverable**: `python -m ht_lens.extract <pdf> -o <out>` CLI.
- 페이지별 PNG (200dpi)
- block JSON: `{id, type, bbox, order, text}`
- 한/영/혼재 fixture로 회귀 테스트

**DoD**
- 3종 sample PDF 모두 block JSON이 사람이 봐도 합리적
- snapshot test 통과
- `extract` 의존성은 `pymupdf`, `pillow`, `langdetect` 정도로 제한

**위험**
- 멀티컬럼 reading order
- 캡션/각주 분리
- 한글 폰트 인식

---

### Phase 2 — DB + LLMClient + Translation ⬜
**Deliverable**
- `python -m ht_lens.ingest <extract_dir>` → SQLite 적재
- `python -m ht_lens.translate --doc-id <id>` → 번역 채움
- `LLMClient` 추상화 + `AnthropicClient` / `OllamaClient` 구현

**DoD**
- end-to-end 한 권 번역 가능 (수백 페이지 OK)
- 캐시 동작 (재실행 시 비용 0)
- 실패 block `--retry-failed`로 복구
- mypy strict 유지

**위험**
- 번역 비용 (캐시 키 설계 필수)
- rate limit / 동시성
- block 경계를 넘는 문장 처리

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
- 모델 빠른 토글 (Claude ↔ Qwen)
- block 단위 재번역

**DoD**
- 실사용 일주일 사이클에서 막히는 지점 없음
- README에 사용 예시 캡처 추가

---

## Versioning

| 버전 | 시점               | 의미                              |
| ---- | ------------------ | --------------------------------- |
| v0.1 | Phase 1~2 완료     | CLI로 번역 가능                   |
| v0.2 | Phase 3~4 완료     | 브라우저에서 읽기 가능            |
| v0.3 | Phase 5 완료       | Q&A 동작, 핀                      |
| v1.0 | Phase 6 완료       | 일상 도구로 사용 가능             |

---

## Risks & Open Questions

- **Block grouping 정확도**: 멀티컬럼/표/캡션에서 휴리스틱이 자주 깨진다.
  Phase 1에서 80% 잡고 진행, Phase 6에서 보강.
- **번역 비용**: 수백 페이지 × Claude API면 한 권에 수만 원. 캐시 키
  `hash(text + src + tgt + model)` 필수.
- **폰트 fitting**: bbox에 텍스트 욱여넣기. 한글은 영문 대비 폭/높이가
  다르다. `fitty` 류 또는 CSS `clamp()` 검토.
- **Reading order**: 채팅 맥락 품질에 직결. 컬럼 인식 실패 시 엉뚱한
  context가 들어간다.
- **이미지 위 텍스트**: 다이어그램 라벨이 텍스트로 잡힐 때 오버레이가
  깨진다. z-index/투명도 별도 처리.
- **로컬 모델 품질**: Qwen 등은 도메인에 따라 번역 품질이 들쭉날쭉.
  fallback 정책 (실패 시 Claude로 재시도) 필요.

---

## Workflow Conventions

- 각 Phase는 별도 브랜치(`phase-N-<short-name>`)에서 작업, PR로 머지
- 커밋: Conventional Commits (`feat:`, `fix:`, `chore:`, `refactor:`)
- Phase 종료 시: ROADMAP의 해당 Phase ⬜ → ✅ 갱신, README 상태 갱신
- 위에 명시되지 않은 dependency 추가 시 ROADMAP에 근거 기록
