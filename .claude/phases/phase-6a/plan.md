# Phase 6a — Plan

## Goal

Phase 5 viewer 위에 사용자 체감 큰 UX 3종을 더한다: Cmd+K 전체 검색, 질문 markdown export, block 단위 재번역. v0.4 마일스톤.

## Scope

**In**
- Backend (Phase 3 router 확장):
  - `GET /search?q&doc_id&limit` — SQLite LIKE 기반 cross-doc 검색
  - `GET /documents/{doc_id}/export.md` — 질문 모음 markdown 다운로드
  - `POST /blocks/{block_id}/retranslate` — 단일 block 재번역 (upsert)
- `api/export_markdown.py` — 서버 측 markdown 빌더
- `api/schemas.py`: SearchHit 모델 추가
- Frontend:
  - `js/components/search_modal.js` — Cmd/Ctrl+K modal + 결과 list + ↑↓ Enter Esc
  - `js/components/block.js` — 우클릭 → 재번역 confirm
  - `js/components/sidebar.js` — 질문 탭 상단 export 버튼
  - `js/components/chat_panel.js` — (선택) 패널 내 재번역 버튼
  - `js/utils/keyboard.js` — Cmd+K hook
  - `js/api.js` — search/export/retranslate 메서드
  - `js/state.js` — searchOpen/searchQuery/searchResults
  - `js/viewer.js` — 모달 통합 + 검색 결과 클릭 시 navigate
- `css/search_modal.css`
- Integration tests: 신규 endpoint 3종 + static 자산 + 회귀 가드
- 7 screenshots (search modal / results / jump / export 버튼 / exported md / retranslate confirm / result)

**Out**
- FTS5 migration (필요 시 Phase 6b)
- Phase 6b 영역 (header heuristic, 멀티컬럼, samples.md determinism, 회전 페이지)
- Phase 6c 영역 (백그라운드 작업 패널, 모델 토글, streaming, Playwright suite, LLM-driven title)
- 새 Python/JS dep
- block.type=image 재번역 (의미 없음)
- localStorage migration (Phase 5에서 처리)

## Approach

### 1. Search endpoint

```python
# src/ht_lens/api/routers/search.py
@router.get("/search", response_model=list[SearchHit])
async def search(
    q: Annotated[str, Query(min_length=2, max_length=200)],
    doc_id: Annotated[int | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[SearchHit]:
    ...
```

SQL (parameterised LIKE):
```sql
SELECT b.id, b.block_local_id, b.type, b.original_text,
       p.page_num, d.id AS doc_id, d.filename,
       t.translated_text
FROM blocks b
JOIN pages p ON p.id = b.page_id
JOIN documents d ON d.id = p.doc_id
LEFT JOIN translations t ON t.block_id = b.id
WHERE LOWER(b.original_text) LIKE :pat
   OR LOWER(t.translated_text) LIKE :pat
ORDER BY (CASE WHEN d.id = :doc_id THEN 0 ELSE 1 END),
         d.id, p.page_num, b.order_idx
LIMIT :limit
```

Pattern: `%{lowered q}%`. doc_id 우선 정렬은 SELECT-side에서 처리.

SearchHit:
```python
class SearchHit(BaseModel):
    doc_id: int
    doc_filename: str
    page_num: int
    block_id: int
    block_local_id: str
    type: str
    matched_field: Literal["original", "translated"]
    preview: str
    match_start: int
    match_end: int
```

Preview builder: matched offset ±60 chars + 양끝 ellipsis. 한국어 surrogate 문제 없도록 string slice. `matched_field` 결정 우선순위: original이 우선 매치하면 original, 아니면 translated.

성능: 10K block 환경에서 < 200ms 목표. 실측에서 미달 시 Phase 6b FTS5로 미룸 (debate에서 확인).

### 2. Export endpoint

`GET /documents/{doc_id}/export.md`:

```python
@router.get("/documents/{doc_id}/export.md")
async def export_markdown(doc_id: int, session: ...) -> Response:
    md = await build_questions_markdown(session, doc_id)
    if md is None:
        raise HTTPException(404, "document not found")
    filename = f"ht_lens-{doc_id}-questions.md"
    return Response(
        content=md,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
```

`api/export_markdown.py`:
- 문서 + 모든 thread + 모든 message fetch (JOIN)
- thread는 page_num → block.order_idx → thread.created_at 순 정렬
- 빈 thread (메시지 0) 제외
- markdown format:
  ```
  # {filename} — 질문 모음

  - 문서: {filename}
  - 페이지 수: {num_pages}
  - 질문 수: {N threads}
  - 생성: {now ISO}

  ---

  ## p.{page_num} — {block_local_id}

  > 원문: {original_text[:300]}
  > 번역: {translated_text[:300]}

  ### {thread.title}

  **나** ({message.created_at}):
  {content}

  **AI** ({message.model}):
  {content}

  ---
  ```

