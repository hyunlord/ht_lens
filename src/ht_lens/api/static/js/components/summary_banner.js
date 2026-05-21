"use strict";

import { summarizeDocument } from "../api.js";

/** Phase 6d viewer summary banner.
 *
 *  Mounts above ``#stage`` and shows the document's auto-summary.
 *  When ``summary`` is empty (image-only PDF, or upload pipeline
 *  skipped this stage with an error_message) the banner shows a
 *  "재생성" button that calls ``POST /documents/{id}/summarize``.
 */
export function renderSummaryBanner(mount, doc, { onUpdated } = {}) {
  if (!mount) return;
  mount.innerHTML = "";
  if (!doc) {
    mount.hidden = true;
    return;
  }
  mount.hidden = false;
  const card = document.createElement("div");
  card.className = "summary-banner";

  const title = document.createElement("div");
  title.className = "summary-banner-title";
  title.textContent = "문서 요약";
  card.appendChild(title);

  if (doc.summary) {
    const body = document.createElement("p");
    body.className = "summary-banner-body";
    body.textContent = doc.summary;
    card.appendChild(body);
  } else {
    const empty = document.createElement("p");
    empty.className = "summary-banner-empty";
    empty.textContent =
      "이 문서의 자동 요약이 아직 생성되지 않았습니다. 재생성 버튼을 누르세요.";
    card.appendChild(empty);
  }

  const actions = document.createElement("div");
  actions.className = "summary-banner-actions";
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "summary-banner-btn";
  btn.textContent = doc.summary ? "재생성" : "요약 생성";
  btn.addEventListener("click", async () => {
    btn.disabled = true;
    btn.textContent = "요약 생성 중...";
    try {
      const updated = await summarizeDocument(doc.id);
      onUpdated?.(updated);
    } catch (err) {
      btn.textContent = `실패: ${err.message}`;
      setTimeout(() => {
        btn.textContent = doc.summary ? "재생성" : "요약 생성";
        btn.disabled = false;
      }, 3000);
    }
  });
  actions.appendChild(btn);
  card.appendChild(actions);

  mount.appendChild(card);
}
