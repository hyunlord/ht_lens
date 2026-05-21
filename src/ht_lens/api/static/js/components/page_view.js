"use strict";

import { renderBlock } from "./block.js";

/** Render a page into ``container``.
 *
 *  Phase 6b: the function now optionally renders only one side (original or
 *  translation) so a parent ``pane`` can host two of them side-by-side for
 *  the comparison view. Default behavior (no ``side``) is unchanged for
 *  Phase 4/5 callers — ``overlayMode`` controls which text the overlay shows.
 *
 *  ``threadsByBlock`` is an optional Map<blockId, Thread[]> used to render
 *  pin markers on blocks that already have at least one thread (Phase 5).
 */
export function renderPageView(
  container,
  doc,
  page,
  overlayMode,
  zoom,
  threadsByBlock = null,
  options = {},
) {
  container.innerHTML = "";
  const side = options.side || null; // "original" | "translation" | null
  // When ``side`` is set the overlay always shows that side's text. This is
  // what the side-by-side ``both`` mode uses.
  const effectiveOverlayMode = side || overlayMode;

  const wrap = document.createElement("div");
  wrap.className = "stage-wrap";
  if (side) wrap.dataset.side = side;
  const stage = document.createElement("div");
  stage.className = "stage";
  stage.style.setProperty("--stage-zoom", String(zoom));
  const pixelW = page.render.pixel_w;
  const pixelH = page.render.pixel_h;
  stage.style.width = `${pixelW}px`;
  stage.style.height = `${pixelH}px`;

  const img = document.createElement("img");
  img.className = "page-bg";
  img.alt = `page ${page.page_num}`;
  img.width = pixelW;
  img.height = pixelH;
  img.src = `/documents/${doc.id}/pages/${page.page_num}/image`;
  // Lazy-load image when far below the viewport — the page placeholder still
  // claims height via the stage div, so this only delays bitmap decode.
  img.loading = "lazy";
  img.decoding = "async";
  stage.appendChild(img);

  if (page.rotation && page.rotation !== 0) {
    const banner = document.createElement("div");
    banner.className = "rotation-banner";
    banner.textContent = `회전 페이지 (rotation=${page.rotation}°) — 텍스트 오버레이 미지원 (Phase 6c 예정)`;
    stage.appendChild(banner);
  } else {
    const overlay = document.createElement("div");
    overlay.className = "overlay";
    overlay.dataset.mode = effectiveOverlayMode;
    if (side) overlay.dataset.side = side;
    overlay.style.width = `${pixelW}px`;
    overlay.style.height = `${pixelH}px`;
    const scale = {
      x: pixelW / page.width,
      y: pixelH / page.height,
      pageW: page.width,
      pageH: page.height,
    };
    for (const block of page.blocks) {
      const threads = threadsByBlock?.get?.(block.id) || [];
      renderBlock(overlay, block, scale, effectiveOverlayMode, threads);
    }
    stage.appendChild(overlay);
  }

  wrap.appendChild(stage);
  container.appendChild(wrap);

  // Container sizing: the .stage transform is purely visual; we need to
  // reserve scrollable space for the zoomed stage as well.
  wrap.style.width = `${pixelW * zoom}px`;
  wrap.style.height = `${pixelH * zoom}px`;
}
