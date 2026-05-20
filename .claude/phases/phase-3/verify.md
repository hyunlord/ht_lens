# Phase 3 — Verify (self, v3 — post Planner-directed fix)

Planner-directed targeted fix 적용 후 재작성. Round 2 cross-verify 상한 도달했고 Planner가 직접 fix 1건 + 회귀 테스트 1건 지시 → cross-verify 재호출 금지. 본 verify는 `0ab906f`(test 커밋, head) 시점에 대한 self-evaluation. 작성 직전 `git status` clean 확인.

## 5-A. Automated checks (fresh 실행)

| Check    | Command (실행한 그대로) | Result |
| -------- | ----------------------- | ------ |
| Lint     | `uv run ruff check .`     | All checks passed! (0 errors) |
| Format   | `uv run ruff format --check .` | (verify 단계 별도 호출) all files already formatted |
| Type     | `uv run mypy src/`         | Success: no issues found in 49 source files |
| Test (fast) | `make test-fast` → `pytest -m "not llm and not slow"` (Makefile:17) | **197 passed, 5 deselected** in 72.51s |
| Coverage | `make check` 내장 (`pytest -m "not llm" --cov`) | TOTAL 74% (1645 stmts / 395 missed). 새 fix 영역 (`schemas.BlockType`, `test_get_page_serializes_table_block_type`) 100%. |
| Test (llm) | `pytest -m llm` | 재실행 안 함 (이번 라운드는 schema/test 변경만으로 LLM 경로 무관). 직전 라운드(67c7fbd)에서 5 passed 검증 완료. 본 fix는 LLM 호출 경로를 건드리지 않음. |
| CI (local) | `make check` (Makefile:20: `ruff format .` + `ruff check .` + `mypy strict` + `pytest -m "not llm"`) | **RC=0** |
| CI (remote) | `.github/workflows/ci.yml` push/PR trigger (sync deps + ruff + mypy + pytest) | **pending push** (Planner-directed push 미실행, CI run은 push 후 확정) |

R2 cross-verify 표현 수정:
- verify v2가 "GitHub Actions 없음"이라 적었으나 사실은 `.github/workflows/ci.yml`이 존재. v3에서는 "CI (remote)" 행을 분리하여 "pending push"로 정확히 명시 (push 전이라 remote 결과는 미확정).
- ruff 파일 카운트 차이(38 vs 89): `uv run ruff format --check .`는 디렉토리 전체(repo) 89개 파일을, `uv run ruff format --check src/`는 src 한정 38개 파일을 보고. verify v2의 38은 src 한정 측정치였음을 명시 (오해를 부른 표현 정정).

## 5-B. Functional checks

### 1) End-to-end 데이터 흐름

이전 verify v2와 같은 DB(`/tmp/ht_lens_phase3.db`) 유지. Schema fix는 응답 직렬화 경로만 영향 — DB row의 type 컬럼 자체 변경 없음. extract → ingest → translate 재실행 불필요.

### 2) verify_api.sh (직전 라운드 stale 아님)

직전 라운드(verify v2, RE-CODE 후) exit 0 + 9-step 통과. 본 라운드의 변경은:
- `BlockRead.type` Literal 확장 (4 values)
- 신규 테스트 1건 추가

verify_api.sh 자체와 실제 페이지 응답 경로는 변경 없음. 재실행은 본 fix의 변경 surface와 무관하므로 생략 가능 (Planner-directed scope 최소).

### 3) Integration test 전수 (mock LLM)

`uv run pytest -m "not llm"` → **197 passed, 5 deselected** (이전 v2: 196 → 197, +1 신규).

신규 1건:
- `tests/integration/test_api_pages.py::test_get_page_serializes_table_block_type` — DB의 `Block.type`을 `"table"`로 강제 update 후 `GET /documents/{id}/pages/{n}` 응답이 200 + `blocks[..].type == "table"`을 검증.

### 4) `ROADMAP §schema` 일치 검증

ROADMAP §schema (line 51-53):
```
blocks(id, page_id, type ∈ {text, image, header, table}, ...)
```

수정 후 `src/ht_lens/api/schemas.py:18`:
```python
BlockType = Literal["text", "image", "header", "table"]
```

→ 완전 일치. 회귀 테스트가 잠금.

## 5-C. Regression check (R1 fix + R2 fix 모두 회귀 없음)

본 라운드는 Planner-directed RE-CODE의 일종. WORKFLOW + CLAUDE 가드 적용.

