# Phase 6i — Challenge (Worker response to Codex debate)

## Summary decision: **RE-PLAN**

Codex raised 15 substantive points. 4개는 critical (ESM vs UMD, DOMPurify allowlist over-engineering, ROADMAP scope, vendor source reproducibility). 11개 substantive. **9 ACCEPT, 4 PARTIAL, 2 REJECT**.

## Debate responses

### 1. Over-engineering

#### §1.1 DOMPurify MathML/tag allowlist 불필요 — **ACCEPT (critical)**
- Codex 주장: marked가 emit한 HTML은 sanitize 후 KaTeX가 처리. KaTeX가 만든 HTML은 sanitize 안 거침. 따라서 ADD_TAGS의 `math/semantics/mrow/...` 는 marked가 그것을 emit할 때만 필요한데, default marked는 emit 안 함. **security surface만 늘림**.
- 확인: 정확. KaTeX 렌더 결과 (`<span class="katex">...`) 는 KaTeX 자체 trust 모드로 안전성 책임. DOMPurify는 marked 출력만 보호.
- **결론 V2**: `ADD_TAGS` 의 MathML 노드 모두 제거. `ADD_ATTR`도 marked 출력에 필요한 것만 (기존 `target/rel` + KaTeX 출력은 trust=false면 안전). KaTeX 출력의 안전성은 별도 test (test 6 XSS guard) 로 보장.

#### §1.2 `index.html`은 document list — KaTeX CSS 불필요 — **ACCEPT**
- 확인: `index.html`은 doc list 페이지 (block overlay/chat 없음). KaTeX 부담 없이.
- **결론 V2**: `index.html` 변경 제외. `viewer.html` 만 link 추가.

#### §1.3 inline `$...$` only로 시작했으나 display `$$...$$` 함께 — **PARTIAL**
- Codex 주장: scope 확장.
- 확인: KaTeX auto-render default는 `$...$` + `$$...$$` 둘 다 처리. 비용 0. 단 사용자 결정 B "Inline only"였으니 plan 명시 필요.
- **결론 V2**: delimiters에 `$$...$$` 포함 명시. 사용자에게 부담 없이 추가 (cost 0). v2_ko prompt가 inline만 쓰지만 학술 문서 본문에 display 수식이 raw로 들어올 가능성 있음 (Murphy PML 본문 인용).

### 2. Hidden assumptions

#### §2.1 ROADMAP scope — Phase 6i 없음 — **ACCEPT (사용자 directive)**
- Codex 주장: WORKFLOW.md + CLAUDE.md scope rule 위반.
- 확인: ROADMAP.md를 사용자가 WIP 수정 중. Phase 6i는 사용자 prompt에서 명시적으로 직접 invoke. **사용자 directive로 ROADMAP과 align 예정**.
- **결론 V2**: plan V2 §Context에 "사용자가 ROADMAP.md 수정 중 — Phase 6i는 사용자 directive로 invoke됨. ROADMAP은 별도 사용자 작업" 명시. summary에서 사용자 ROADMAP §6i wording 권장.

#### §2.2 `katex.min.js`는 UMD, ESM 아님 — **ACCEPT (CRITICAL bug)**
- Codex 주장: `katex.min.js`는 script-tag 용 UMD. ESM 아님. `import` 실패.
- 확인 (직접 검증): `file katex.min.js` → `JavaScript source ... !function(e,t)...` (UMD wrapper). `katex.mjs` 첫 줄 → `export { ... katex as default ... }` (ESM 확정).
- 영향: V1 plan대로면 viewer 로드 시 즉시 깨짐.
- **결론 V2**: vendor에 `katex.mjs` + `contrib/auto-render.mjs` 사용 (NOT .min.js). 크기: 596KB + 8KB unminified (~280KB min은 ESM 형태 없음). 1.5MB → 1.8MB 약간 증가 acceptable.

#### §2.3 Vendor 획득 not reproducible — **ACCEPT**
- Codex 주장: `~/.vscode-server/.../node_modules/katex/` 가 모든 worker machine에 있지 않음. Not repo contract.
- 확인: 정확. CI runner에 vscode-server 없음 (vendor 이미 committed면 OK지만 source는 기록 필요).
- **결론 V2**: vendor 디렉토리에 `SOURCE.md` 추가 — "KaTeX 0.16.22 from npm `katex` package, MIT license. To regenerate: `npm pack katex@0.16.22 && tar xf katex-0.16.22.tgz -C /tmp && cp -r /tmp/package/dist/{katex.mjs,katex.min.css,fonts,LICENSE} src/.../vendor/katex/ && cp /tmp/package/dist/contrib/auto-render.mjs src/.../vendor/katex/`".

