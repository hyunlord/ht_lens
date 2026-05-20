"""CLI error contracts and edge cases."""

from __future__ import annotations

import json
from pathlib import Path

import fitz  # type: ignore[import-untyped]

from ht_lens.cli import main

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _run(args: list[str]) -> int:
    return main(["extract", *args])


def _make_encrypted_pdf(path: Path) -> None:
    doc = fitz.open()
    doc.new_page()
    doc.save(str(path), encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="secret", owner_pw="owner")
    doc.close()


def _make_corrupted_pdf(path: Path) -> None:
    path.write_bytes(b"%PDF-1.4\nthis is not a real PDF body\n%%EOF\n")


def _make_image_only_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 200, 200))
    pix.clear_with(255)
    page.insert_image(fitz.Rect(100, 100, 300, 300), pixmap=pix)
    doc.save(str(path))
    doc.close()


def test_cli_rejects_existing_non_empty_out_dir_without_overwrite(
    tmp_path: Path,
) -> None:
    out = tmp_path / "out"
    out.mkdir()
    (out / "stash.txt").write_text("hi")
    code = _run([str(FIXTURES / "sample_en.pdf"), "-o", str(out)])
    assert code == 2
    # external file must not be touched
    assert (out / "stash.txt").read_text() == "hi"


def test_cli_overwrite_replaces_previous_output(tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    stale = out / "pages"
    stale.mkdir()
    (stale / "page_9999.json").write_text("{}")
    external = out / "untouched.txt"
    external.write_text("keep me")

    code = _run([str(FIXTURES / "sample_en.pdf"), "-o", str(out), "--overwrite"])
    assert code == 0
    assert not (out / "pages" / "page_9999.json").exists()
    assert external.read_text() == "keep me"
    assert (out / "doc_meta.json").exists()


def test_encrypted_pdf_exit_code_2(tmp_path: Path) -> None:
    pdf = tmp_path / "enc.pdf"
    _make_encrypted_pdf(pdf)
    out = tmp_path / "out"
    code = _run([str(pdf), "-o", str(out)])
    assert code == 2
    # Failure must not leave pages/ behind to block a retry without --overwrite.
    assert not (out / "pages").exists()
    assert not (out / "images").exists()


def test_corrupted_pdf_exit_code_3(tmp_path: Path) -> None:
    pdf = tmp_path / "bad.pdf"
    _make_corrupted_pdf(pdf)
    out = tmp_path / "out"
    code = _run([str(pdf), "-o", str(out)])
    assert code == 3
    assert not (out / "pages").exists()
    assert not (out / "images").exists()


def test_scanned_page_writes_empty_blocks_json(tmp_path: Path) -> None:
    pdf = tmp_path / "scan.pdf"
    _make_image_only_pdf(pdf)
    out = tmp_path / "out"
    code = _run([str(pdf), "-o", str(out)])
    assert code == 0
    page_json = json.loads((out / "pages" / "page_0001.json").read_text())
    text_blocks = [b for b in page_json["blocks"] if b["type"] in ("text", "header")]
    assert text_blocks == []
    # png exists
    assert (out / "pages" / "page_0001.png").exists()
