"""Phase 8e-5 — image-repair manifest + page-clip unit tests.

Locks the pure coordinate math, the black-bg audit heuristic, and the
stable-evidence manifest matching (verify-cross R2: inverted/degenerate/
out-of-range bbox skip; override scoped + stale-safe)."""

from __future__ import annotations

from pathlib import Path

from ht_lens.image_repair import (
    IMAGES_FIXED_DIR,
    CaptionOverride,
    ImageOverride,
    Overrides,
    black_bg_fraction,
    build_and_save_overrides,
    clip_render_figure,
    is_degraded_candidate,
    is_safe_basename,
    load_overrides,
    match_caption_override,
    match_image_override,
    normalized_bbox_to_page_rect,
    run_image_backfill,
    save_overrides,
)


def _pdf(path: Path, *, pages: int = 1, w: int = 576, h: int = 648, rotation: int = 0) -> None:
    import fitz

    doc = fitz.open()
    for _ in range(pages):
        page = doc.new_page(width=w, height=h)
        page.draw_rect(fitz.Rect(50, 50, 300, 300), fill=(0.2, 0.2, 0.2))
        if rotation:
            page.set_rotation(rotation)
    doc.save(str(path))
    doc.close()


def _png(path: Path, color: tuple[int, int, int]) -> None:
    from PIL import Image

    Image.new("RGB", (80, 80), color).save(path)


# --------------------------------------------------------------------------- #
# normalized_bbox_to_page_rect
# --------------------------------------------------------------------------- #
def test_norm_bbox_doc1_ch1_matches_pdf_page_points() -> None:
    # doc1 ch1 stored bbox [420,91,595,313] on a 576x648 page → middle.json
    # [242,59,343,203] (verified against source PDF page.rect).
    r = normalized_bbox_to_page_rect([420.0, 91.0, 595.0, 313.0], 576, 648)
    assert r is not None
    assert abs(r[0] - 241.9) < 0.5 and abs(r[1] - 59.0) < 0.5
    assert abs(r[2] - 342.7) < 0.5 and abs(r[3] - 202.8) < 0.5


def test_norm_bbox_padding_clamps_to_page() -> None:
    r = normalized_bbox_to_page_rect([0.0, 0.0, 1000.0, 1000.0], 100, 200, pad=20)
    assert r == (0.0, 0.0, 100.0, 200.0)  # full page, pad cannot exceed bounds


def test_norm_bbox_inverted_and_degenerate_return_none() -> None:
    assert normalized_bbox_to_page_rect([10, 10, 5, 20], 100, 100) is None  # x1<x0
    assert normalized_bbox_to_page_rect([10, 10, 20, 10], 100, 100) is None  # y1==y0
    assert normalized_bbox_to_page_rect([10, 10, 10, 20], 100, 100) is None  # x1==x0


def test_norm_bbox_out_of_range_returns_none() -> None:
    assert normalized_bbox_to_page_rect([-10, 10, 50, 60], 100, 100) is None
    assert normalized_bbox_to_page_rect([10, 10, 1100, 60], 100, 100) is None


def test_norm_bbox_malformed_returns_none() -> None:
    assert normalized_bbox_to_page_rect(None, 100, 100) is None
    assert normalized_bbox_to_page_rect([1, 2, 3], 100, 100) is None
    assert normalized_bbox_to_page_rect([1, 2, 3, 4], 0, 100) is None  # bad page dims


# --------------------------------------------------------------------------- #
# black_bg_fraction / is_degraded_candidate (synthetic, hermetic)
# --------------------------------------------------------------------------- #
def test_black_bg_fraction_separates_black_and_white(tmp_path: Path) -> None:
    from PIL import Image

    black = tmp_path / "black.png"
    Image.new("RGB", (80, 80), (0, 0, 0)).save(black)
    white = tmp_path / "white.png"
    Image.new("RGB", (80, 80), (255, 255, 255)).save(white)
    assert black_bg_fraction(black) > 0.9
    assert black_bg_fraction(white) < 0.1
    assert is_degraded_candidate(black) is True
    assert is_degraded_candidate(white) is False