#### §2.4 DoD XSS 문구가 misleading — **PARTIAL**
- Codex 주장: `trust: false + DOMPurify` 라고 했지만 DOMPurify는 post-KaTeX path에 없음.
- 확인: 정확. DOMPurify는 marked 출력만 보호. KaTeX 출력은 KaTeX 자체 trust=false로 보호.
- **결론 V2**: DoD XSS 항목 정확히 분리:
  - marked 경로 XSS: DOMPurify (기존)
  - KaTeX 경로 XSS: `trust: false` (KaTeX 자체 sanitization)
  - test 6은 KaTeX 경로의 `\href javascript:` 차단 검증

### 3. Edge cases

#### §3.1 `text.includes("$")` false positives — **ACCEPT**
- Codex 주장: currency, shell var, OCR noise, prose about LaTeX 모두 `$` 포함. v2_ko promise는 사용자 입력 / 옛 doc 에서 보장 안 됨.
- 확인: 정확. 더 견고한 gate 필요.
- **결론 V2**: `text.includes("$")` → **paired-delimiter regex**:
  ```js
  const HAS_INLINE_MATH = /\$[^$\n]+\$/;
  const HAS_DISPLAY_MATH = /\$\$[\s\S]+?\$\$/;
  if (HAS_INLINE_MATH.test(text) || HAS_DISPLAY_MATH.test(text)) {
    applyMath(el);
  }
  ```
  단일 `$5.00` 같은 짝 없는 `$` 는 trigger 안 함. `$ . $` 같은 noise는 KaTeX가 throwOnError:false로 silent fallback.

#### §3.2 fitFontSize 와 KaTeX glyph layout 충돌 — **PARTIAL**
- Codex 주장: font_fit.js는 Noto/Inter 측정. KaTeX glyph 레이아웃 (\sum, \frac, super/sub) 은 bbox 초과 가능. block.js overflow-warning logic과 collision.
- 확인: 정확. 본 phase scope 안에서 완벽 해결은 어려움 (KaTeX 렌더 결과 height 측정 후 fitFontSize 재계산은 큰 변경).
- **결론 V2**: 본 phase는 best-effort — raw text로 fit 계산 + KaTeX 렌더는 inherit. Known limitation 명시 (별도 phase에서 KaTeX height-aware 처리). 수식 over-flow는 기존 `overflow: hidden` 으로 clip — visual 결과는 "수식이 약간 잘릴 수 있음" 보고.

#### §3.3 Chat의 inline code / fenced code 안 `$` — **ACCEPT**
- Codex 주장: KaTeX `ignoredTags` default가 `pre/code/script/...` 포함하지만 plan에서 명시 검증 없음.
- **결론 V2**: applyMath 호출 시 `ignoredTags: ["script", "noscript", "style", "textarea", "pre", "code", "option"]` 명시 (KaTeX default 명시적 보장). test 추가.

#### §3.4 Font-path breakage 우려 — **PARTIAL**
- Codex 주장: KaTeX CSS expects `fonts/` relative path. 잘못 layout 시 fallback glyph + reflow.
- 확인: 정확한 우려. KaTeX CSS의 `@font-face url` 은 `fonts/KaTeX_Main-Regular.woff2` 형태. CSS 파일이 `vendor/katex/katex.min.css` 라면 fonts는 `vendor/katex/fonts/` 에 있어야 함. plan에 명시.
- **결론 V2**: vendor 레이아웃 명확. test로 한 font URL `200 OK` 확인.

### 4. Alternative approaches

#### §4.1 ESM `.mjs` 사용 (§2.2 결합) — **ACCEPT**

#### §4.2 render_markdown.js를 markdown+sanitize에 집중, math는 component level — **ACCEPT (§1.1 결합)**
- DOMPurify allowlist 제거 + `applyMath` 는 별도 export, component (block.js/message.js)에서만 호출.

#### §4.3 paired-delimiter gate (§3.1 결합) — **ACCEPT**

### 5. Missing tests

