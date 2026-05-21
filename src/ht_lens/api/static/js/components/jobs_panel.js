"use strict";

import { listJobs } from "../api.js";

/** Active-jobs polling panel — Phase 6d.
 *
 *  Polls ``GET /jobs?status=active`` every 2 s, renders a progress bar
 *  per job into ``opts.mount``, and stops polling when no active jobs
 *  remain (the upload pipeline reached ``done`` or ``failed``).
 *
 *  Honors ``document.visibilityState`` — when the tab is hidden the
 *  interval is cleared so a backgrounded tab doesn't keep hammering
 *  the server.
 *
 *  Idempotent: calling ``startJobsPolling`` while it's already running
 *  is a no-op. The module keeps a single timer + mount reference.
 */

const POLL_MS = 2000;
const TERMINAL = new Set(["done", "failed"]);
let _timer = null;
let _mount = null;
let _onAllDone = null;
let _previouslyActive = new Set();

function clearTimer() {
  if (_timer) {
    clearInterval(_timer);
    _timer = null;
  }
}

function renderEmpty() {
  if (!_mount) return;
  _mount.hidden = true;
  _mount.innerHTML = "";
}

function renderJobs(jobs) {
  if (!_mount) return;
  if (jobs.length === 0) {
    renderEmpty();
    return;
  }
  _mount.hidden = false;
  _mount.innerHTML = "";
  const header = document.createElement("div");
  header.className = "active-jobs-header";
  header.textContent = `진행 중인 작업 (${jobs.length})`;
  _mount.appendChild(header);
  for (const job of jobs) {
    _mount.appendChild(renderOne(job));
  }
}

function renderOne(job) {
  const row = document.createElement("div");
  row.className = "job-row";
  row.dataset.jobId = String(job.id);

  const head = document.createElement("div");
  head.className = "job-head";
  const name = document.createElement("span");
  name.className = "job-filename";
  name.textContent = job.upload_filename || `job #${job.id}`;
  const stat = document.createElement("span");
  stat.className = "job-status";
  stat.textContent = job.status;
  head.appendChild(name);
  head.appendChild(stat);
  row.appendChild(head);

  const bar = document.createElement("div");
  bar.className = "job-progress";
  const fill = document.createElement("div");
  fill.className = "job-progress-fill";
  fill.style.width = `${Math.max(0, Math.min(100, job.progress_pct || 0))}%`;
  bar.appendChild(fill);
  row.appendChild(bar);

  if (job.progress_message) {
    const msg = document.createElement("div");
    msg.className = "job-message";
    msg.textContent = job.progress_message;
    row.appendChild(msg);
  }
  if (job.error_message) {
    const err = document.createElement("div");
    err.className = "job-error";
    err.textContent = job.error_message;
    row.appendChild(err);
  }
  return row;
}

async function poll() {
  try {
    const active = await listJobs("active");
    if (!Array.isArray(active)) return;
    renderJobs(active);
    const currentActive = new Set(active.map((j) => j.id));
    const transitioned = [..._previouslyActive].filter(
      (id) => !currentActive.has(id),
    );
    _previouslyActive = currentActive;
    if (active.length === 0) {
      stopJobsPolling();
      if (transitioned.length > 0 && typeof _onAllDone === "function") {
        try {
          await _onAllDone();
        } catch (err) {
          console.warn("onAllDone callback failed", err);
        }
      }
    }
  } catch (err) {
    console.warn("jobs poll failed", err);
  }
}

export function startJobsPolling(opts = {}) {
  const { mount = null, onAllDone = null } = opts;
  if (mount && mount !== _mount) _mount = mount;
  if (onAllDone) _onAllDone = onAllDone;
  if (_timer) return; // already running
  // First poll runs immediately so the panel populates without a 2-second gap.
  poll();
  _timer = setInterval(() => {
    if (document.visibilityState === "hidden") return; // pause while backgrounded
    poll();
  }, POLL_MS);
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") poll();
  });
}

export function stopJobsPolling() {
  clearTimer();
}

export const _TERMINAL_STATES = TERMINAL;
