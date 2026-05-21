"use strict";

/** Thin fetch wrapper for the ht_lens REST API. Same-origin only. */

export class ApiError extends Error {
  constructor(status, body) {
    super(`${status}: ${body}`);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

/** GET ``path`` and return parsed JSON, or throw :class:`ApiError`. */
export async function apiGet(path) {
  const resp = await fetch(path, {
    headers: { Accept: "application/json" },
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new ApiError(resp.status, text);
  }
  return resp.json();
}
