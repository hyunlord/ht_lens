"""Unit tests for ORM model definitions and Block.bbox property."""

from __future__ import annotations

import json

from ht_lens.db.models import Block


def test_block_bbox_decodes_correctly() -> None:
    b = Block(
        page_id=1,
        block_local_id="p1_b001",
        type="text",
        bbox_json=json.dumps([10.5, 20.0, 100.5, 50.0]),
        order_idx=0,
        original_text="hello",
    )
    assert b.bbox == (10.5, 20.0, 100.5, 50.0)


def test_block_bbox_returns_floats() -> None:
    b = Block(
        page_id=1,
        block_local_id="p1_b001",
        type="text",
        bbox_json=json.dumps([0, 0, 200, 400]),
        order_idx=0,
        original_text="",
    )
    x0, y0, x1, y1 = b.bbox
    assert all(isinstance(v, float) for v in (x0, y0, x1, y1))
