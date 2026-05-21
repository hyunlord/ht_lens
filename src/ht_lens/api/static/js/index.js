"use strict";

import { apiGet } from "./api.js";
import { attachUpload } from "./components/upload.js";
import { startJobsPolling } from "./components/jobs_panel.js";

const grid = document.getElementById("doc-grid");
const statusEl = document.getElementById("status");
const uploadZone = document.getElementById("upload-zone");
const uploadButton = document.getElementById("upload-button");
const uploadInput = document.getElementById("upload-input");
const activeJobsEl = document.getElementById("active-jobs");

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
  s.title = rawStatus;
  return s;
}

function summaryPreview(text) {
  if (!text) return null;
  const p = document.createElement("p");
  p.className = "summary-preview";
  const trimmed = text.length > 120 ? text.slice(0, 120) + "…" : text;
  p.textContent = trimmed;
  return p;
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
  // Phase 6d: optional summary preview (120 char cap).
  const preview = summaryPreview(doc.summary);
  if (preview) a.appendChild(preview);
  return a;
}

async function refetchDocs() {
  if (!grid) return;
  try {
    const docs = await apiGet("/documents");
    grid.innerHTML = "";
    if (!Array.isArray(docs) || docs.length === 0) {
      setStatus(
        "no documents yet — drop a PDF above to get started",
        "empty",
      );
      return;
    }
    setStatus("");
    for (const doc of docs) grid.appendChild(renderCard(doc));
  } catch (err) {
    setStatus(`error loading documents: ${err.message}`, "error");
    console.error(err);
  }
}

async function main() {
  setStatus("loading…");
  await refetchDocs();

  // Phase 6d: upload zone + active-jobs panel wiring.
  if (uploadZone && uploadButton && uploadInput) {
    attachUpload({
      zone: uploadZone,
      button: uploadButton,
      input: uploadInput,
      onUploaded: ({ jobId, documentId, dedup, filename }) => {
        if (dedup && documentId) {
          setStatus(
            `이미 업로드된 문서입니다: ${filename} → viewer로 이동`,
            "info",
          );
          window.setTimeout(() => {
            window.location.href = `viewer.html?doc=${documentId}&page=1`;
          }, 800);
          return;
        }
        if (jobId) {
          setStatus(`업로드 수락됨: ${filename} (job #${jobId})`, "info");
          startJobsPolling({ mount: activeJobsEl, onAllDone: refetchDocs });
        }
      },
      onError: (msg) => setStatus(`업로드 실패: ${msg}`, "error"),
    });
  }
  // Resume polling if an active job already exists (e.g. page reload mid-job).
  startJobsPolling({ mount: activeJobsEl, onAllDone: refetchDocs });
}

main();
