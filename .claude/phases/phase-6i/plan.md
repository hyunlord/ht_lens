# Phase 6i — LaTeX Rendering (V2, post Codex debate)

> **V1 → V2 changelog**: Codex critique 15개. 9 ACCEPT / 4 PARTIAL / 2 REJECT. Critical fixes:
> 1. `katex.min.js` 는 UMD — `katex.mjs` (ESM) 로 변경 (Codex §2.2 ACCEPT, verified via `file` + grep export)
> 2. DOMPurify MathML allowlist 제거 — KaTeX 출력은 sanitize 경로 밖이므로 over-engineering (Codex §1.1 ACCEPT)
> 3. `index.html` 변경 제외 — KaTeX는 viewer.html 만 (Codex §1.2 ACCEPT)
> 4. `text.includes("$")` → paired-delimiter regex (Codex §3.1 ACCEPT)
> 5. KaTeX `ignoredTags` 명시 (`pre/code/script/...`) (Codex §3.3 ACCEPT)
> 6. Assistant-only math path in chat (Codex §5 ACCEPT)
> 7. Vendor `SOURCE.md` for reproducibility (Codex §2.3 ACCEPT)
> 8. ROADMAP §6i wording — 사용자 직접 (Codex §2.1 acknowledged)
> 9. Tests 6 → 12 (6 added per Codex §5)

## Goal
Viewer 와 chat 응답의 `$...$` (그리고 `$$...$$`) LaTeX 수식이 raw source가 아닌 렌더된 형태로 표시되도록 한다. 번역 결과 (v2_ko prompt 규칙대로 수식 영어 유지) 는 그대로, 표시만 변경.

## Context

### 사용자 발견 (doc 7 page 996)
- 번역 정상, 수식만 LaTeX source 노출: `$p(z) = \text{Dir}(z|\alpha)$`, `$\sum_{k=1}^K z_k = 1$`, `$\mathbb{E}[z_{nk}|x_n]$` 등.

### 기술 — KaTeX 0.16.22 ESM
- `katex.mjs` (596KB unminified ESM, `export { ... katex as default ... }`) + `contrib/auto-render.mjs` (8KB)
- `.min.js` 는 UMD wrapper (`!function(e,t){"object"==typeof exports...`) — ESM import 불가
- 폰트: `fonts/*.woff2` 24 files, ~1.2MB
- CSS: `katex.min.css` ~28KB

### ROADMAP 상태 (Codex §2.1)
ROADMAP.md를 사용자가 WIP 수정 중. Phase 6i 항목은 사용자 prompt에서 직접 invoke. 본 plan은 사용자 directive 기준 진행. ROADMAP §6i wording은 사용자 직접 (별도 작업, summary 권장).

### 사용자 결정 (Stage 1)
- **A**: Vendor committed (Phase 5 pattern)
- **B**: Inline `$...$` only (display `$$...$$`도 cost 0이라 함께 — V2에서 명시)
- **C**: el.innerHTML + renderMathInElement (auto-render)
- **D**: marked 후 KaTeX auto-render

## Scope

**In**:

### Sub-goal 1 — KaTeX vendor (ESM 정확본)
- `src/ht_lens/api/static/vendor/katex/`:
  - `katex.mjs` (~596KB ESM)
  - `katex.min.css` (~28KB)
  - `auto-render.mjs` (contrib ESM, ~8KB)
  - `fonts/` (~1.2MB, 24 woff2)
  - `LICENSE` (MIT)
  - `SOURCE.md` — 재현 명령 (npm pack katex@0.16.22 + cp)

### Sub-goal 2 — `render_markdown.js` 최소 변경
- DOMPurify config **그대로 유지** (MathML allowlist 추가 X)
- 새 export `applyMath(el)` — `auto-render.mjs` renderMathInElement 래퍼:
  ```js
  import katex from "../../vendor/katex/katex.mjs";
  import renderMathInElementExt from "../../vendor/katex/auto-render.mjs";

  export function applyMath(el) {
    if (!el) return;
    try {
      renderMathInElementExt(el, {
        delimiters: [
          { left: "$$", right: "$$", display: true },
          { left: "$", right: "$", display: false },
        ],
        ignoredTags: ["script", "noscript", "style", "textarea", "pre", "code", "option"],
        throwOnError: false,
        errorColor: "#cc0000",
        trust: false,
        strict: false,
      });
    } catch (e) {
      // last-resort guard — renderMathInElement shouldn't throw with
      // throwOnError:false, but if it does, do not break the host page.
      console.warn("KaTeX renderMathInElement failed", e);
    }
  }
  ```

