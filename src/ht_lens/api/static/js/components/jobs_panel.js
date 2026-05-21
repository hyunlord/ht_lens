"use strict";

import { listJobs } from "../api.js";

/** Active-jobs polling panel — Phase 6d (Planner-directed R2 fix).
 *
 *  Polls ``GET /jobs?status=active&include_recent_terminals=true`` every
 *  2 s and renders a progress bar per job into ``opts.mount``. Honors
 *  ``document.visibilityState`` — when the tab is hidden the interval
 *  is cleared so a backgrounded tab doesn't keep hammering the server.
 *
 *  R2 fix: terminal-state jobs (``failed`` and ``done``) within the
 *  recent-window stay visible until the user clicks dismiss, so a
 *  failed extract / translate / summarize stage doesn't silently
 *  vanish from the UI. Active jobs (in the pending→summarizing band)
 *  drive the poll loop; once both queues are empty + dismissed the
 *  panel hides and the docs grid refetches.
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
// R2 fix: terminal job ids the user explicitly dismissed. Suppressed
// from future renders so the panel can finally hide once the active
// queue drains.
let _dismissedTerminals = new Set();
let _refetchOnce = false;

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
  const activeCount = jobs.filter((j) => !TERMINAL.has(j.status)).length;
  const failedCount = jobs.filter((j) => j.status === "failed").length;
  let label = `진행 중인 작업 (${activeCount})`;
  if (failedCount > 0) label += ` · 실패 ${failedCount}`;
  header.textContent = label;
  _mount.appendChild(header);
  for (const job of jobs) {
    _mount.appendChild(renderOne(job));
  }
}

function renderOne(job) {
  const row = document.createElement("div");
  row.className = "job-row";
  if (job.status === "failed") row.classList.add("job-row--failed");
  if (job.status === "done") row.classList.add("job-row--done");
  row.dataset.jobId = String(job.id);
  row.dataset.status = job.status;

  const head = document.createElement("div");
  head.className = "job-head";
  const name = document.createElement("span");
  name.className = "job-filename";
  const prefix = job.status === "failed" ? "❌ 실패: " : "";
  name.textContent = prefix + (job.upload_filename || `job #${job.id}`);
  const stat = document.createElement("span");
  stat.className = "job-status";
  stat.textContent = job.status;
  head.appendChild(name);
  head.appendChild(stat);

  // R2 fix: terminal rows get a dismiss button so the user can clear
  // them once they've read the error_message. Active rows do not.
  if (TERMINAL.has(job.status)) {
    const dismiss = document.createElement("button");
    dismiss.type = "button";
    dismiss.className = "job-dismiss";
    dismiss.textContent = "✕";
    dismiss.title = "닫기";
    dismiss.addEventListener("click", () => {
      _dismissedTerminals.add(job.id);
      // Re-render immediately so the user sees the row disappear.
      poll();
    });
    head.appendChild(dismiss);
  }
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
    const rows = await listJobs("active", { includeRecentTerminals: true });
    if (!Array.isArray(rows)) return;
    // Drop user-dismissed terminals.
    const visible = rows.filter((j) => !_dismissedTerminals.has(j.id));
    renderJobs(visible);
    const activeNow = visible.filter((j) => !TERMINAL.has(j.status));
    const activeIds = new Set(activeNow.map((j) => j.id));
    const transitioned = [..._previouslyActive].filter(
      (id) => !activeIds.has(id),
    );
    _previouslyActive = activeIds;
    if (transitioned.length > 0 && !_refetchOnce) {
      // At least one active job just reached a terminal state — refresh
      // the docs grid so a newly-done upload shows up as a card. We do
      // this once per "wave" so dismissing rows doesn't trigger repeated
      // refetches.
      _refetchOnce = true;
      if (typeof _onAllDone === "function") {
        try {
          await _onAllDone();
        } catch (err) {
          console.warn("onAllDone callback failed", err);
        }
      }
    }
    if (activeNow.length === 0 && visible.length === 0) {
      // Both queues drained; stop the timer but leave the dismiss
      // tracking in place so the next start-cycle stays clean.
      stopJobsPolling();
      _refetchOnce = false;
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
  _refetchOnce = false;
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