| Codex 제안 | V2 채택 |
| --- | --- |
| `test_render_message_assistant_applies_math_and_preserves_related_blocks` | ✅ jsdom test 7 |
| `test_render_message_user_content_with_dollar_stays_plain_text` | ✅ jsdom test 8 (user/system 경로는 applyMath 호출 안 함) |
| `test_render_block_translation_math_preserves_click_and_contextmenu_contract` | ✅ jsdom test 9 (click + contextmenu listener 살아있음 확인) |
| `test_apply_math_ignores_currency_or_unmatched_dollar` | ✅ jsdom test 10 (paired-delimiter gate 검증) |
| `test_markdown_code_block_math_not_rendered` | ✅ jsdom test 11 (KaTeX ignoredTags `pre/code`) |
| Static asset KaTeX CSS + font URL 200 OK + only viewer.html links | ✅ Python test 12 (`test_static_serving.py` 또는 신규) |

기존 6 + Codex 추가 6 = **12 tests**.

## Plan revisions (V1 → V2)

1. **CRITICAL ESM fix**: `katex.mjs` + `auto-render.mjs` 사용 (NOT min.js / min.mjs는 없음). Vendor size 1.5MB → 1.8MB.
2. **Scope minimize**: `viewer.html` 만 KaTeX CSS link (index.html 제외).
3. **DOMPurify config 미니멀**: MathML allowlist 제거. KaTeX 출력은 KaTeX trust=false로 보호.
4. **Vendor SOURCE.md** 추가 (npm package 재현 명령).
5. **Paired-delimiter gate**: `text.includes("$")` → regex `\$[^$\n]+\$` 또는 `\$\$[\s\S]+?\$\$`.
6. **KaTeX `ignoredTags` 명시**: `pre/code/script/...`.
7. **Assistant-only math**: `message.js`에서 assistant message에만 `applyMath` (user/system은 plain).
8. **fitFontSize limitation 명시**: best-effort, KaTeX height-aware 처리는 별도 phase.
9. **DoD XSS 정확 분리**: marked 경로 (DOMPurify) + KaTeX 경로 (trust:false).
10. **Tests 6 → 12**: 6 추가.
11. **ROADMAP §6i wording**: 사용자 직접 수정 (summary 권장).

## DoD checklist (V2)

| DoD item | Status | Evidence |
| -------- | ------ | -------- |
| Viewer `$...$` 렌더 (paired) | Open | test 1 + 사용자 viewer (doc 7 p996) |
| Chat assistant 응답 수식 렌더 | Open | test 7 |
| 한국어 + 수식 혼재 | Open | test 2 |
| 깨진 LaTeX fallback | Open | test 4 |
| KaTeX 경로 XSS (\href javascript:) | Open | test 6 |
| marked 경로 XSS (기존 보장) | Open | Phase 5 test_render_markdown_js 통과 |
| Assistant only math | Open | test 8 (user 메시지 plain) |
| Block click + contextmenu 보존 | Open | test 9 |
| Currency/unpaired `$` 무시 | Open | test 10 |
| Code block 내부 수식 무시 | Open | test 11 |
| KaTeX static assets 200 OK | Open | test 12 |
| Only viewer.html links KaTeX | Open | test 12 |
| 552 → 564+ tests | Open | full pytest |
| ESM import 실제 동작 | Open | jsdom load tests (1-11) |
| Vendor reproducibility | Open | `SOURCE.md` 존재 |

## Risk register (V2)

| Risk | Likelihood | Impact | Mitigation |
| ---- | ---------- | ------ | ---------- |
| UMD import fail (V1 hazard) | Eliminated | High | `katex.mjs` ESM 사용 |
| DOMPurify allowlist 보안 surface (V1) | Eliminated | Medium | allowlist 제거, marked-only path 보호 |
| `text.includes("$")` false positives (V1) | Eliminated | Medium | paired-delimiter regex |
| ROADMAP wording mismatch | Known | Low | summary에서 사용자 권장 |
| Vendor source not reproducible | Eliminated | Low | SOURCE.md |
| fitFontSize KaTeX glyph 충돌 | Known | Low | best-effort, 별도 phase |
| KaTeX font path breakage | Low | Medium | static asset test (test 12) |
| Code block math 잘못 렌더 | Eliminated | Low | `ignoredTags` 명시 + test 11 |

## Decision
- [x] PASS → proceed to RE-PLAN (V2) → code
- [ ] RE-PLAN (reason: ) — chosen
