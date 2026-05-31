# Phase 8e-1 — Bold extraction spike (R-F finding, durable artifact)

verify-cross R1 §4#4 asked for an auditable artifact. This records the MinerU
CPU `pipeline` inspection that concluded bold is not available without GPU.

## Source
- Extractor: MinerU 3.2.1 (`~/mineru_test/venv/bin/mineru`), backend `pipeline` (CPU), the 8a/8e production extraction mode.
- Output: `~/mineru_test/output_cpu_990-1000/doc7_chapter_990-1000/auto/` (doc7 ch28 slice).

## Inspection (exact)
```
# span-level keys across middle.json (pdf_info → preproc_blocks → lines → spans)
SPAN keys seen: {'bbox', 'type', 'content', 'score', 'image_path', 'cross_page'}
LINE keys seen: {'bbox', 'spans'}
STYLE-RELATED keys anywhere (bold/italic/weight/style/font/strong): NONE
content_list_v2.json style keys: NONE
raw markdown (*.md) bold markers (** / __): 0
```
- The earlier substring grep that "found" `bold`/`weight`/`style` was a FALSE POSITIVE — those words appear inside body-text content, not as structural keys. A key-name walk found zero style attributes and zero `bold=true` spans.

## Conclusion
- **Bold is not present in the MinerU CPU `pipeline` structured output.** There is no span-level style/weight metadata to read, and the rendered markdown carries no `**`.
- Bold therefore requires one of (deferred to 8e-2 backend decision per challenge R-F):
  - (a) GPU `vlm-*` / `hybrid-*` MinerU backend (richer markdown; needs the Blackwell GPU the user chose to avoid for the CPU batch), or
  - (b) PyMuPDF font-flag extraction (1.x technique) reconciled onto MinerU chunks (extra pipeline, non-trivial alignment).
- The reflow renderer already supports bold (`render_markdown.js` marked GFM → `<strong>`, DOMPurify allows it), so the gap is purely extraction-side.

## Recommendation
- 8e-1 ships math hardening; bold is a documented finding, NOT implemented.
- 8e-2 (extraction batch) is where the backend is chosen — surface options (a)/(b)/defer to the user there.
