"use strict";

/** Font-fitting helpers.
 *
 * ``fitFontSize`` picks the largest font size (within ``[MIN_SIZE, MAX_SIZE]``)
 * for which the wrapped text fits inside the given bbox. Wrapping is simulated
 * by ``wrapTextByWidth`` which uses :meth:`CanvasRenderingContext2D.measureText`
 * when available; otherwise (e.g. Node) it falls back to ``estimateCharWidth``.
 */

export const MIN_SIZE = 6;
export const MAX_SIZE = 32;
const LINE_HEIGHT_RATIO = 1.15;
const FONT_STACK =
  "'Noto Sans KR', 'Inter', -apple-system, BlinkMacSystemFont, system-ui, sans-serif";

/** Approximate the rendered width of a single character (in px) at ``size``.
 *  CJK ≈ 1.0×size, ASCII ≈ 0.55×size. Used as a Node-friendly fallback. */
export function estimateCharWidth(ch, size) {
  const code = ch.charCodeAt(0);
  // CJK ranges (rough): Hangul, Hangul Jamo, CJK Unified, Hiragana, Katakana.
  const isCjk =
    (code >= 0xac00 && code <= 0xd7af) ||
    (code >= 0x1100 && code <= 0x11ff) ||
    (code >= 0x4e00 && code <= 0x9fff) ||
    (code >= 0x3040 && code <= 0x309f) ||
    (code >= 0x30a0 && code <= 0x30ff);
  return size * (isCjk ? 1.0 : 0.55);
}

function makeMeasurer(size, weight) {
  if (typeof document !== "undefined" && document.createElement) {
    try {
      const cv = document.createElement("canvas");
      const ctx = cv.getContext("2d");
      if (ctx) {
        ctx.font = `${weight} ${size}px ${FONT_STACK}`;
        return (s) => ctx.measureText(s).width;
      }
    } catch (_e) {
      /* fall through to estimator */
    }
  }
  // Fallback: sum estimated per-char widths.
  return (s) => {
    let total = 0;
    for (const ch of s) total += estimateCharWidth(ch, size);
    return total;
  };
}

/** Greedy word-aware wrap: returns array of line strings that all fit
 *  within ``maxW``. Handles CJK by breaking per-character when needed. */
export function wrapTextByWidth(text, maxW, measure) {
  const lines = [];
  for (const paragraph of text.split(/\n/)) {
    if (paragraph === "") {
      lines.push("");
      continue;
    }
    // Treat each whitespace-separated chunk as a word; CJK chunks can be
    // broken character-by-character when even one word does not fit.
    const tokens = paragraph.split(/(\s+)/);
    let line = "";
    for (const tok of tokens) {
      if (tok === "") continue;
      const candidate = line + tok;
      if (measure(candidate) <= maxW || line === "") {
        if (measure(candidate) <= maxW) {
          line = candidate;
        } else {
          // Single token longer than maxW — break per char.
          for (const ch of tok) {
            const tryLine = line + ch;
            if (measure(tryLine) <= maxW || line === "") {
              line = tryLine;
            } else {
              lines.push(line);
              line = ch;
            }
          }
        }
      } else {
        lines.push(line.trimEnd());
        line = /^\s+$/.test(tok) ? "" : tok;
      }
    }
    if (line !== "") lines.push(line.trimEnd());
  }
  return lines;
}

/** Return ``true`` if the text wrapped at ``size`` fits within bbox. */
export function fits(size, text, bboxW, bboxH, weight = "normal") {
  if (bboxW <= 0 || bboxH <= 0) return false;
  const measure = makeMeasurer(size, weight);
  const lines = wrapTextByWidth(text, bboxW, measure);
  const totalH = lines.length * size * LINE_HEIGHT_RATIO;
  return totalH <= bboxH;
}

/** Binary-search the largest size in ``[MIN_SIZE, MAX_SIZE]`` for which
 *  the text fits. Returns ``MIN_SIZE`` if even that overflows. */
export function fitFontSize(text, bboxW, bboxH, weight = "normal") {
  if (!text || bboxW <= 0 || bboxH <= 0) return MIN_SIZE;
  if (fits(MAX_SIZE, text, bboxW, bboxH, weight)) return MAX_SIZE;
  if (!fits(MIN_SIZE, text, bboxW, bboxH, weight)) return MIN_SIZE;
  let lo = MIN_SIZE;
  let hi = MAX_SIZE;
  // Integer binary search; we want the largest size that fits.
  while (lo + 1 < hi) {
    const mid = Math.floor((lo + hi) / 2);
    if (fits(mid, text, bboxW, bboxH, weight)) lo = mid;
    else hi = mid;
  }
  return lo;
}
