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
    clip_render_figure,
    is_degraded_candidate,
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
    assert ov[0].fixed_basename == "deg.png"
    assert (tmp_path / "doc" / IMAGES_FIXED_DIR / "deg.png").is_file()
    # the white (normal) image is not repaired
    assert not (tmp_path / "doc" / IMAGES_FIXED_DIR / "ok.png").exists()


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