def test_is_degraded_candidate_missing_file_is_false() -> None:
    assert is_degraded_candidate("/no/such/file.png") is False


# --------------------------------------------------------------------------- #
# manifest: save/load + stable-evidence matching
# --------------------------------------------------------------------------- #
def _ov() -> Overrides:
    return Overrides(
        images=[ImageOverride(4, "orig.jpg", [159.0, 91.0, 831.0, 308.0], "orig.png")],
        captions=[CaptionOverride(4, "orig.jpg", [159.0, 91.0, 831.0, 308.0], "Figure 28.19: ...")],
    )


def test_overrides_round_trip(tmp_path: Path) -> None:
    save_overrides(tmp_path, _ov())
    got = load_overrides(tmp_path)
    assert got.images[0].fixed_basename == "orig.png"
    assert got.captions[0].caption.startswith("Figure 28.19")


def test_load_overrides_absent_is_empty(tmp_path: Path) -> None:
    got = load_overrides(tmp_path)
    assert got.images == [] and got.captions == []


def test_load_overrides_drops_non_numeric_bbox(tmp_path: Path) -> None:
    """verify-cross R2 §4#2: a manifest bbox of the wrong type must be dropped
    at load, never reach _bbox_close and crash serving."""
    import json

    (tmp_path / "overrides.json").write_text(
        json.dumps(
            {
                "images": [
                    {  # bad bbox type → dropped (must not crash)
                        "page_idx": 0,
                        "orig_basename": "x.jpg",
                        "bbox": "oops",
                        "fixed_basename": "x.png",
                    },
                    {  # bbox wrong length → dropped
                        "page_idx": 0,
                        "orig_basename": "y.jpg",
                        "bbox": [1, 2, 3],
                        "fixed_basename": "y.png",
                    },
                ],
                "captions": [
                    {
                        "page_idx": 0,
                        "orig_basename": "z.jpg",
                        "bbox": [1, "x", 3, 4],  # non-numeric element → dropped
                        "caption": "c",
                    }
                ],
            }
        )
    )
    ov = load_overrides(tmp_path)
    assert ov.images == [] and ov.captions == []
    # matching against a dropped/garbage bbox never raises
    assert match_image_override(ov, 0, "/p/x.jpg", "oops") is None  # type: ignore[arg-type]


def test_match_image_override_by_stable_evidence(tmp_path: Path) -> None:
    ov = _ov()
    # matches: same page, same basename, close bbox (within tol)
    m = match_image_override(ov, 4, "/abs/path/orig.jpg", [160.0, 91.0, 831.0, 308.0])
    assert m is not None and m.fixed_basename == "orig.png"


def test_match_image_override_stale_and_scoped_return_none() -> None:
    ov = _ov()
    # different page → no match (override scoped to its page)
    assert match_image_override(ov, 5, "/x/orig.jpg", [159.0, 91.0, 831.0, 308.0]) is None
    # basename changed (re-ingest) → stale, no match
    assert match_image_override(ov, 4, "/x/other.jpg", [159.0, 91.0, 831.0, 308.0]) is None
    # bbox drifted beyond tol → no match
    assert match_image_override(ov, 4, "/x/orig.jpg", [400.0, 91.0, 831.0, 308.0]) is None
    # no img_path → no match
    assert match_image_override(ov, 4, None, [159.0, 91.0, 831.0, 308.0]) is None


def test_match_caption_override(tmp_path: Path) -> None:
    ov = _ov()
    m = match_caption_override(ov, 4, "/abs/orig.jpg", [159.0, 91.0, 831.0, 308.0])
    assert m is not None and m.caption.startswith("Figure 28.19")
    assert match_caption_override(ov, 4, "/abs/orig.jpg", [1.0, 2.0, 3.0, 4.0]) is None


