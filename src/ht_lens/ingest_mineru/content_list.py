"""Typed parser for MinerU ``content_list.json`` (Phase 8a).

MinerU emits a flat, reading-ordered list of typed items per document.
This module normalizes that list into ``ParsedChunk`` records before any
DB insert, so MinerU-version assumptions live in exactly one place
(challenge §4 — typed parser boundary).

Item taxonomy observed in MinerU 3.2.1 (``~/mineru_test`` sandbox):

- ``text`` with no ``text_level``  → body paragraph        → chunk ``text``
- ``text`` with ``text_level=N``   → section heading        → chunk ``heading``
- ``equation`` (``text_format=latex``) → display math        → chunk ``equation``
- ``image`` (``img_path``, ``image_caption``)                → chunk ``image``
- ``chart`` (``img_path``, ``content``, ``chart_caption``)   → chunk ``image`` (content kept)
- ``table`` (``text`` html/latex)                            → chunk ``table``
- ``page_number`` / ``header`` / ``footer`` / ``page_footnote`` → page chrome → **dropped**

``header`` is the *running page header* (e.g. "Chapter 28…"), NOT a section
heading — section headings are ``text`` items carrying ``text_level``. This
distinction is load-bearing and locked by ``test_content_list_parser``.

Malformed handling (challenge §3.1, explicit — never silent loss):
- ``page_idx`` missing/non-int → ``ContentListError`` (reject the document).
- ``bbox`` missing/malformed   → stored as ``"[]"`` (provenance gap logged).
- ``text`` ``None``/empty on a text-ish item → item skipped (no empty chunk).
- unrecognized ``type``        → preserved as chunk ``unknown`` (no drop).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

_log = logging.getLogger("ht_lens.ingest_mineru")

# Running page chrome — excluded from the reflow stream.
CHROME_TYPES = frozenset({"page_number", "header", "footer", "page_footnote"})

# MinerU types that carry a figure/chart image.
_IMAGE_TYPES = frozenset({"image", "chart"})


class ContentListError(ValueError):
    """Raised when ``content_list.json`` is structurally unusable."""


@dataclass(frozen=True)
class ParsedChunk:
    """One normalized, reflow-ordered item ready for DB insert.

    ``bbox_json`` keeps MinerU's raw coordinates verbatim (provenance);
    coordinate-system reconciliation (px↔pt / rotation) is deferred to the
    side-by-side viewer in Phase 8c.
    """

    page_idx: int
    order_idx: int
    type: str  # text | heading | equation | image | table | unknown
    text_level: int | None
    bbox_json: str
    content: str
    text_format: str | None
    img_path: str | None
    caption: str | None


def _bbox_json(item: dict[str, Any]) -> str:
    raw = item.get("bbox")
    if isinstance(raw, list) and len(raw) == 4:
        try:
            return json.dumps([float(v) for v in raw])
        except (TypeError, ValueError):
            pass
    _log.warning("content_list item missing/malformed bbox (type=%s)", item.get("type"))
    return "[]"


def _require_page_idx(item: dict[str, Any], pos: int) -> int:
    raw = item.get("page_idx")
    if raw is None:
        raise ContentListError(f"item #{pos} missing page_idx")
    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        raise ContentListError(f"item #{pos} non-int page_idx: {raw!r}") from exc


def _join_captions(item: dict[str, Any], *keys: str) -> str | None:
    parts: list[str] = []
    for key in keys:
        val = item.get(key)
        if isinstance(val, list):
            parts.extend(str(v).strip() for v in val if str(v).strip())
        elif isinstance(val, str) and val.strip():
            parts.append(val.strip())
    return " ".join(parts) if parts else None


def parse_content_list(items: list[dict[str, Any]]) -> list[ParsedChunk]:
    """Normalize a MinerU ``content_list`` (already JSON-decoded) into chunks.

    ``order_idx`` is assigned sequentially over *kept* items so the reflow
    order has no gaps from dropped chrome.
    """
    if not isinstance(items, list):
        raise ContentListError(f"content_list must be a list, got {type(items).__name__}")

    chunks: list[ParsedChunk] = []
    order = 0
    for pos, item in enumerate(items):
        if not isinstance(item, dict):
            raise ContentListError(f"item #{pos} is not an object: {type(item).__name__}")
        mtype = item.get("type")
        if mtype in CHROME_TYPES:
            continue

        page_idx = _require_page_idx(item, pos)
        bbox = _bbox_json(item)

        text = item.get("text")
        text = text.strip() if isinstance(text, str) else ""

        if mtype == "text":
            if not text:
                continue  # empty body/heading — skip, no hollow chunk
            level = item.get("text_level")
            if level is not None:
                try:
                    level_int = int(level)
                except (TypeError, ValueError) as exc:
                    # Normalize into the parser's domain error rather than
                    # letting a raw ValueError escape ingest (verify-cross R1 §4).
                    raise ContentListError(f"item #{pos} non-int text_level: {level!r}") from exc
                chunk = ParsedChunk(
                    page_idx, order, "heading", level_int, bbox, text, None, None, None
                )
            else:
                chunk = ParsedChunk(page_idx, order, "text", None, bbox, text, None, None, None)
        elif mtype == "equation":
            if not text:
                continue
            chunk = ParsedChunk(
                page_idx,
                order,
                "equation",
                None,
                bbox,
                text,
                item.get("text_format") or "latex",
                item.get("img_path"),
                None,
            )
        elif mtype in _IMAGE_TYPES:
            caption = _join_captions(item, "image_caption", "chart_caption")
            content = item.get("content") if isinstance(item.get("content"), str) else ""
            chunk = ParsedChunk(
                page_idx,
                order,
                "image",
                None,
                bbox,
                content or "",
                None,
                item.get("img_path"),
                caption,
            )
        elif mtype == "table":
            caption = _join_captions(item, "table_caption")
            body = text or (
                item.get("table_body") if isinstance(item.get("table_body"), str) else ""
            )
            chunk = ParsedChunk(
                page_idx,
                order,
                "table",
                None,
                bbox,
                body or "",
                None,
                item.get("img_path"),
                caption,
            )
        else:
            # Unrecognized type — preserve, never silently drop (challenge §3.1/§5.2).
            _log.warning("content_list unknown type %r preserved as 'unknown'", mtype)
            chunk = ParsedChunk(
                page_idx, order, "unknown", None, bbox, text, None, item.get("img_path"), None
            )

        chunks.append(chunk)
        order += 1

    return chunks


__all__ = ["CHROME_TYPES", "ContentListError", "ParsedChunk", "parse_content_list"]
