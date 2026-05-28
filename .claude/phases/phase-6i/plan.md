# Phase 6i — LaTeX Rendering (Viewer + Chat)

## Goal
사용자 핵심 use case (Murphy PML, Aggarwal RecSys 등 학술 문서) 에서 viewer 와 chat 응답의 `$...$` LaTeX 수식이 raw source가 아닌 렌더된 형태로 표시되도록 한다. 번역 결과 (v2_ko prompt 규칙대로 수식 영어 유지) 는 그대로, 표시만 변경.

## Context

### 사용자 발견 (doc 7 page 996)
- 번역은 정상 (한국어 자연스러움)
- 수식 LaTeX source 노출: `$p(z) = \text{Dir}(z|\alpha)$`, `$\sum_{k=1}^K z_k = 1$`, `$\mathbb{E}[z_{nk}|x_n]$` 등
- viewer + chat 모두 동일 issue

### 기술 선택 — KaTeX (NOT MathJax)
- KaTeX 0.16.22 (locally available, `~/.vscode-server/.../node_modules/katex/`):
  - 동기 렌더, 페이지 리플로우 없음
  - Bundle 작음 (~280KB JS + ~7KB auto-render extension + ~1.2MB fonts)
  - Inline `$...$` 렌더 충분 (수식 많은 textbook에 적합)
- MathJax 대비: 폰트 로딩 + 번들 + 동기 렌더 우위. ht_lens는 MathML/접근성/`\eqref` 불필요.
- Phase 5 vendor pattern (marked@11 + DOMPurify ESM) — KaTeX 자연스럽게 추가.

### 사용자 결정 (Stage 1)
- **A**: Vendor committed (Phase 5 pattern, 오프라인 우선)
- **B**: Inline `$...$` only (v2_ko prompt 표준). + display `$$...$$` 도 KaTeX auto-render default가 처리 (비용 0).
- **C**: el.innerHTML + renderMathInElement (auto-render contrib)
- **D**: marked 후 KaTeX auto-render (DOMPurify config 조정)

### 결정 E (plan 단계 worker 자체 결정) — fitFontSize 충돌
viewer block overlay는 fitFontSize로 텍스트 크기 맞춤. KaTeX 렌더는 수식 height 변동 가능.
- **선택**: fitFontSize 계산은 raw text (plain) 기반 — KaTeX 렌더 결과 크기는 inherit 사용
- KaTeX `.katex` CSS rule: `font-size: inherit` 으로 block font에 맞춤
- 수식 width가 한 줄 넘으면 overflow:hidden으로 clip (기존 viewer 동작 유지)
- 추후 개선 영역 (별도 phase)

## Scope

**In**:

### Sub-goal 1 — KaTeX vendor committed
- `src/ht_lens/api/static/vendor/katex/`:
  - `katex.min.js` (ESM, ~280KB)
  - `katex.min.css` (~28KB)
  - `auto-render.min.js` (contrib auto-render, ~7KB)
  - `fonts/` (~1.2MB, 24 woff2 files)
  - `LICENSE` (MIT)
- Source: KaTeX 0.16.22 local node_modules → `cp -r` to vendor.

### Sub-goal 2 — `render_markdown.js` KaTeX 통합
- DOMPurify config 확장: KaTeX HTML+MathML tags/attrs 허용 (`span`, `math`, `semantics`, `mrow`, `mi`, `mn`, `mo`, `mfrac`, `msup`, `msub`, `class`, `style`, `aria-hidden`, etc.)
- 새 export `applyMath(el)` — `renderMathInElement` 래퍼:
  - delimiters: `$...$` inline + `$$...$$` display
  - `throwOnError: false`, `trust: false`, `strict: false`
  - errorColor: `#cc0000`
- 기존 `renderMarkdown` 호출자 변경 없음.

### Sub-goal 3 — Viewer block overlay 렌더
- `block.js`: `el.textContent = text` 그대로, **text에 `$` 포함 시 `applyMath(el)` 호출**
- fitFontSize는 raw text 기준 (변경 없음)
- CSS `.block .katex { font-size: inherit; line-height: inherit; }` 추가

### Sub-goal 4 — Chat 응답 렌더
- `message.js`: `body.innerHTML = renderMarkdown(...)` 후 `applyMath(body)` 호출

