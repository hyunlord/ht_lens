"use strict";

/** Phase 6c — viewport fit helpers.
 *
 *  ``computeFitZoom`` returns the largest ``ZOOM_STEPS`` value that keeps a
 *  page (or two side-by-side panes) within the stage container's available
 *  horizontal space. We pick the largest step ``<=`` the target so the
 *  result NEVER overflows (snap-down, not snap-nearest — debate §2 fix).
 *
 *  Inputs:
 *  - pageWidthPt: page width in PDF points (typically 612)
 *  - stageWidthPx: stage-container clientWidth in CSS px
 *  - scale: render scale (pixel_w / pageWidthPt; typically 2.78 at 200dpi)
 *  - viewMode: 'translation' | 'original' | 'both' — drives paneCount
 *
 *  The function uses ``viewModeActual`` semantics: when the chat panel is
 *  open and ``state.viewMode === 'both'``, ``state.viewModeActual`` is
 *  ``'translation'`` and only one pane is mounted, so callers must pass
 *  ``viewModeActual`` to get the correct pane count.
 */

export const ZOOM_STEPS = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0];

// Layout margins inside the stage container — must stay in sync with
// viewer.css (.stage-container padding + .page-row gap between panes).
const STAGE_PADDING_PX = 32;
const PANE_GAP_PX = 16;

export function computeFitZoom({
  pageWidthPt,
  stageWidthPx,
  scale,
  viewMode,
}) {
  if (!Number.isFinite(pageWidthPt) || pageWidthPt <= 0) return 1.0;
  if (!Number.isFinite(stageWidthPx) || stageWidthPx <= 0) return 1.0;
  if (!Number.isFinite(scale) || scale <= 0) return 1.0;
  const paneCount = viewMode === "both" ? 2 : 1;
  const naturalPx = pageWidthPt * scale * paneCount;
  const margin = STAGE_PADDING_PX + (paneCount - 1) * PANE_GAP_PX;
  const target = (stageWidthPx - margin) / naturalPx;
  // Snap DOWN to the largest step <= target. If target < smallest step,
  // return the smallest step (overflow accepted on tiny viewports).
  let pick = ZOOM_STEPS[0];
  for (const step of ZOOM_STEPS) {
    if (step <= target) pick = step;
  }
  return pick;
}
