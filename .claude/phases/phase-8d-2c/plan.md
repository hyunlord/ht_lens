# Phase 8d-2c — Plan (neighbor 재번역 + 사이드탭 resize) — 8d 마지막

## Goal
(1) 짧은/저문맥 chunk를 이웃 context로 재번역해 'where→어디에' 류 오역 교정(수식밀집/참조번호/보일러플레이트 제외), (2) 채팅 패널 너비 drag-resize + 본문 너비 연동(sessionStorage). 8d 시리즈 마지막.

## Stage 0 실측 (threshold 결정 근거)
doc7 `<60`자 text chunk **10개 중 실 오역은 'where'→'어디에'(id 2) 1개뿐**. 나머지 9: 식번호 `(28.116)/(28.123)/(28.126)`(verbatim, 정상), 정상 단문 `model is as follows:`/`Consider a factored Bernoulli likelihood:`, 저작권 보일러플레이트 `Author: Kevin P. Murphy...`(×4). → `<60`은 9/10이 불필요/위험(정상 번역 덮어쓰기). **Planner 확정: `<25`자 + 식/참조번호(digit-dominant) 제외 + 수식밀집($) 제외 + 보일러플레이트(중복 content) 제외.** 단 short $ chunk 0개(수식밀집 6곳은 status=failed → 이미 제외). 재사용: `translate/chunk_pipeline`(translate_chunks) + `math_protect.has_math`. chat 패널=고정 drawer(8d-2a, position:fixed right).

## Scope
**In (8d-2c)**
- neighbor 재번역: `is_math_dense`(has_math 또는 $-비율), `is_reference_number`(괄호+점표기 숫자/digit-dominant), `is_repeated`(doc 내 content 중복=보일러플레이트). `select_short_retranslate(doc_id, max_chars=25)` = type=text + len<max + status=='translated' + 위 제외. 이웃(radius 1, **text 이웃만**) context로 재번역(`math_protect` 적용), 출력은 대상 chunk만 → chunk_translations 덮어쓰기. **실패 시 기존 보존**(8b no-write). CLI `translate-chunks --short-only [--max-chars 25] [--dry-run]`.
- `--dry-run`: 대상 재번역(이웃 context) → **before/after 출력, DB 미기록**.
- resize: `js/resize.js`(신규) — 채팅 drawer 좌측 `.chat-resizer` drag → `--chat-w` + `.pane--reflow` margin-right 연동, min/max clamp, **sessionStorage** 저장/복원. 채팅 toggle open/close 시 margin on/off.

**Out**
- 수식밀집 영어 fallback 6곳 재번역 = 8e(math 강건화). 볼드 = 8e. localStorage 금지. cross-doc live = 8e.

## Approach
### A. neighbor 재번역 (translate, 8b 재사용)
- `is_math_dense(text)`: `has_math(text)`(paired $) → True. (short $ 0이지만 일반성.)
- `is_reference_number(text)`: `^\s*\(?\d+(\.\d+)*\)?[.:]?\s*$` 또는 digit-비율 높음 → 식/참조번호.
- `is_repeated(content, all_contents)`: 동일 content가 doc 내 2회+ → 보일러플레이트.
- `select_short_retranslate`: text + len<25 + status=translated + not(math/ref/repeated).
- 재번역: 이웃 radius 1(text만, heading/image/equation 이웃은 라벨만 또는 skip), 프롬프트에 이웃+대상 → 번역, 대상만 추출, `math_protect` 왕복(8b), chunk_translations upsert. 실패(LLM/placeholder) → 기존 row 보존(8b 패턴).
- CLI: chunk_pipeline에 short-only 경로 또는 `retranslate_short()`; cli `--short-only/--max-chars/--dry-run`.

