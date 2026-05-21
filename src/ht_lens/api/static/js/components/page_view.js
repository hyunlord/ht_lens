"use strict";

import { renderBlock } from "./block.js";

/** Render a page into ``container``. Uses ``page.render.pixel_w`` /
 *  ``pixel_h`` as the stage's intrinsic coordinate space — block bboxes
 *  (PDF points) are scaled into that pixel space once, and zoom is applied
 *  via CSS transform on ``.stage``. */
export function renderPageView(container, doc, page, overlayMode, zoom) {
  container.innerHTML = "";

  const wrap = document.createElement("div");
  wrap.className = "stage-wrap";
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
  stage.appendChild(img);

  if (page.rotation && page.rotation !== 0) {
    const banner = document.createElement("div");
    banner.className = "rotation-banner";
    banner.textContent =
      `회전 페이지 (rotation=${page.rotation}°) — 텍스트 오버레이 미지원 (Phase 6 예정)`;
    stage.appendChild(banner);
  } else {
    const overlay = document.createElement("div");
    overlay.className = "overlay";
    overlay.dataset.mode = overlayMode;
    overlay.style.width = `${pixelW}px`;
    overlay.style.height = `${pixelH}px`;
    const scale = {
      x: pixelW / page.width,
      y: pixelH / page.height,
      pageW: page.width,
      pageH: page.height,
    };
    for (const block of page.blocks) {
      renderBlock(overlay, block, scale, overlayMode);
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