# --------------------------------------------------------------------------- #
# clip_render_figure
# --------------------------------------------------------------------------- #
def test_clip_render_figure_writes_png(tmp_path: Path) -> None:
    pdf = tmp_path / "src.pdf"
    _pdf(pdf)
    dest = tmp_path / "out.png"
    assert clip_render_figure(pdf, 0, [100, 100, 500, 500], dest) is True
    assert dest.is_file() and dest.stat().st_size > 0


def test_clip_render_figure_skips_rotated_page(tmp_path: Path) -> None:
    pdf = tmp_path / "rot.pdf"
    _pdf(pdf, rotation=90)
    dest = tmp_path / "out.png"
    assert clip_render_figure(pdf, 0, [100, 100, 500, 500], dest) is False  # no silent mis-crop
    assert not dest.exists()


def test_clip_render_figure_skips_invalid_bbox_and_page(tmp_path: Path) -> None:
    pdf = tmp_path / "src.pdf"
    _pdf(pdf)
    assert clip_render_figure(pdf, 0, [500, 500, 100, 100], tmp_path / "a.png") is False  # inverted
    assert clip_render_figure(pdf, 9, [100, 100, 500, 500], tmp_path / "b.png") is False  # page OOB
    assert not (tmp_path / "a.png").exists() and not (tmp_path / "b.png").exists()


# --------------------------------------------------------------------------- #
# run_image_backfill (dry-run / apply / allowlist)
# --------------------------------------------------------------------------- #
def test_backfill_dry_run_writes_nothing(tmp_path: Path) -> None:
    pdf = tmp_path / "src.pdf"
    _pdf(pdf)
    black = tmp_path / "fig.jpg"
    _png(black, (0, 0, 0))
    ov, report = run_image_backfill(
        chunks=[(0, str(black), [100, 100, 500, 500])],
        pdf_path=pdf,
        dest_root=tmp_path / "doc",
        dry_run=True,
    )
    assert ov == []  # dry-run produces no overrides
    assert report[0].detected is True and report[0].written is False
    assert not (tmp_path / "doc" / IMAGES_FIXED_DIR).exists()


def test_backfill_apply_writes_only_detected(tmp_path: Path) -> None:
    pdf = tmp_path / "src.pdf"
    _pdf(pdf)
    black = tmp_path / "deg.jpg"
    _png(black, (0, 0, 0))
    white = tmp_path / "ok.jpg"
    _png(white, (255, 255, 255))
    ov, _report = run_image_backfill(
        chunks=[(0, str(black), [100, 100, 500, 500]), (0, str(white), [100, 100, 500, 500])],
        pdf_path=pdf,
        dest_root=tmp_path / "doc",
        dry_run=False,
    )
    assert len(ov) == 1 and ov[0].orig_basename == "deg.jpg"
    assert ov[0].fixed_basename == "p0000_deg.png"
    assert (tmp_path / "doc" / IMAGES_FIXED_DIR / "p0000_deg.png").is_file()
    # the white (normal) image is not repaired
    assert not (tmp_path / "doc" / IMAGES_FIXED_DIR / "p0000_ok.png").exists()


def test_backfill_allowlist_filters(tmp_path: Path) -> None:
    pdf = tmp_path / "src.pdf"
    _pdf(pdf)
    black = tmp_path / "deg.jpg"
    _png(black, (0, 0, 0))
    ov, report = run_image_backfill(
        chunks=[(0, str(black), [100, 100, 500, 500])],
        pdf_path=pdf,
        dest_root=tmp_path / "doc",
        allowlist_basenames={"someone_else.jpg"},
        dry_run=False,
    )
    assert ov == []  # detected but not in allowlist → not repaired
    assert report[0].detected is True and report[0].in_allowlist is False


