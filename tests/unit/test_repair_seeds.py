"""Phase F1 (8e-5 follow-up) — committed repair seeds are well-formed.

Locks `repair_seeds/*.json` (the durable, reviewed repair inputs) so a malformed
seed is caught in CI before `ht-lens repair-images` ever runs. The live manifest
under data/extracts_v2/<doc>/ is gitignored; the seed is the git source of truth."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ht_lens.image_repair import CaptionOverride, ImageOverride, is_safe_basename

SEEDS_DIR = Path(__file__).resolve().parents[2] / "repair_seeds"


def _valid_bbox(b: object) -> bool:
    return (
        isinstance(b, list)
        and len(b) == 4
        and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in b)
    )


@pytest.mark.parametrize("name", ["doc1.json", "doc5.json"])
def test_repair_seed_well_formed(name: str) -> None:
    data = json.loads((SEEDS_DIR / name).read_text())
    assert isinstance(data.get("image_allowlist", []), list)
    assert isinstance(data.get("captions", []), list)
    # image_allowlist entries are plain basenames (no path escape)
    for b in data.get("image_allowlist", []):
        assert isinstance(b, str) and is_safe_basename(b), b
    # every caption entry has the stable-evidence keys + valid types, and can
    # construct a CaptionOverride (the exact shape the CLI/manifest consumes)
    for c in data.get("captions", []):
        assert {"page_idx", "orig_basename", "bbox", "caption"} <= c.keys()
        assert isinstance(c["page_idx"], int)
        assert isinstance(c["orig_basename"], str) and c["orig_basename"]
        assert _valid_bbox(c["bbox"]), c
        assert isinstance(c["caption"], str) and c["caption"].strip()
        CaptionOverride(c["page_idx"], c["orig_basename"], c["bbox"], c["caption"])


def test_doc5_seed_is_caption_only_with_expected_corrections() -> None:
    data = json.loads((SEEDS_DIR / "doc5.json").read_text())
    assert data["image_allowlist"] == []  # caption-only (no degraded images)
    caps = {(c["page_idx"], c["caption"]) for c in data["captions"]}
    assert len(data["captions"]) == 8
    # the confirmed doc1-style mis-pairing corrections (panel label restored)
    assert (223, "(a) Parallel design") in caps
    assert (257, "(a) Proportional division of ratings") in caps
    assert (339, "(a) Ratings matrix") in caps
    assert (109, "(a) Perceptron") in caps


def test_doc1_seed_has_image_allowlist() -> None:
    data = json.loads((SEEDS_DIR / "doc1.json").read_text())
    assert len(data["image_allowlist"]) == 3  # 3 degraded PGM diagrams
    assert all(is_safe_basename(b) for b in data["image_allowlist"])
    # constructing ImageOverride-shaped expectations stays valid
    assert len(data["captions"]) == 3  # page4 28.19/28.20a/28.20b
    _ = ImageOverride  # imported symbol used to assert availability