### Sub-goal 3 — Viewer block overlay (paired-delimiter gate)
- `block.js`:
  ```js
  // existing: el.textContent = text + fitFontSize
  if (overlayMode === "translation" && _hasPairedMath(text)) {
    applyMath(el);
  }
  ```
  `_hasPairedMath` helper:
  ```js
  const INLINE_MATH_RE = /\$[^$\n]+\$/;
  const DISPLAY_MATH_RE = /\$\$[\s\S]+?\$\$/;
  function _hasPairedMath(text) {
    return INLINE_MATH_RE.test(text) || DISPLAY_MATH_RE.test(text);
  }
  ```
- Currency `$5.00`은 짝 없는 `$` → no trigger.

### Sub-goal 4 — Chat assistant-only math
- `message.js`:
  ```js
  // existing: body.innerHTML = renderMarkdown(msg.content || "");
  if (msg.role === "assistant") {
    applyMath(body);
  }
  ```
- user/system 메시지는 plain — `$5.00` 안전.

### Sub-goal 5 — HTML link
- **`viewer.html` 만** `<link rel="stylesheet" href="/static/vendor/katex/katex.min.css">`. `index.html` 제외.

### Sub-goal 6 — CSS
```css
/* base.css 또는 viewer.css */
.block .katex { font-size: inherit; line-height: inherit; }
.message .katex-display { margin: 0.5em 0; overflow-x: auto; }
.katex-error { color: var(--warn, #cc0000); }
```

### Sub-goal 7 — Tests (12 total: 6 V1 + 6 V2 added)

**기존 V1 (6)**:
1. `test_inline_math_renders_to_katex_span`
2. `test_korean_text_with_inline_math_mixed`
3. `test_display_math_renders` ($$...$$)
4. `test_broken_latex_falls_back` (throwOnError false)
5. `test_dompurify_preserves_katex_html_via_renderMarkdown_then_applyMath`
6. `test_no_xss_via_href` (`\href{javascript:alert(1)}{x}` 차단)

**V2 추가 (Codex §5, 6)**:
7. `test_chat_assistant_message_applies_math_and_keeps_related_blocks` — assistant 메시지 KaTeX 렌더 + related_blocks footer 보존
8. `test_chat_user_message_with_dollar_stays_plain` — user 메시지에 `$5.00` 있어도 KaTeX 렌더 안 됨
9. `test_block_translation_math_preserves_click_and_contextmenu` — applyMath 후 `ht-lens:block-click` / `ht-lens:block-contextmenu` listener 동작
10. `test_paired_delimiter_gate_ignores_unmatched_dollar` — `"$5.00 only"` → KaTeX 호출 안 됨
11. `test_markdown_code_block_math_not_rendered` — fenced code block 안 `$x^2$` → 렌더 안 됨 (ignoredTags)
12. `test_static_assets_serve_200_and_only_viewer_links_katex` — `/static/vendor/katex/katex.min.css` + 한 font 200 OK. index.html에는 katex link 없음, viewer.html에만 있음.

**Out**:
- Backend 변경 0
- DB 변경 0
- v2_ko prompt 변경 0
- MathJax
- Block overlay layout 변경 (fitFontSize 그대로, KaTeX glyph overflow는 known limitation)
- Equation numbering / `\eqref` / `\label`
- `mhchem` / `render-a11y-string` 등 다른 KaTeX contrib
- ROADMAP §6i wording (사용자 직접)
- index.html link (Codex §1.2)

## Approach

### 1. Vendor 설치
```bash
mkdir -p src/ht_lens/api/static/vendor/katex
SRC=~/.vscode-server/cli/servers/Stable-7d842fb85a0275a4a8e4d7e040d2625abbf7f084/server/node_modules/katex
cp $SRC/dist/katex.mjs $SRC/dist/katex.min.css src/ht_lens/api/static/vendor/katex/
cp $SRC/dist/contrib/auto-render.mjs src/ht_lens/api/static/vendor/katex/
cp -r $SRC/dist/fonts src/ht_lens/api/static/vendor/katex/
cp $SRC/LICENSE src/ht_lens/api/static/vendor/katex/
```
Plus `SOURCE.md` 작성.

### 2. `render_markdown.js`
DOMPurify 그대로 + `applyMath` 새 export. **MathML allowlist 추가 안 함** (KaTeX 출력은 sanitize 안 거침).