# --------------------------------------------------------------------------- #
# RE-CODE (verify-cross R1): malformed-item / basename safety / collision /
# build_and_save orchestration
# --------------------------------------------------------------------------- #
def test_is_safe_basename() -> None:
    assert is_safe_basename("fig.png") is True
    assert is_safe_basename("/abs/fig.png") is False
    assert is_safe_basename("../fig.png") is False
    assert is_safe_basename("a/b.png") is False
    assert is_safe_basename("") is False


def test_load_overrides_drops_malformed_and_unsafe(tmp_path: Path) -> None:
    import json

    (tmp_path / "overrides.json").write_text(
        json.dumps(
            {
                "images": [
                    "bad",  # not a dict
                    {"page_idx": 0, "orig_basename": "x.jpg", "bbox": [0, 0, 1, 1]},  # missing key
                    {  # unsafe fixed_basename → dropped (R1 §4#2)
                        "page_idx": 0,
                        "orig_basename": "x.jpg",
                        "bbox": [0, 0, 1, 1],
                        "fixed_basename": "../../etc/passwd.png",
                    },
                    {  # valid
                        "page_idx": 1,
                        "orig_basename": "ok.jpg",
                        "bbox": [0, 0, 1, 1],
                        "fixed_basename": "ok.png",
                    },
                ],
                "captions": ["bad", {"page_idx": 1}],  # neither valid
            }
        )
    )
    ov = load_overrides(tmp_path)  # must not raise (R1 §4#3)
    assert [o.fixed_basename for o in ov.images] == ["ok.png"]
    assert ov.captions == []


def test_load_overrides_non_dict_root_is_empty(tmp_path: Path) -> None:
    (tmp_path / "overrides.json").write_text("[1, 2, 3]")
    ov = load_overrides(tmp_path)
    assert ov.images == [] and ov.captions == []


def test_backfill_same_basename_distinct_pages_no_collision(tmp_path: Path) -> None:
    pdf = tmp_path / "src.pdf"
    _pdf(pdf, pages=2)
    black = tmp_path / "dup.jpg"
    _png(black, (0, 0, 0))
    # same original basename appears on two pages → distinct fixed files (R1 §4#4)
    ov, _ = run_image_backfill(
        chunks=[(0, str(black), [100, 100, 500, 500]), (1, str(black), [100, 100, 500, 500])],
        pdf_path=pdf,
        dest_root=tmp_path / "doc",
        dry_run=False,
    )
    fixed = sorted(o.fixed_basename for o in ov)
    assert len(fixed) == 2 and fixed[0] != fixed[1]  # no overwrite
    for fb in fixed:
        assert (tmp_path / "doc" / IMAGES_FIXED_DIR / fb).is_file()


def test_build_and_save_overrides_apply_and_dry_run(tmp_path: Path) -> None:
    pdf = tmp_path / "src.pdf"
    _pdf(pdf)
    black = tmp_path / "deg.jpg"
    _png(black, (0, 0, 0))
    caps = [CaptionOverride(0, "deg.jpg", [100, 100, 500, 500], "Figure X")]
    root = tmp_path / "doc"
    # dry-run: nothing written
    build_and_save_overrides(
        chunks=[(0, str(black), [100, 100, 500, 500])],
        pdf_path=pdf,
        dest_root=root,
        caption_overrides=caps,
        dry_run=True,
    )
    assert not (root / "overrides.json").exists()
    # apply: manifest with image override + merged captions persisted
    build_and_save_overrides(
        chunks=[(0, str(black), [100, 100, 500, 500])],
        pdf_path=pdf,
        dest_root=root,
        caption_overrides=caps,
        dry_run=False,
    )
    loaded = load_overrides(root)
    assert len(loaded.images) == 1 and len(loaded.captions) == 1
    assert loaded.captions[0].caption == "Figure X"


