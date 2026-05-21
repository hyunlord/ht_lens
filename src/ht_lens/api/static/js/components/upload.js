"use strict";

import { uploadPDF } from "../api.js";

/** Wire up the PDF drop zone and file-select button.
 *
 *  ``opts``:
 *    - ``zone`` (HTMLElement): the drag target (gets ``upload-zone--drag``)
 *    - ``button`` (HTMLElement): the "파일 선택" button
 *    - ``input`` (HTMLInputElement): the hidden ``<input type=file>``
 *    - ``onUploaded({jobId, documentId, dedup, filename})``
 *    - ``onError(message)``
 */
export function attachUpload(opts) {
  const { zone, button, input, onUploaded, onError } = opts;

  async function handleFile(file) {
    if (!file) return;
    if (!/\.pdf$/i.test(file.name) && file.type !== "application/pdf") {
      onError?.("PDF 파일만 업로드 가능합니다");
      return;
    }
    try {
      const resp = await uploadPDF(file);
      onUploaded?.({
        jobId: resp.job_id,
        documentId: resp.document_id,
        dedup: resp.dedup,
        filename: file.name,
      });
    } catch (err) {
      onError?.(err.message || String(err));
    }
  }

  button.addEventListener("click", () => input.click());
  input.addEventListener("change", () => {
    const file = input.files?.[0];
    if (file) handleFile(file);
    input.value = "";
  });

  // Drag-and-drop on the zone. Listening on zone itself (not document)
  // keeps the dragover class scoped to the drop target.
  zone.addEventListener("dragenter", (e) => {
    e.preventDefault();
    zone.classList.add("upload-zone--drag");
  });
  zone.addEventListener("dragover", (e) => {
    e.preventDefault();
    zone.classList.add("upload-zone--drag");
  });
  zone.addEventListener("dragleave", (e) => {
    if (e.target === zone) zone.classList.remove("upload-zone--drag");
  });
  zone.addEventListener("drop", (e) => {
    e.preventDefault();
    zone.classList.remove("upload-zone--drag");
    const file = e.dataTransfer?.files?.[0];
    if (file) handleFile(file);
  });
}