### R1 fix 4건 — RE-CODE 후 v3에서도 회귀 없음

| R1 fix | 회귀 보호 테스트 (v3에서 재실행 통과) |
| ------ | ------------------------------------- |
| Whitespace-only content 거부 (`MessageCreate._non_whitespace`) | `test_messages_empty_content_returns_422`, `test_messages_whitespace_only_content_returns_422` — v3 197 통과 안에 포함 |
| `LLM_TIMEOUT` env 처리 | `tests/unit/test_llm_factory_timeout.py` 3건 — 통과 |
| Schema `BlockRead.type` / `MessageRead.role` Literal | mypy strict 0 errors (router cast 정합) — 통과 |
| `verify_api.sh` 9-step + GET /threads/{id}/messages route | `test_get_thread_messages_route_*` 2건 — 통과 |

### R2 fix 1건 (table) — 신규 추가

- 변경: `Literal["text","image","header"]` → `Literal["text","image","header","table"]` (1 file, 1 line)
- 회귀 보호: `test_get_page_serializes_table_block_type` (table 타입 block을 DB에 강제 update 후 API 응답이 pydantic validation을 통과하는지 검증)
- 사이드 이펙트 분석:
  - `src/ht_lens/api/routers/pages.py:60` `cast(BlockType, b.type)` — 4 values 받음, 정상.
  - `src/ht_lens/api/routers/threads.py:32` `cast(BlockType, block.type)` — 4 values 받음, 정상.
  - mypy strict pass.
  - Phase 1 `extract/blocks.py:12`의 `GroupedType = Literal["text", "image", "header"]`는 그대로 유지 (Phase 1은 아직 table 미생성, 의도된 격리). API 응답 schema만 superset으로 확장.

### 새 코드 경로의 단위 테스트 존재 여부

- `BlockType` 확장된 Literal: `test_get_page_serializes_table_block_type`이 잠금. 또한 기존 모든 페이지 응답 테스트가 text/header/image 케이스를 잠그고 있음.
- 새 테스트는 `update(Block)` 직접 SQL을 사용하여 Phase 1 path를 우회한 시드 → API serializer 만 격리 검증.

### 기존 contract 무회귀

- ruff 0 errors. mypy strict 0 errors.
- Phase 1/2 테스트 (147건) 전수 통과.
- Phase 3 신규 49건 (R0 43 + RE-CODE 6) + R2 fix 1건 = 50건, 모두 통과.
- 총합 197 fast tests pass.

### Deviations from plan (Planner-directed, summary v2에서도 반영)

- `BlockType` Literal에 `table` 추가 — plan에는 3 values였음. Planner-directed scope.
- 그 외 변경 없음. CLI/lifespan/router 동작 모두 동일.

## 5-D. Scoring (100, self-assessment, v3 재산정)

| Item       | Score / Max | Evidence |
| ---------- | ----------- | -------- |
| 독창성     | 14 / 15     | (v2와 동일) `system=` 활용 + LLM-first transaction + Literal typing + traversal 가드. |
| 완결성     | 33 / 35     | (v2와 동일) DoD 9건 + GET /threads/{id}/messages + 9-step verify_api.sh. |
| 안정성     | **30 / 30** | v2의 29 → 30 (+1). `table` block runtime validation 실패 risk 제거. 회귀 테스트 잠금. R1 fix 4건 + R2 fix 1건 모두 회귀 없음. |
| 확장성     | **20 / 20** | v2의 19 → 20 (+1). API 응답 schema가 ROADMAP §schema와 완전 일치 → Phase 6 table ingest 도입 시 API 무수정. |
| **Total**  | **97 / 100** | (v2의 95 → v3 97) |

## 5-E. Self verdict

- [x] PASS_CANDIDATE (≥95)
- [ ] FAIL → RE-CODE
- [ ] FAIL → RE-PLAN

근거:
- Planner-directed scope 1건 fix 적용 (`BlockType` 확장) + 회귀 테스트 1건 + 모든 자동 검사 통과
- R1 cross-verify의 4 substantive issue + R2 cross-verify의 substantive issue 1건 모두 해소
- 197 fast tests + 5 LLM tests(직전 라운드 검증) + verify_api.sh 9-step exit 0
- R2의 cosmetic 5건은 summary v2에서 "Phase 4 entry condition"로 흡수 (Planner 지시)
- **cross-verify 재호출 금지** (WORKFLOW Round 2 상한 + Planner 명시 지시)
- **push 금지** (Planner-directed fix 정책: Planner가 직접 push)
