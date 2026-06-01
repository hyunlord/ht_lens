"use strict";

// ht_lens 2.0 reflow — inline enrichment (Phase 8d-1).
//
// Wraps academic citations ("[BJ05]") and intra-document section
// references ("28.3.5", only when they name a real heading) inside the
// already-rendered reading text. DOM-only: a TreeWalker collects text
// nodes, each is replaced ONCE by a DocumentFragment (no innerHTML, no
// repeated splitText) so adjacent/multiple matches are safe (debate R8)
// and there is no XSS surface (debate R10).
//
// MUST run AFTER applyMath: any text node under KaTeX output is skipped
// via closest(".katex") so rendered math is never corrupted (debate R5).

// Citation: bracketed token that MUST contain a digit, so language /
// note markers like [KO], [EN], [Note] are never styled (debate R1),
// while [BJ05], [CDS02], [Kha+10], [Hot36] are.
const CITE_RE = /\[[A-Za-z][A-Za-z.'+-]*\d[A-Za-z0-9.'+-]*\]/;
// Dotted number with >= 2 segments (so a bare "28" or integer is ignored).
const SECREF_RE = /\d+(?:\.\d+)+/;
// Combined left-to-right scan; group 1 = citation, group 2 = section ref.
const SCAN_RE = new RegExp(`(${CITE_RE.source})|(${SECREF_RE.source})`, "g");

/** True when a text node sits inside KaTeX output or a code span. */
function inProtectedZone(node) {
  const el = node.parentElement;
  return !!el && el.closest(".katex, .katex-display, pre, code") !== null;
}

/** Build a replacement fragment for one text node, or null if nothing
 *  was wrapped. `sectionNums` gates section refs (membership only —
 *  equation/figure numbers like 28.116 stay plain text, debate R11). */
function enrichTextNode(text, sectionNums) {
  SCAN_RE.lastIndex = 0;
  const frag = document.createDocumentFragment();
  let last = 0;
  let matched = false;
  let m;
  while ((m = SCAN_RE.exec(text)) !== null) {
    const token = m[0];
    const isCite = m[1] !== undefined;
    if (!isCite && !sectionNums.has(token)) continue; // unknown dotted no. → plain
    if (m.index > last) {
      frag.appendChild(document.createTextNode(text.slice(last, m.index)));
    }
    let el;
    if (isCite) {
      el = document.createElement("span");
      el.className = "rf-cite";
    } else {
      el = document.createElement("a");
      el.className = "rf-ref";
      el.dataset.sec = token;
      el.setAttribute("role", "link");
    }
    el.textContent = token;
    frag.appendChild(el);
    last = m.index + token.length;
    matched = true;
  }
  if (!matched) return null;
  if (last < text.length) frag.appendChild(document.createTextNode(text.slice(last)));
  return frag;
}

/** Enrich citations + known section refs inside `el`, in place.
 *  `sectionNums`: Set of valid dotted section numbers (heading originals). */
export function enrichInline(el, sectionNums) {
  if (!el) return;
  const nums = sectionNums || new Set();
  const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
  const targets = [];
  let n;
  while ((n = walker.nextNode()) !== null) {
    const v = n.nodeValue;
    if (!v || !v.trim()) continue;
    if (inProtectedZone(n)) continue;
    if (!CITE_RE.test(v) && !SECREF_RE.test(v)) continue;
    targets.push(n);
  }
  for (const node of targets) {
    const frag = enrichTextNode(node.nodeValue, nums);
    if (frag) node.replaceWith(frag);
  }
}

export { CITE_RE, SECREF_RE };