`>` blockquote는 markdown 표준. 긴 텍스트는 300자 truncate + `…`. content는 그대로 보존 (escape 안 함; 사용자 자신의 데이터).

### 3. Retranslate endpoint

`POST /blocks/{block_id}/retranslate`:

```python
@router.post("/blocks/{block_id}/retranslate", status_code=202)
async def retranslate_block(
    block_id: int,
    session: ...,
    llm: ...,
    sem: Annotated[asyncio.Semaphore, Depends(get_chat_semaphore)],
) -> RetranslateResponse:
    block = await session.get(Block, block_id, options=[selectinload(Block.page)])
    if block is None:
        raise HTTPException(404, "block not found")
    if block.type not in ("text", "header"):
        raise HTTPException(400, f"block type {block.type!r} cannot be retranslated")
    doc = await session.get(Document, block.page.doc_id)
    async with sem:
        new_text = await llm.translate(
            block.original_text, doc.src_lang, doc.tgt_lang,
        )
    model = getattr(llm, "model_name", "unknown")
    ck = make_cache_key(block.original_text, doc.src_lang, doc.tgt_lang, model)
    now = datetime.now(UTC)
    existing = await session.get(Translation, block_id)
    if existing is None:
        existing = Translation(block_id=block_id, translated_text=new_text,
                               model=model, cache_key=ck, status="translated",
                               updated_at=now)
        session.add(existing)
    else:
        existing.translated_text = new_text
        existing.model = model
        existing.cache_key = ck
        existing.status = "translated"
        existing.updated_at = now
    await session.commit()
    return RetranslateResponse(block_id=block_id, translation=...)
```

**캐시 정책**: 기존 row update (debate 결정사항 4). row supersede 패턴 (`model="superseded-{ts}"`)은 cache lookup이 복잡해지므로 reject. 단순 upsert.

`block.type == "header"`도 재번역 허용 (debate 결정사항 9).

### 4. Search Modal (Frontend)

```html
<div class="search-modal" hidden>
  <div class="search-modal-backdrop"></div>
  <div class="search-modal-content">
    <input type="text" class="search-input" placeholder="원문/번역 검색..." />
    <div class="search-results" role="listbox"></div>
    <div class="search-empty" hidden>결과 없음</div>
  </div>
</div>
```

- Cmd/Ctrl+K → 모달 열기 + input focus
- Esc → 닫기
- 입력 debounce 200ms → `apiGet("/search?q=...&doc_id=N&limit=50")`
- 결과 항목: `<button role="option">` 안에 doc filename, page, preview (matched 부분 `<mark>`)
- ↑↓로 선택 이동, Enter로 점프
- 결과 클릭/선택 시 viewer.html?doc=X&page=Y로 navigate + block 활성화 (URL 파라미터)

debounce 결정: 200ms. (debate §8 확정)

### 5. Export 버튼 (Frontend)

좌측 사이드바 ❓ 질문 탭 상단:

```html
<div class="sidebar-actions">
  <button class="export-btn">📥 마크다운으로 내보내기</button>
</div>
```

click → `apiGet`이 아니라 brower download trigger:
```js
async function exportQuestions(docId) {
  const url = `/documents/${docId}/export.md`;
  // 단순 a[download] 트릭
  const a = document.createElement("a");
  a.href = url;
  a.download = "";  // server Content-Disposition 우선
  document.body.appendChild(a);
  a.click();
  a.remove();
}
```

### 6. Retranslate 트리거 (Frontend)

**우클릭 (contextmenu) + 확인 modal**:

block 컴포넌트에 `contextmenu` 이벤트:
- `e.preventDefault()`
- `block.type in {text, header}` 만
- confirmation modal:
  ```html
  <div class="confirm-modal">
    <p>이 단락을 재번역하시겠습니까?</p>
    <small>{original_text 미리보기}</small>
    <button class="cancel">취소</button>
    <button class="confirm">재번역</button>
  </div>
  ```
- 확인 시:
  - panelToken bump
  - spinner overlay
  - `apiPost(/blocks/{id}/retranslate)`
  - 응답 받으면:
    - `state.threadDetailById[...]?.block` 갱신 (있으면)
    - `currentPage.blocks[idx].translated_text = response.translation.translated_text`
    - `repaintPage()` 호출
    - toast "재번역 완료"

`block.js`에 contextmenu 핸들러 + ConfirmModal helper. 우클릭 mobile/터치는 long-press로 후속 phase에서 처리.