### 3. `block.js`
`text.includes("$")` → `_hasPairedMath(text)` regex. `applyMath` 는 textContent 설정 후 호출 (KaTeX가 in-place 변환).

### 4. `message.js`
`msg.role === "assistant"` 일 때만 `applyMath(body)`. user / system 메시지는 plain.

### 5. `viewer.html`
`<link>` 추가. `index.html` 변경 X.

### 6. CSS
KaTeX inherit + display margin.

### 7. SOURCE.md
```
KaTeX 0.16.22 (MIT license).

Files:
- katex.mjs           (ESM module, export default = katex)
- katex.min.css       (font-face declarations)
- auto-render.mjs     (contrib auto-render extension, ESM)
- fonts/*.woff2       (KaTeX_Main/Math/AMS/Caligraphic/Fraktur/Script/SansSerif/Size1-4/Typewriter)

To regenerate:
    npm pack katex@0.16.22
    tar xf katex-0.16.22.tgz -C /tmp/
    BASE=/tmp/package/dist
    DEST=src/ht_lens/api/static/vendor/katex
    cp $BASE/katex.mjs $BASE/katex.min.css $DEST/
    cp $BASE/contrib/auto-render.mjs $DEST/
    cp -r $BASE/fonts $DEST/
    cp /tmp/package/LICENSE $DEST/
```

## File-level changes

| Path | Action | Note |
| ---- | ------ | ---- |
| `src/ht_lens/api/static/vendor/katex/katex.mjs` | NEW | ~596KB ESM |
| `src/ht_lens/api/static/vendor/katex/katex.min.css` | NEW | ~28KB |
| `src/ht_lens/api/static/vendor/katex/auto-render.mjs` | NEW | ~8KB ESM |
| `src/ht_lens/api/static/vendor/katex/fonts/*.woff2` | NEW (24 files) | ~1.2MB |
| `src/ht_lens/api/static/vendor/katex/LICENSE` | NEW | MIT |
| `src/ht_lens/api/static/vendor/katex/SOURCE.md` | NEW | 재현 명령 |
| `src/ht_lens/api/static/js/utils/render_markdown.js` | MODIFY | `applyMath` export (DOMPurify config 그대로) |
| `src/ht_lens/api/static/js/components/block.js` | MODIFY | `_hasPairedMath` + `applyMath` |
| `src/ht_lens/api/static/js/components/message.js` | MODIFY | assistant-only `applyMath` |
| `src/ht_lens/api/static/viewer.html` | MODIFY | KaTeX CSS link |
| `src/ht_lens/api/static/css/base.css` | MODIFY (or viewer.css) | KaTeX inherit + display margin |
| `tests/integration/test_katex_render_js.py` | NEW | jsdom 11 tests (1-11) |
| `tests/integration/test_static_serving.py` | MODIFY (또는 NEW test) | static asset 200 + scope (test 12) |

## Dependencies (new)
없음 (vendor committed).

## Test strategy

**12 jsdom + python tests** (Codex §5 추가 6 포함). 회귀 552 → 564+.

## DoD mapping

위 §challenge.md DoD checklist 참조.

## Risk / 주의

### Critical (V1 hazards eliminated)
1. ~~UMD import fail~~ → `katex.mjs` ESM (Codex §2.2)
2. ~~DOMPurify allowlist over-engineering~~ → 제거 (§1.1)
3. ~~`text.includes("$")` false positives~~ → paired-delimiter (§3.1)
4. ~~Code block 수식 잘못 렌더~~ → `ignoredTags` (§3.3)
5. ~~User msg에 KaTeX 잘못 적용~~ → assistant-only (§5)

### Known limitation
6. **fitFontSize vs KaTeX glyph layout**: best-effort. raw text 기반 + inherit. 일부 수식 over-flow는 `overflow: hidden`로 clip. KaTeX height-aware fit은 별도 phase.
7. **ROADMAP §6i wording**: 사용자 직접 (summary 권장).

### Debate에서 verify-cross에서 다룰 잠재 항목
- DOMPurify 미설정 시 `<a target rel>` 외 attr 처리? 기존 Phase 5 test 통과여부.
- `_hasPairedMath` regex가 `$$ x $$` (display) 도 inline match? 둘 다 trigger되면 applyMath 한 번만 실행이라 OK.
- KaTeX 동기 렌더 latency for math-heavy page (사용자 검증 영역).
