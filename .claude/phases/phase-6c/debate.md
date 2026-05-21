## 1. Over-engineering

- The `.env` fix in `.claude/phases/phase-6c/plan.md` is spread across `src/ht_lens/cli.py`, `scripts/dev_serve.sh`, a new direct `python-dotenv` dependency, and Linux-specific `/proc/PID/environ` verification. `ROADMAP.md` Phase 6c only requires “`.env`가 `ht-lens serve` 진입 시 자동 반영.” Duplicating load paths is scope creep and guarantees drift.

- The fit-to-width proposal adds `src/ht_lens/api/static/js/utils/viewport.js`, new zoom APIs in `state.js`, special persistence rules, and hooks in `viewer.js` for load, resize, sidebar toggle, and view-mode changes. The roadmap DoD only says “새 페이지 진입 시 자동으로 viewport 폭 fit.” Auto-refit on every layout change is extra behavior that should be deferred.

- The natural-scroll fix changes too many variables at once in `src/ht_lens/api/static/js/components/stage_container.js`: `rootMargin`, active-page selection logic, and possibly a `scroll` listener. For a 6c bug-fix phase, this is too invasive. Reproduce the exact failure first, then make the smallest change that fixes it.

## 2. Hidden assumptions

- The plan assumes `src/ht_lens/cli.py` is the only relevant entrypoint. It is not. `src/ht_lens/api/app.py:create_app()` is used directly by tests (`tests/integration/_api_helpers.py`) and can be launched by uvicorn without going through the CLI. If that path matters, the proposed fix does not satisfy the Phase 6c env DoD.

- The fit logic assumes arbitrary zoom values are compatible with the current state model. They are not. `src/ht_lens/api/static/js/state.js` enforces `ZOOM_STEPS`, but the plan’s own example expects `computeFitZoom(...)=~0.69`. If the value is snapped to `0.75`, “fit-to-width” becomes approximate and can still overflow.

- The verification plan assumes Linux process inspection is stable evidence. It is brittle. `.claude/phases/phase-6c/plan.md` mentions both `pgrep ht_lens.api` and `pgrep ht-lens`, but `scripts/dev_serve.sh` runs `uv run ht-lens serve`, so the process name is not guaranteed. `/proc/PID/environ` also makes the proof Linux-only.

- The shell fallback assumes `source "$REPO_ROOT/.env"` is equivalent to `python-dotenv`. It is not. Bash sourcing has different parsing rules and can execute shell syntax. A `.env` file that `python-dotenv` accepts can still break `scripts/dev_serve.sh`.

## 3. Edge cases

- Deep links to later pages are at risk. `viewer.js:loadDocument()` currently builds placeholder rows and calls `scrollToPage()` before the plan’s auto-fit hook. If zoom changes after scrolling, placeholder heights change and the target page or `block` highlight can shift.

- `both` mode plus open chat panel is underspecified. `state.js` forces `viewModeActual` from `"both"` to `"translation"` when the panel is open. If fit calculation keys off `viewMode` instead of `viewModeActual`, the wrong pane count is used and the auto-fit DoD fails in the normal chat flow.

- The sidebar toggle can be unstable during scroll-driven rerenders. `renderSidebar()` wipes `aside.sidebar` on every repaint, and `setCurrentPage()` fires repeatedly from `attachIntersectionObserver()`. A toggle button rendered inside the sidebar can lose listeners or re-mount unexpectedly.

- The CWD-vs-repo-root `.env` policy is a trap. The plan loads both in `cli.py` with `override=False`, so the first file silently wins. Running `ht-lens serve` from a document folder with its own `.env` can switch LLM provider unexpectedly.

## 4. Alternative approaches

- Load `.env` where the value is consumed, not at the CLI wrapper. `src/ht_lens/api/app.py` before `from_env()` or `src/ht_lens/llm/factory.py` is the right level. That covers `ht-lens serve`, `create_app()` in tests, and direct uvicorn entry without shell hacks.

- Use a `ResizeObserver` on `#stage` or `.viewer-shell` for fit-to-width instead of manual hooks for resize, sidebar toggle, and view-mode changes. The real signal is container-width change. That is simpler and less fragile than wiring multiple events through `viewer.js`.

- Keep the sidebar toggle outside `renderSidebar()` in `src/ht_lens/api/static/viewer.html` or another stable top-level mount. `renderSidebar()` is intentionally disposable; a global layout control should not live inside a subtree that is recreated on every page-state update.

## 5. Missing tests

- Add `test_create_app_reads_dotenv_without_cli_import`. The proposed `tests/integration/test_dotenv_load.py` only proves `import ht_lens.cli` mutates `os.environ`; it does not prove the real `create_app()` path satisfies the Phase 6c env DoD.

- Add `test_auto_fit_preserves_deep_link_target_page`. Nothing in the plan tests the interaction between placeholder-row resizing and `scrollToPage()` for `viewer.html?doc=...&page=6&block=...`.

- Add `test_auto_fit_uses_view_mode_actual_when_panel_open`. Grepping for `computeFitZoom` and `setZoomAutoFit` in `tests/integration/test_static_serving.py` is not enough; this needs a jsdom/runtime assertion against `state.viewModeActual`.

- Add `test_sidebar_toggle_survives_sidebar_rerender_on_current_page_change`. This is the most likely failure mode because `repaintSidebar()` runs whenever `setCurrentPage()` fires.

- Add `test_attach_intersection_observer_mounts_last_page_on_fast_scroll`. The planned “mountPage called 6 times” jsdom check does not exercise the real `IntersectionObserver` callback path that currently decides whether the next page mounts at all.
