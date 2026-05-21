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

async function _fetch(method, path, body) {
  const init = {
    method,
    headers: { Accept: "application/json" },
  };
  if (body !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }
  const resp = await fetch(path, init);
  if (!resp.ok) {
    const text = await resp.text();
    throw new ApiError(resp.status, text);
  }
  if (resp.status === 204) return null;
  return resp.json();
}

/** GET ``path`` and return parsed JSON, or throw :class:`ApiError`. */
export function apiGet(path) {
  return _fetch("GET", path);
}

export function apiPost(path, body) {
  return _fetch("POST", path, body || {});
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