### Sub-goal 5 — HTML link
- `index.html` + `viewer.html`에 `<link rel="stylesheet" href="/static/vendor/katex/katex.min.css">` 추가

### Sub-goal 6 — Tests (jsdom 6 tests)
- `tests/integration/test_katex_render_js.py` (Phase 5 `test_render_markdown_js.py` 패턴):
  1. `test_inline_math_renders_to_katex_span` — `$E=mc^2$` → `<span class="katex">`
  2. `test_korean_text_with_inline_math_mixed` — `"잠재 변수 $p(z)$ 사용"` → 한국어 그대로 + KaTeX span
  3. `test_display_math_renders` — `$$\sum_k z_k = 1$$` → display
  4. `test_broken_latex_falls_back` — `$\invalidcmd{` → no exception (throwOnError false)
  5. `test_dompurify_preserves_katex_html` — `renderMarkdown` + `applyMath` 통합 후 KaTeX span 살아남음
  6. `test_no_xss_via_href` — `$\href{javascript:alert(1)}{x}$` → `javascript:` 차단

**Out**:
- Backend 변경 0 (translation/embedding 영향 0)
- DB 변경 0
- v2_ko prompt 변경 0
- MathJax (KaTeX만)
- Block overlay layout 변경 (fitFontSize 그대로)
- Equation numbering / `\eqref` / `\label` (MathJax 영역)
- `mhchem` chemical formula
- 한국어 \text{} 안 polyglossia
- KaTeX 다른 contrib extensions (copy-tex, render-a11y)

## Approach

### 1. Vendor 설치
```bash
mkdir -p src/ht_lens/api/static/vendor/katex
SRC=~/.vscode-server/cli/servers/Stable-*/server/node_modules/katex/dist
cp $SRC/katex.min.js $SRC/katex.min.css src/ht_lens/api/static/vendor/katex/
cp $SRC/contrib/auto-render.min.js src/ht_lens/api/static/vendor/katex/
cp -r $SRC/fonts src/ht_lens/api/static/vendor/katex/
cp ~/.vscode-server/.../node_modules/katex/LICENSE src/ht_lens/api/static/vendor/katex/
```

### 2. `render_markdown.js`
```js
import { marked } from "../../vendor/marked.esm.js";
import DOMPurifyFactory from "../../vendor/purify.es.mjs";
import katex from "../../vendor/katex/katex.min.js";
import renderMathInElementExt from "../../vendor/katex/auto-render.min.js";

// ...existing DOMPurify init + marked.setOptions...

export function renderMarkdown(text) {
  if (!text) return "";
  const html = marked.parse(text);
  return DOMPurify.sanitize(html, {
    USE_PROFILES: { html: true },
    ADD_TAGS: [
      "math", "semantics", "mrow", "annotation",
      "msup", "msub", "msubsup", "mfrac",
      "mi", "mn", "mo", "mtext",
      "munderover", "mover", "munder",
      "mspace", "mstyle", "mtable", "mtr", "mtd",
    ],
    ADD_ATTR: [
      "target", "rel", "class", "style", "aria-hidden",
      "data-mathml", "stretchy", "fence",
      "lspace", "rspace", "minsize", "maxsize",
      "encoding", "displaystyle", "scriptlevel",
    ],
  });
}

export function applyMath(el) {
  if (!el) return;
  try {
    renderMathInElementExt(el, {
      delimiters: [
        { left: "$$", right: "$$", display: true },
        { left: "$", right: "$", display: false },
      ],
      throwOnError: false,
      errorColor: "#cc0000",
      trust: false,
      strict: false,
    });
  } catch (e) {
    console.warn("KaTeX renderMathInElement failed", e);
  }
}
```

### 3. `block.js`
```js
// existing: el.textContent = text
if (overlayMode === "translation" && text.includes("$")) {
  applyMath(el);  // raw text → KaTeX-rendered HTML in place
}
```

### 4. `message.js`
```js
body.innerHTML = renderMarkdown(msg.content || "");
applyMath(body);
```

### 5. `index.html` / `viewer.html`
```html
<link rel="stylesheet" href="/static/vendor/katex/katex.min.css">
```

### 6. CSS
```css
/* base.css */
.block .katex { font-size: inherit; line-height: inherit; }
.message .katex-display { margin: 0.5em 0; }
.katex-error { color: var(--warn, #cc0000); }
```

