"use strict";

/** Thin fetch wrappers for the ht_lens REST API. Same-origin only. */

export class ApiError extends Error {
  constructor(status, body) {
    super(`${status}: ${body}`);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

async function _fetch(method, path, body, opts = {}) {
  const init = {
    method,
    headers: { Accept: "application/json" },
  };
  if (body !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }
  if (opts.signal) init.signal = opts.signal;
  const resp = await fetch(path, init);
  if (!resp.ok) {
    const text = await resp.text();
    throw new ApiError(resp.status, text);
  }
  if (resp.status === 204) return null;
  return resp.json();
}

/** GET ``path`` and return parsed JSON, or throw :class:`ApiError`.
 *  Phase 6b: accepts ``{signal}`` so stage_container can cancel an in-flight
 *  page fetch via AbortController when the page goes off-screen. */
export function apiGet(path, opts = {}) {
  return _fetch("GET", path, undefined, opts);
}

export function apiPost(path, body, opts = {}) {
  return _fetch("POST", path, body || {}, opts);
}

// -- Phase 6b: lightweight per-page metadata for the natural-scroll viewer --

export function getPagesSummary(docId) {
  return apiGet(`/documents/${encodeURIComponent(docId)}/pages-summary`);
}

// -- Phase 5: thread + message helpers (consumed by chat_panel + viewer) --

export function listThreadsForDoc(docId) {
  return apiGet(`/threads?doc_id=${encodeURIComponent(docId)}`);
}

export function createThread(blockId, title) {
  const body = { block_id: blockId };
  if (title) body.title = title;
  return apiPost("/threads", body);
}

export function getThreadDetail(threadId) {
  return apiGet(`/threads/${encodeURIComponent(threadId)}`);
}

export function explainThread(threadId) {
  return apiPost(`/threads/${encodeURIComponent(threadId)}/explain`);
}

export function postMessage(threadId, content) {
  return apiPost(`/threads/${encodeURIComponent(threadId)}/messages`, {
    content,
  });
}

// -- Phase 6a: search / export / retranslate --

export function searchAll(q, { docId = null, limit = 50 } = {}) {
  const params = new URLSearchParams({ q, limit: String(limit) });
  if (docId !== null && docId !== undefined) {
    params.set("doc_id", String(docId));
  }
  return apiGet(`/search?${params.toString()}`);
}

/** Download the export markdown via fetch + Blob so we can surface server
 *  errors as a toast instead of a silent broken anchor click. */
export async function exportQuestions(docId) {
  const resp = await fetch(`/documents/${encodeURIComponent(docId)}/export.md`);
  if (!resp.ok) {
    const text = await resp.text();
    throw new ApiError(resp.status, text);
  }
  const blob = await resp.blob();
  const filename = `ht_lens-${docId}-questions.md`;
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
  return filename;
}

export function retranslateBlock(blockId) {
  return apiPost(`/blocks/${encodeURIComponent(blockId)}/retranslate`);
}

// -- Phase 6d: uploads / jobs / summarize --

/** Multipart POST /uploads. Returns ``{job_id, document_id, dedup}``.
 *  Surfaces server errors as ``ApiError`` so the upload UI can show a toast. */
export async function uploadPDF(file) {
  const form = new FormData();
  form.append("file", file, file.name);
  const resp = await fetch("/uploads", { method: "POST", body: form });
  if (!resp.ok) {
    const text = await resp.text();
    throw new ApiError(resp.status, text);
  }
  return resp.json();
}

/** ``opts.includeRecentTerminals=true`` (Phase 6d Planner-directed R2 fix)
 *  layers on top of ``status=active`` and ALSO surfaces ``failed`` / ``done``
 *  jobs whose ``finished_at`` is within the last 5 minutes. The frontend
 *  uses this so the panel can show a job that just failed instead of
 *  silently hiding it. */
export function listJobs(statusFilter, opts = {}) {
  const params = new URLSearchParams();
  if (statusFilter) params.set("status", statusFilter);
  if (opts.includeRecentTerminals) {
    params.set("include_recent_terminals", "true");
  }
  const qs = params.toString();
  return apiGet(`/jobs${qs ? `?${qs}` : ""}`);
}

export function getJob(jobId) {
  return apiGet(`/jobs/${encodeURIComponent(jobId)}`);
}

export function summarizeDocument(docId) {
  return apiPost(`/documents/${encodeURIComponent(docId)}/summarize`);
}
