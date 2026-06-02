"""Phase 8e-4 — nested image dedup unit tests (render-filter).

Locks ``_drop_captionless_images_contained_by_captioned``: drop a captionless
image only when a same-page captioned image STRICTLY contains it (doc1 Fig
28.18 = 3 panels nested in the captioned full crop). Keeps side-by-side figures,
standalone captionless images, equal bboxes, and malformed bboxes (verify-cross
§2.6/§3.11/§3.12/§5.5-5.7).
"""

from __future__ import annotations

from ht_lens.api.routers.reflow import (
    ReflowChunk,
    _drop_captionless_images_contained_by_captioned,
    _strict_contains,
)


def _img(cid: int, page: int, bbox, caption: str | None):
    return ReflowChunk(
        id=cid,
        type="image",
        text_level=None,
        page_idx=page,
        original="",
        translated=None,
        caption=caption,
        caption_translated=None,
        img_url=f"/v2/chunks/{cid}/image",
        bbox=bbox,
    )


def _text(cid: int, page: int):
    return ReflowChunk(
        id=cid,
        type="text",
        text_level=None,
        page_idx=page,
        original="t",
        translated="ㅌ",
        caption=None,
        caption_translated=None,
        img_url=None,
        bbox=None,
    )


def _ids(chunks):
    return [c.id for c in chunks]


# --------------------------------------------------------------------------- #
# _strict_contains
# --------------------------------------------------------------------------- #
def test_strict_contains_true_for_nested_panel() -> None:
    full = [156.0, 84.0, 855.0, 475.0]  # Fig 28.18 full crop
    for panel in ([512, 273, 857, 461], [156, 86, 503, 266], [508, 84, 855, 276]):
        assert _strict_contains(full, [float(v) for v in panel]), panel


def test_strict_contains_false_for_equal_disjoint_inverted_malformed() -> None:
    box = [0.0, 0.0, 100.0, 100.0]
    assert not _strict_contains(box, list(box))  # equal → not strict
    assert not _strict_contains(box, [200.0, 200.0, 300.0, 300.0])  # disjoint
    assert not _strict_contains(box, [10.0, 10.0, 5.0, 5.0])  # inverted child
    assert not _strict_contains(
        [100.0, 100.0, 0.0, 0.0], [10.0, 10.0, 50.0, 50.0]
    )  # inverted parent
    assert not _strict_contains(box, None)
    assert not _strict_contains(box, [1.0, 2.0, 3.0])  # len 3


# --------------------------------------------------------------------------- #
# _drop_captionless_images_contained_by_captioned
# --------------------------------------------------------------------------- #
def test_drops_nested_captionless_panels_keeps_captioned_full() -> None:
    # doc1 page2 Figure 28.18: full(30, caption) contains panels 27/28/29 (nocap).
    chunks = [
        _text(10, 2),
        _img(27, 2, [512.0, 273.0, 857.0, 461.0], None),
        _img(28, 2, [156.0, 86.0, 503.0, 266.0], None),
        _img(29, 2, [508.0, 84.0, 855.0, 276.0], None),
        _img(30, 2, [156.0, 84.0, 855.0, 475.0], "Figure 28.18: (a) ..."),
        _text(31, 2),
    ]
    out = _drop_captionless_images_contained_by_captioned(chunks)
    assert _ids(out) == [10, 30, 31]  # panels gone, full + text kept, order preserved


def test_keeps_side_by_side_figures_not_nested() -> None:
    # doc1 page4: a wide captionless image above two captioned figures side by
    # side — none contains another → all kept.
    chunks = [
        _img(53, 4, [159.0, 91.0, 831.0, 308.0], None),
        _img(54, 4, [218.0, 399.0, 451.0, 625.0], "Figure 28.19: ..."),
        _img(55, 4, [590.0, 398.0, 762.0, 625.0], "Figure 28.20: ..."),
    ]
    assert _ids(_drop_captionless_images_contained_by_captioned(chunks)) == [53, 54, 55]


def test_keeps_standalone_captionless_image() -> None:
    # A captionless diagram with no captioned container stays visible.
    chunks = [_text(1, 0), _img(2, 0, [10.0, 10.0, 50.0, 50.0], None)]
    assert _ids(_drop_captionless_images_contained_by_captioned(chunks)) == [1, 2]


def test_keeps_equal_bbox_captionless() -> None:
    # Same bbox captioned + captionless → not a nested panel (strict only).
    chunks = [
        _img(1, 0, [0.0, 0.0, 100.0, 100.0], "cap"),
        _img(2, 0, [0.0, 0.0, 100.0, 100.0], None),
    ]
    assert _ids(_drop_captionless_images_contained_by_captioned(chunks)) == [1, 2]


def test_malformed_bbox_never_drops() -> None:
    chunks = [
        _img(1, 0, [0.0, 0.0, 200.0, 200.0], "cap"),
        _img(2, 0, None, None),  # no bbox
        _img(3, 0, [100.0, 100.0, 10.0, 10.0], None),  # inverted
    ]
    assert _ids(_drop_captionless_images_contained_by_captioned(chunks)) == [1, 2, 3]


def test_only_captioned_container_drops_captionless() -> None:
    # A captionless image containing a captionless image must NOT drop it
    # (only a CAPTIONED container drops).
    chunks = [
        _img(1, 0, [0.0, 0.0, 200.0, 200.0], None),  # captionless container
        _img(2, 0, [50.0, 50.0, 100.0, 100.0], None),  # captionless child
    ]
    assert _ids(_drop_captionless_images_contained_by_captioned(chunks)) == [1, 2]


def test_different_pages_not_compared() -> None:
    chunks = [
        _img(1, 0, [0.0, 0.0, 200.0, 200.0], "cap"),
        _img(2, 1, [50.0, 50.0, 100.0, 100.0], None),  # different page → kept
    ]
    assert _ids(_drop_captionless_images_contained_by_captioned(chunks)) == [1, 2]