## File-level changes

| Path | Action | Note |
| ---- | ------ | ---- |
| `src/ht_lens/api/static/vendor/katex/katex.min.js` | NEW | ~280KB |
| `src/ht_lens/api/static/vendor/katex/katex.min.css` | NEW | ~28KB |
| `src/ht_lens/api/static/vendor/katex/auto-render.min.js` | NEW | ~7KB |
| `src/ht_lens/api/static/vendor/katex/fonts/*.woff2` | NEW (24 files) | ~1.2MB |
| `src/ht_lens/api/static/vendor/katex/LICENSE` | NEW | MIT |
| `src/ht_lens/api/static/js/utils/render_markdown.js` | MODIFY | DOMPurify config + `applyMath` |
| `src/ht_lens/api/static/js/components/block.js` | MODIFY | conditional `applyMath` |
| `src/ht_lens/api/static/js/components/message.js` | MODIFY | `applyMath` after innerHTML |
| `src/ht_lens/api/static/index.html` | MODIFY | `<link>` |
| `src/ht_lens/api/static/viewer.html` | MODIFY | 동일 |
| `src/ht_lens/api/static/css/base.css` | MODIFY | KaTeX CSS overrides |
| `tests/integration/test_katex_render_js.py` | NEW | jsdom 6 tests |

## Dependencies (new)
없음 (vendor committed).

## Test strategy

### jsdom (6 tests, Phase 5 패턴)
- 위 Sub-goal 6 참조

### 회귀
- 기존 552 → 558+ (+6 KaTeX jsdom)
- Phase 5 `test_render_markdown_js.py` 통과 (DOMPurify config 확장이 기존 XSS 방어 안 깨야)
- `test_static_serving.py`가 있다면 vendor/katex 정적 200 OK

## DoD mapping

| DoD item | How to satisfy | Evidence |
| -------- | -------------- | -------- |
| Viewer `$...$` 렌더 | `block.js` `applyMath` | test 1 + 사용자 viewer (doc 7 p996) |
| Chat 응답 수식 렌더 | `message.js` `applyMath` | test 5 + 사용자 chat |
| 한국어 + 수식 혼재 | KaTeX delimiter 검출 | test 2 |
| 깨진 LaTeX fallback | `throwOnError: false` | test 4 |
| XSS 방어 | `trust: false` + DOMPurify | test 6 |
| 552 → 558+ | jsdom 6 new | full pytest |
| Vendor offline | committed | `find vendor/katex -type f` |
| Phase 5 vendor pattern 유지 | marked/DOMPurify 패턴 | code review |

## Risk / 주의

### Medium
1. **DOMPurify가 KaTeX HTML strip**: `ADD_TAGS`/`ADD_ATTR` 정확 명시 필요. 부족하면 KaTeX span 사라짐 → 사용자 visual 깨짐. test 1+5로 직접 검증.
2. **marked가 `$...$` 처리**: marked 11+ default는 `$` 안 건드림 (보장). 단 fenced code block 안 `$` 도 통과 — KaTeX가 code block 내부도 렌더하면 잘못. KaTeX auto-render는 `ignoredTags: ["script", "noscript", "style", "textarea", "pre", "code", "option"]` default 가 있어 pre/code 무시.
3. **fitFontSize와 충돌**: raw text 기준 → 수식 inherit 후 실제 너비 약간 다름. 사용자 perception 작음.

### Low
4. **번들 크기**: ~1.5MB (fonts 우세). 일회성.
5. **첫 페이지 fonts FOIT**: ~50ms.
6. **수식 많은 page render latency**: doc 7 p996 ~20수식 동기 ~50ms.

### Debate에서 다룰 질문
- KaTeX의 `trust: false` 가 정말 `\href` javascript: 차단? (KaTeX docs: trust=false면 \href는 안전 protocol만)
- DOMPurify ADD_TAGS의 mathml node list — KaTeX가 emit하는 모든 tag 커버?
- `text.includes("$")` false positive — price `$5.00` 같은 경우 (단 v2_ko prompt가 수식만 `$` 사용, 안전)
- marked가 inline code (backtick) 안 `$` 처리?
- KaTeX 폰트 로딩 중 viewer block height 깜빡임 (FOUT)?