### B. resize (frontend, isolated)
- `resize.js`: `clampWidth(px)`(280..min(60vw)) export, `applyChatWidth(px)`(`.chat` width + `documentElement --chat-w` + `.pane--reflow` margin-right + sessionStorage) export, `initResize({contentEl})`(resizer pointer drag, restore from sessionStorage, toggle 연동). reflow.css: `.chat-resizer`(좌측 핸들), `.pane--reflow { margin-right: var(--chat-w, 0) }`(chat open 시), `.chat { width: var(--chat-w, 380px) }`. reflow.html: `.chat`에 `<div class="chat-resizer">`. chat.js toggle/reflow.js initChat이 initResize 호출 + open/close 시 margin 토글.
- KaTeX 리렌더 불요(인라인 reflow). 고정 drawer → `.layout` 그리드 불변(compare 안전).

## File-level changes
| Path | Action | Note |
| ---- | ------ | ---- |
| `src/ht_lens/translate/short_retranslate.py` | 신규 | is_math_dense/is_reference_number/is_repeated/select_short_retranslate/retranslate_short |
| `src/ht_lens/translate/cli.py` | 수정 | `--short-only/--max-chars/--dry-run` |
| `src/ht_lens/api/static/js/resize.js` | 신규 | clampWidth/applyChatWidth/initResize (sessionStorage) |
| `src/ht_lens/api/static/js/chat.js` | 수정 | initResize 호출 + toggle margin 연동 |
| `src/ht_lens/api/static/reflow.html` + `css/reflow.css` | 수정 | .chat-resizer, --chat-w/margin |
| `tests/integration/test_short_retranslate.py` 등 | 신규 | select(threshold+제외), retranslate(neighbor+fail-preserve), dry-run, resize jsdom |

## Dependencies (new)
| Package | Why |
| ------- | --- |
| (없음) | qwen/math_protect 기존. 신규 0. |

## Test strategy
- `select_short_retranslate`: 'where'(5자, alpha) IN; `(28.116)`(ref-number) OUT; `$x$`(math) OUT; 반복 boilerplate OUT; 정상 60자+ OUT; status=failed OUT.
- `is_math_dense`/`is_reference_number`/`is_repeated` 단위.
- retranslate(mock LLM): 이웃 context가 프롬프트에 포함, 대상만 upsert, **실패 시 기존 translated 보존**(no-write).
- `--dry-run`: 대상 출력 + chunk_translations **무변경**.
- resize jsdom: drag→`--chat-w`/`.pane--reflow` margin/`.chat` width 갱신, clamp(min280/max60vw), sessionStorage 저장, restore(sessionStorage→복원), toggle close→margin 0.
- 회귀 736→736+신규. ruff/format/mypy clean. 1.x blocks=49850.

## DoD mapping
| DoD item | How | Evidence |
| --- | --- | --- |
| 짧은 fragment 오역 개선(where) | select + neighbor retranslate | test_select + retranslate + 사용자(where→여기서) |
| 수식밀집/참조/보일러플레이트 제외 | is_math_dense/is_reference_number/is_repeated | test 제외 케이스 |
| 덮어쓰기 안전 (dry-run + fail-preserve) | --dry-run + no-write | test dry-run(무변경) + fail-preserve |
| 사이드탭 resize + 본문 연동 + sessionStorage | resize.js | resize jsdom(drag/margin/clamp/sessionStorage) + 사용자 |
| 1.x 무손상 | translate/frontend만, migration 0 | blocks=49850 + 736 회귀 |

## 위험 / 완화
- 정상 번역 덮어쓰기 → `<25` + 3 제외(math/ref/repeated) + **dry-run**(Stage 0 데이터: doc7 대상 사실상 'where' 1개).
- 재번역 실패 손실 → fail-preserve(기존 row 유지, 8b no-write), dry-run 선확인.
- 이웃이 비텍스트(equation/image) → text 이웃만 context(라벨/skip).
- resize 본문/compare/KaTeX → 고정 drawer + margin(그리드 불변), KaTeX 인라인 reflow(리렌더 불요), min/max clamp.
- sessionStorage 복원 타이밍 → initResize가 DOM ready 후 restore; 미설정 시 기본 380px.
- math-dense 판정 일관성(8e 대상) → has_math 재사용(8b와 동일 기준).