### 7. State 확장

```js
export const state = {
  ...,
  // Phase 6a additions
  searchOpen: false,
  searchQuery: "",
  searchResults: [],         // [SearchHit]
  searchSelected: 0,         // ↑↓로 이동
  retranslateInProgress: null, // block id | null
};

export function openSearch() { ... }
export function closeSearch() { ... }
```

검색 상태는 **persist 안 함** (휘발성 UI).

### 8. URL 라우팅 (block 활성화)

검색 결과 jump:
- `viewer.html?doc=N&page=M&block=B`
- viewer.js가 `block` 파라미터 받으면 `state.activeBlockId = block`로 자동 설정 + scrollIntoView

기존 viewer/index 라우팅은 호환.

### 9. Keyboard 확장

`utils/keyboard.js`:
- Cmd/Ctrl+K → `onOpenSearch`
- Esc → 이미 panel close에 쓰임. search modal이 열려있으면 search close 우선 → panel close.

### 10. Error handling

- 검색 실패: modal 내 "검색 오류: ..." banner
- 재번역 실패: toast 빨강 + "다시 시도" 버튼 (block 우클릭 한 번 더)
- export 실패: toast

### 11. 검색 매처 정합성

- Case-insensitive: `LOWER()` SQL + lowercased pattern
- 멀티바이트 (한국어): SQLite LIKE는 byte-level이라 한글에는 동작. UTF-8 환경에서 충돌 없음.
- 공백 normalize: 클라이언트에서 `query.trim().replace(/\s+/g, " ")`
- 빈 결과 시 200 응답 + 빈 리스트

### 12. 성능 측정 + fallback

verify.md 5-B에서 측정:
- 실제 데이터 (sample_mixed.pdf = 102 blocks)
- 100 block × N doc 시뮬레이션 (sqlite INSERT) — Phase 6a scope 외; 단순 실측 + 추정

목표 200ms 미달 시 Phase 6b로 FTS5 도입 미룸 (debate에서 결정 확인).

### 13. CSS

`search_modal.css`:
- modal: fixed center, 600×~600px max, z-index: 100
- backdrop: rgba(0,0,0,0.5) + backdrop-filter blur(4px)
- input: large, system font
- 결과 항목: padding, hover background, selected highlight
- `<mark>` 매칭 강조: yellow background

### 14. Phase 5 호환성

- viewer.js: 기존 동작 유지, 검색 통합은 새 모듈 + listener
- closePanel/discardPanel/togglePanel/openSearch/closeSearch 함수 분리 유지 (Phase 5 패턴 일관)
- block.js: 기존 click handler 그대로, contextmenu만 신규 추가

### 15. RE-CODE 대비 (워크플로우 보강 0-3-A)

신규 함수/state 식별자:
- `openSearch`, `closeSearch`, `setSearchResults`
- `state.searchOpen`, `state.searchQuery`, `state.searchResults`, `state.searchSelected`
- `apiGet("/search?...")` wrapper `searchAll(q, docId)`
- `exportQuestions(docId)` wrapper
- `retranslateBlock(blockId)` wrapper
- `renderSearchModal(container, ctx, callbacks)`
- `renderConfirmModal(container, msg, onConfirm, onCancel)`

각각 grep test로 잠금 + tests/integration/test_static_serving.py 확장.

## File-level changes

| Path | Action | Note |
| ---- | ------ | ---- |
| `src/ht_lens/api/routers/search.py` | NEW | GET /search |
| `src/ht_lens/api/routers/blocks.py` | NEW | POST /blocks/{id}/retranslate |
| `src/ht_lens/api/routers/documents.py` | MODIFY | GET /documents/{id}/export.md |
| `src/ht_lens/api/schemas.py` | MODIFY | SearchHit + RetranslateResponse |
| `src/ht_lens/api/export_markdown.py` | NEW | markdown 빌더 |
| `src/ht_lens/api/app.py` | MODIFY | search + blocks 라우터 등록 |
| `src/ht_lens/api/static/js/components/search_modal.js` | NEW | modal |
| `src/ht_lens/api/static/js/components/confirm_modal.js` | NEW | helper |
| `src/ht_lens/api/static/js/components/block.js` | MODIFY | contextmenu |
| `src/ht_lens/api/static/js/components/sidebar.js` | MODIFY | export 버튼 |
| `src/ht_lens/api/static/js/components/chat_panel.js` | MODIFY (선택) | 재번역 버튼 |
| `src/ht_lens/api/static/js/utils/keyboard.js` | MODIFY | Cmd+K hook |
| `src/ht_lens/api/static/js/api.js` | MODIFY | searchAll/exportQuestions/retranslateBlock |
| `src/ht_lens/api/static/js/state.js` | MODIFY | search state + openSearch/closeSearch |
| `src/ht_lens/api/static/js/viewer.js` | MODIFY | 검색/재번역 통합 + ?block 파라미터 |
| `src/ht_lens/api/static/css/search_modal.css` | NEW | modal 스타일 |
| `src/ht_lens/api/static/viewer.html` | MODIFY | search_modal.css link + key hint |
| `tests/integration/test_api_search.py` | NEW | search endpoint |
| `tests/integration/test_api_export.py` | NEW | export endpoint |
| `tests/integration/test_api_retranslate.py` | NEW | retranslate + @pytest.mark.llm 일부 |
| `tests/integration/test_static_serving.py` | MODIFY | new assets + grep markers |
| `docs/phases/phase-6a/README.md` | NEW | 7 시나리오 + screenshots |
| `docs/phases/phase-6a/screenshots/*.png` | NEW (7) | manual + Playwright |

