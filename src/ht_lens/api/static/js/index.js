"use strict";

import { apiGet } from "./api.js";

const grid = document.querySelector(".doc-card-grid");
const statusEl = document.getElementById("status");

function setStatus(msg, kind) {
  if (!statusEl) return;
  statusEl.textContent = msg;
  statusEl.hidden = !msg;
  statusEl.classList.remove("error", "empty");
  if (kind) statusEl.classList.add(kind);
}

function formatDate(iso) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toISOString().slice(0, 10);
  } catch (_e) {
    return iso;
  }
}

const STATUS_LABELS = {
  ready_for_translation: { label: "번역 대기", cls: "status--pending" },
  translating: { label: "번역 중", cls: "status--running" },
  translated: { label: "번역 완료", cls: "status--ok" },
  partial_translated: { label: "부분 번역", cls: "status--partial" },
  failed: { label: "실패", cls: "status--failed" },
};

function statusTag(rawStatus) {
  const meta = STATUS_LABELS[rawStatus] || { label: rawStatus, cls: "" };
  const s = document.createElement("span");
  s.className = `tag status-tag ${meta.cls}`.trim();
  s.textContent = meta.label;
  s.title = rawStatus; // raw value still accessible on hover for debugging
  return s;
}

function renderCard(doc) {
  const a = document.createElement("a");
  a.className = "doc-card";
  a.href = `viewer.html?doc=${doc.id}&page=1`;
  const filename = document.createElement("div");
  filename.className = "filename";
  filename.textContent = doc.filename;
  const meta = document.createElement("div");
  meta.className = "meta";
  const tag = (text) => {
    const s = document.createElement("span");
    s.className = "tag";
    s.textContent = text;
    return s;
  };
  meta.appendChild(tag(`${doc.src_lang} → ${doc.tgt_lang}`));
  meta.appendChild(tag(`${doc.num_pages} pages`));
  meta.appendChild(statusTag(doc.status));
  const created = document.createElement("span");
  created.textContent = formatDate(doc.created_at);
  meta.appendChild(created);
  a.appendChild(filename);
  a.appendChild(meta);
  return a;
}

async function main() {
  try {
    setStatus("loading…");
    const docs = await apiGet("/documents");
    if (!Array.isArray(docs) || docs.length === 0) {
      // "no documents" empty state.
      setStatus(
        "no documents yet — run `ht-lens extract` + `ht-lens ingest` first",
        "empty",
      );
      return;
    }
    setStatus("");
    for (const doc of docs) {
      grid.appendChild(renderCard(doc));
    }
  } catch (err) {
    setStatus(`error loading documents: ${err.message}`, "error");
    console.error(err);
  }
}

main();