# --------------------------------------------------------------------------- #
# Phase 8e-6 detectors (read-only audit)
# --------------------------------------------------------------------------- #
def test_detect_degraded_images(tmp_path: Path) -> None:
    from ht_lens.image_repair import detect_degraded_images

    black = tmp_path / "deg.jpg"
    _png(black, (0, 0, 0))
    white = tmp_path / "ok.jpg"
    _png(white, (255, 255, 255))
    out = detect_degraded_images(
        [
            (0, 0, str(black), [100, 100, 500, 500]),
            (1, 1, str(white), [100, 100, 500, 500]),
            (2, 2, str(black), [1, 2, 3]),  # degraded but malformed bbox (len 3)
            (3, 3, None, None),  # no path → skipped
            (4, 4, str(tmp_path / "gone.jpg"), [0, 0, 1, 1]),  # missing → skipped
        ]
    )
    by = {c.page_idx: c for c in out}
    assert 0 in by and by[0].black_frac > 0.6 and by[0].bbox_valid is True
    assert by[0].order_idx == 0
    assert all(c.black_frac > 0.6 for c in out)
    assert not any(c.page_idx == 1 for c in out)  # white not degraded
    # malformed bbox degraded one is flagged but marked clip-impossible (reported)
    assert by[2].bbox_valid is False
    assert len(out) == 2  # deg(p0) + malformed(p2); white/none/missing excluded


def test_detect_degraded_images_same_basename_same_page_distinct_identity(tmp_path: Path) -> None:
    from ht_lens.image_repair import detect_degraded_images

    black = tmp_path / "dup.jpg"
    _png(black, (0, 0, 0))
    # two chunks, same page + same basename, different order_idx → kept distinct
    out = detect_degraded_images(
        [(0, 5, str(black), [0, 0, 400, 400]), (0, 6, str(black), [0, 0, 400, 400])]
    )
    assert len(out) == 2
    assert {c.order_idx for c in out} == {5, 6}  # identity preserved (R1 §4#1)


def _ci(cid, pg, cap, bbox, base):
    from ht_lens.image_repair import ImageChunkInfo

    return ImageChunkInfo(cid, pg, cap, bbox, f"/x/{base}")


def test_detect_caption_mispairs_flags_captionless_coexist() -> None:
    from ht_lens.image_repair import detect_caption_mispairs

    # doc5-style: page with a captionless image + a captioned sibling
    chunks = [
        _ci(1, 0, None, [160, 95, 839, 272], "a.jpg"),  # captionless (top)
        _ci(2, 0, "(a) Parallel (b) Sequential Figure 6.2", [142, 299, 861, 477], "b.jpg"),
    ]
    pages = detect_caption_mispairs(chunks)
    assert len(pages) == 1 and pages[0].page_idx == 0
    assert {im.has_caption for im in pages[0].images} == {True, False}


def test_detect_caption_mispairs_no_fp_all_captioned() -> None:
    from ht_lens.image_repair import detect_caption_mispairs

    # normal multi-panel: every image has its (a)/(b) label → NOT flagged
    chunks = [
        _ci(1, 0, "(a) Ordered ratings", [0, 0, 400, 400], "a.jpg"),
        _ci(2, 0, "(b) Unary ratings Figure 1.3", [400, 0, 800, 400], "b.jpg"),
    ]
    assert detect_caption_mispairs(chunks) == []


def test_detect_caption_mispairs_single_image_page_ignored() -> None:
    from ht_lens.image_repair import detect_caption_mispairs

    assert detect_caption_mispairs([_ci(1, 0, None, [0, 0, 100, 100], "a.jpg")]) == []


def test_detect_caption_mispairs_excludes_nested_dedup_drop() -> None:
    from ht_lens.image_repair import detect_caption_mispairs

    # captioned full crop contains a captionless panel (8e-4 dedup drops it) +
    # nothing else captionless → must NOT be flagged as a caption mispair.
    chunks = [
        _ci(1, 0, "Figure X full", [0, 0, 500, 500], "full.jpg"),
        _ci(2, 0, None, [50, 50, 200, 200], "panel.jpg"),  # nested → excluded
    ]
    assert detect_caption_mispairs(chunks) == []