## Dependencies (new)

| Package | Why |
| ------- | --- |
| (none) | Phase 3 endpoint 확장 + Phase 5 vendor 그대로. |

## Test strategy

### Integration (TestClient + mock LLM)
- `test_api_search.py`:
  - 빈 query: 422 (min_length=2)
  - 정상 query → SearchHit 리스트 + matched_field/preview 검증
  - doc_id 필터 (해당 doc 우선 정렬)
  - limit clamp
  - 0 결과 → 200 + 빈 리스트
- `test_api_export.py`:
  - 0 thread 문서 → 200 + 헤더만
  - 10 thread 문서 → 모든 thread 포함, page_num 순 정렬, 빈 thread 제외
  - 잘못된 doc_id → 404
  - Content-Type + Content-Disposition 검증
- `test_api_retranslate.py`:
  - mock LLM 정상 → 202 + 새 translated_text
  - image block → 400
  - 잘못된 block_id → 404
  - 기존 translation 있을 때 upsert (model + cache_key + updated_at 갱신)
  - 기존 translation 없을 때 insert
- `test_static_serving.py` 확장:
  - search_modal.{js,css} 200
  - confirm_modal.js 200
  - block.js contextmenu 마커
  - keyboard.js Cmd+K 마커
  - state.js search 마커
  - viewer.js openSearch 마커
  - export 버튼 sidebar.js 마커

### Live LLM (`@pytest.mark.llm`)
- `test_api_retranslate.py::test_retranslate_live_replaces_translation`: 1 block 재번역 (cost 5초)

### Manual (verify 5-B)
- Cmd+K → 검색 → 결과 점프 (3 시나리오)
- 사이드바 export 버튼 → 다운로드 → 파일 열기
- block 우클릭 → 재번역 → 갱신 확인

### Latency benchmark
- 현재 102 blocks 환경에서 latency 측정
- 시뮬레이션 1000+ blocks도 가능하면 추가 (단순 INSERT) — 추정만

## DoD mapping

| DoD item | How to satisfy | Evidence plan |
| -------- | -------------- | ------------- |
| Cmd+K로 임의 문구 찾고 점프 (200ms) | `GET /search` SQLite LIKE + modal | latency 측정 + 스크린샷 1-3 |
| 질문 export markdown 받기 | `GET /documents/{id}/export.md` + sidebar button | 스크린샷 4-5 + 파일 spot check |
| block 재번역 → 갱신 | `POST /blocks/{id}/retranslate` + contextmenu | 스크린샷 6-7 + integration test |

## 미결정 사항 (debate 검토 대상)

1. **검색 결과 정렬**: doc_id 우선 → page_num → order_idx. matching strength 측정 없음 (Phase 6b).
2. **Preview ±60 chars + ellipsis** — plan 채택.
3. **Export markdown 빌더 backend** — server-side (debate §3 채택). client-side는 cost 동일.
4. **재번역 캐시: row update** (debate §4 plan 결정).
5. **block 우클릭** + confirm modal — plan 채택. mobile은 Phase 6c.
6. **search modal ARIA**: role="dialog", aria-modal="true", input aria-controls 결과 list.
7. **export 파일명**: ASCII 안전 (`ht_lens-{id}-questions.md`). 한국어 filename 회피.
8. **search debounce**: 200ms.
9. **block.type=header 재번역**: 허용. text와 동일 prompt.
10. **search latency 미달 시 FTS5**: Phase 6b로 미룸. 본 phase 200ms 못 채우면 verify에서 명시.

debate에서 Codex가 위 영역의 약점 (특히 search 정렬 + preview unicode + retranslate race) 찌를 가능성.
