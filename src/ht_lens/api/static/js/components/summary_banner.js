"use strict";

import { summarizeDocument } from "../api.js";

/** Phase 6d viewer summary banner — v0.7 hotfix (collapsible + dismissible).
 *
 *  Mounts above ``#stage`` and shows the document's auto-summary. Three
 *  states tracked via ``data-state`` so CSS can collapse/expand cleanly:
 *
 *    - ``collapsed`` (default on viewer entry): header + one-line preview
 *      (first 200 chars), banner stays ~80px so the page below isn't
 *      pushed off-screen. Toggle ``▼ 더보기`` flips to expanded.
 *    - ``expanded``: full body + max-height 40vh + internal scroll for
 *      long summaries. Toggle becomes ``▲ 접기``.
 *    - ``dismissed`` (sticky per doc, localStorage): mount.hidden=true.
 *      Re-shown only after manual ``POST /summarize`` regeneration.
 *
 *  When ``doc.summary`` is empty (image-only PDF or skipped summarize
 *  stage) we render a compact "요약 생성" panel so the user can trigger
 *  the explicit endpoint.
 *
 *  Dismiss key shape: ``ht_lens.summary.dismissed.${docId}`` so multiple
 *  documents track independently and we don't pollute one big preferences
 *  blob.
 */

const DISMISS_KEY_PREFIX = "ht_lens.summary.dismissed.";
const PREVIEW_CHARS = 200;

function dismissKey(docId) {
  return `${DISMISS_KEY_PREFIX}${docId}`;
}

function isDismissed(docId) {
  try {
    return localStorage.getItem(dismissKey(docId)) === "true";
  } catch (_e) {
    return false;
  }
}

function markDismissed(docId) {
  try {
    localStorage.setItem(dismissKey(docId), "true");
  } catch (_e) {
    /* private mode etc. — fall through, banner just won't persist */
  }
}

function clearDismissed(docId) {
  try {
    localStorage.removeItem(dismissKey(docId));
  } catch (_e) {
    /* noop */
  }
}

function makePreview(text) {
  if (!text) return "";
  const flat = text.replace(/\s+/g, " ").trim();
  if (flat.length <= PREVIEW_CHARS) return flat;
  return flat.slice(0, PREVIEW_CHARS) + "…";
}

export function renderSummaryBanner(mountEl, doc, { onUpdated } = {}) {
  if (!mountEl) return;
  mountEl.innerHTML = "";

  if (!doc) {
    mountEl.hidden = true;
    return;
  }

  // R2 hotfix: dismissed-per-doc sticky preference. The user closed this
  // banner for ``doc.id`` previously → respect it across reloads.
  if (isDismissed(doc.id)) {
    mountEl.hidden = true;
    return;
  }

  mountEl.hidden = false;

  const card = document.createElement("div");
  card.className = "summary-banner";
  // Default collapsed for "summary present" path. Empty-summary path has
  // no preview to collapse, so we treat it as an always-open compact
  // regenerate prompt (data-state stays "collapsed" but expanded body is
  // unused).
  card.dataset.state = "collapsed";

  // --- Header row (title + controls). Always visible. ---
  const header = document.createElement("div");
  header.className = "summary-banner-header";

  const title = document.createElement("span");
  title.className = "summary-banner-title";
  title.textContent = "📋 문서 요약";
  header.appendChild(title);

  const controls = document.createElement("div");
  controls.className = "summary-banner-controls";

  const toggleBtn = document.createElement("button");
  toggleBtn.type = "button";
  toggleBtn.className = "summary-banner-toggle";
  toggleBtn.setAttribute("aria-expanded", "false");
  // No body to expand when there's no summary — hide the toggle in that
  // case and let the user use the regenerate button instead.
  if (!doc.summary) {
    toggleBtn.hidden = true;
  } else {
    toggleBtn.textContent = "▼ 더보기";
  }
  controls.appendChild(toggleBtn);

  const closeBtn = document.createElement("button");
  closeBtn.type = "button";
  closeBtn.className = "summary-banner-close";
  closeBtn.setAttribute("aria-label", "닫기");
  closeBtn.title = "닫기 (이 문서에서 다시 보이지 않음)";
  closeBtn.textContent = "✕";
  controls.appendChild(closeBtn);

  header.appendChild(controls);
  card.appendChild(header);

  // --- Preview line (collapsed view body). ---
  const preview = document.createElement("div");
  preview.className = "summary-banner-preview";
  if (doc.summary) {
    preview.textContent = makePreview(doc.summary);
  } else {
    preview.textContent =
      "이 문서의 자동 요약이 아직 생성되지 않았습니다.";
    preview.classList.add("summary-banner-preview--empty");
  }
  card.appendChild(preview);

  // --- Full body (expanded view body), initially hidden. ---
  const body = document.createElement("p");
  body.className = "summary-banner-body";
  body.hidden = true;
  body.textContent = doc.summary || "";
  card.appendChild(body);

  // --- Actions (regenerate). Visible when expanded OR when summary is empty. ---
  const actions = document.createElement("div");
  actions.className = "summary-banner-actions";
  // Hidden in collapsed state when we have a summary; shown when expanded
  // or whenever the summary is absent (empty-state prompt to generate).
  actions.hidden = Boolean(doc.summary);

  const regenBtn = document.createElement("button");
  regenBtn.type = "button";
  regenBtn.className = "summary-banner-regenerate";
  regenBtn.textContent = doc.summary ? "재생성" : "요약 생성";
  actions.appendChild(regenBtn);
  card.appendChild(actions);

  // --- Event wiring ---

  toggleBtn.addEventListener("click", () => {
    const expanded = card.dataset.state === "expanded";
    if (expanded) {
      card.dataset.state = "collapsed";
      body.hidden = true;
      actions.hidden = Boolean(doc.summary);
      toggleBtn.textContent = "▼ 더보기";
      toggleBtn.setAttribute("aria-expanded", "false");
    } else {
      card.dataset.state = "expanded";
      body.hidden = false;
      actions.hidden = false;
      toggleBtn.textContent = "▲ 접기";
      toggleBtn.setAttribute("aria-expanded", "true");
    }
  });

  closeBtn.addEventListener("click", () => {
    markDismissed(doc.id);
    card.dataset.state = "dismissed";
    mountEl.hidden = true;
    mountEl.innerHTML = "";
  });

  regenBtn.addEventListener("click", async () => {
    regenBtn.disabled = true;
    const originalLabel = regenBtn.textContent;
    regenBtn.textContent = "요약 생성 중...";
    try {
      const updated = await summarizeDocument(doc.id);
      // Manual regenerate clears any prior dismiss so the user can see
      // the new summary they just asked for.
      clearDismissed(doc.id);
      onUpdated?.(updated);
    } catch (err) {
      regenBtn.textContent = `실패: ${err.message}`;
      setTimeout(() => {
        regenBtn.textContent = originalLabel;
        regenBtn.disabled = false;
      }, 3000);
    }
  });

  mountEl.appendChild(card);
}

export const _SUMMARY_DISMISS_KEY_PREFIX = DISMISS_KEY_PREFIX;
export const _SUMMARY_PREVIEW_CHARS = PREVIEW_CHARS;
