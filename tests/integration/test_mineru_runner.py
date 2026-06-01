"""Phase 8a — MinerU runner unit tests (verify-cross R1 §5.4).

Covers binary discovery (env/PATH/missing), output-path glob discovery
against a fake MinerU tree (sanitized stem + nested images), and
subprocess failure branches (nonzero exit, missing content_list) — all
without invoking real MinerU.
"""

from __future__ import annotations

import stat
from pathlib import Path

import pytest

from ht_lens.errors import MineruError
from ht_lens.extract_mineru.runner import (
    _discover_outputs,
    resolve_mineru_bin,
    run_mineru,
)

# --- binary discovery ---


def test_resolve_bin_env_explicit_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = tmp_path / "mineru"
    fake.write_text("#!/bin/sh\n")
    fake.chmod(0o755)
    monkeypatch.setenv("HT_LENS_MINERU_BIN", str(fake))
    assert resolve_mineru_bin() == str(fake)


def test_resolve_bin_env_missing_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HT_LENS_MINERU_BIN", "/nonexistent/mineru-xyz")
    with pytest.raises(MineruError, match="not found"):
        resolve_mineru_bin()


def test_resolve_bin_falls_back_to_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HT_LENS_MINERU_BIN", raising=False)
    monkeypatch.setattr(
        "shutil.which", lambda name: "/usr/bin/mineru" if name == "mineru" else None
    )
    assert resolve_mineru_bin() == "/usr/bin/mineru"


def test_resolve_bin_absent_everywhere_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HT_LENS_MINERU_BIN", raising=False)
    monkeypatch.setattr("shutil.which", lambda name: None)
    with pytest.raises(MineruError, match="MinerU not found"):
        resolve_mineru_bin()


# --- output discovery (glob, not hard-coded layout) ---


def test_discover_outputs_sanitized_stem_and_nested_images(tmp_path: Path) -> None:
    # MinerU may sanitize the stem and nest under <stem>/auto/.
    auto = tmp_path / "weird-stem_v2" / "auto"
    (auto / "images").mkdir(parents=True)
    cl = auto / "weird-stem_v2_content_list.json"
    cl.write_text("[]", encoding="utf-8")
    (auto / "weird-stem_v2.md").write_text("# x", encoding="utf-8")
    (auto / "images" / "f.jpg").write_bytes(b"x")

    result = _discover_outputs(tmp_path)
    assert result.content_list_path == cl
    assert result.images_dir == auto / "images"
    assert result.markdown_path == auto / "weird-stem_v2.md"


def test_discover_outputs_missing_content_list_raises(tmp_path: Path) -> None:
    (tmp_path / "auto").mkdir()
    with pytest.raises(MineruError, match=r"no \*_content_list\.json"):
        _discover_outputs(tmp_path)


# --- subprocess failure branches (fake binaries) ---


def _write_script(path: Path, body: str) -> None:
    path.write_text("#!/bin/sh\n" + body)
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IRUSR)


def test_run_mineru_nonzero_exit_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pdf = tmp_path / "in.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    fake = tmp_path / "mineru"
    _write_script(fake, 'echo "boom" >&2\nexit 1\n')
    monkeypatch.setenv("HT_LENS_MINERU_BIN", str(fake))
    with pytest.raises(MineruError, match="exited 1"):
        run_mineru(pdf, tmp_path / "out", timeout_s=30)


def test_run_mineru_success_discovers_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf = tmp_path / "in.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    out = tmp_path / "out"
    # Fake MinerU: create the expected nested output structure.
    fake = tmp_path / "mineru"
    _write_script(
        fake,
        f'mkdir -p "{out}/in/auto/images"\n'
        f'printf "[]" > "{out}/in/auto/in_content_list.json"\n'
        f'echo "# md" > "{out}/in/auto/in.md"\n',
    )
    monkeypatch.setenv("HT_LENS_MINERU_BIN", str(fake))
    result = run_mineru(pdf, out, timeout_s=30)
    assert result.content_list_path.name == "in_content_list.json"
    assert result.content_list_path.is_file()


def test_run_mineru_success_but_no_content_list_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Exit 0 but no content_list — partial output must NOT count as success.
    pdf = tmp_path / "in.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    fake = tmp_path / "mineru"
    _write_script(fake, "exit 0\n")
    monkeypatch.setenv("HT_LENS_MINERU_BIN", str(fake))
    with pytest.raises(MineruError, match=r"no \*_content_list\.json"):
        run_mineru(pdf, tmp_path / "out", timeout_s=30)


def test_run_mineru_sets_cpu_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # The CPU flag must export CUDA_VISIBLE_DEVICES="" to the subprocess.
    pdf = tmp_path / "in.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    out = tmp_path / "out"
    fake = tmp_path / "mineru"
    _write_script(
        fake,
        f'echo "cuda=[$CUDA_VISIBLE_DEVICES]" > "{tmp_path}/cuda.txt"\n'
        f'mkdir -p "{out}/in/auto"\n'
        f'printf "[]" > "{out}/in/auto/in_content_list.json"\n',
    )
    monkeypatch.setenv("HT_LENS_MINERU_BIN", str(fake))
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "0")  # should be overridden to ""
    run_mineru(pdf, out, cpu=True, timeout_s=30)
    assert (tmp_path / "cuda.txt").read_text().strip() == "cuda=[]"


def test_run_mineru_threads_timeout_to_mineru_internal_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Phase 8e-2 verify-cross R1 §4#1: timeout_s must cover MinerU's INTERNAL
    task-result wait, not only the parent subprocess. The 518p Aggarwal run died
    at MinerU's default 3600s internal limit despite a larger --timeout; the
    runner now exports MINERU_TASK_RESULT_TIMEOUT_SECONDS=timeout_s."""
    pdf = tmp_path / "in.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    out = tmp_path / "out"
    fake = tmp_path / "mineru"
    _write_script(
        fake,
        f'echo "task=[$MINERU_TASK_RESULT_TIMEOUT_SECONDS]" > "{tmp_path}/t.txt"\n'
        f'echo "startup=[$MINERU_LOCAL_API_STARTUP_TIMEOUT_SECONDS]" >> "{tmp_path}/t.txt"\n'
        f'mkdir -p "{out}/in/auto"\n'
        f'printf "[]" > "{out}/in/auto/in_content_list.json"\n',
    )
    monkeypatch.setenv("HT_LENS_MINERU_BIN", str(fake))
    monkeypatch.delenv("MINERU_TASK_RESULT_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("MINERU_LOCAL_API_STARTUP_TIMEOUT_SECONDS", raising=False)
    run_mineru(pdf, out, timeout_s=14400)
    body = (tmp_path / "t.txt").read_text()
    assert "task=[14400]" in body  # internal wait gets the full budget
    assert "startup=[600]" in body  # startup capped at 600s


def test_run_mineru_internal_timeout_respects_operator_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An operator-set MINERU_TASK_RESULT_TIMEOUT_SECONDS wins (setdefault)."""
    pdf = tmp_path / "in.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    out = tmp_path / "out"
    fake = tmp_path / "mineru"
    _write_script(
        fake,
        f'echo "task=[$MINERU_TASK_RESULT_TIMEOUT_SECONDS]" > "{tmp_path}/t.txt"\n'
        f'mkdir -p "{out}/in/auto"\n'
        f'printf "[]" > "{out}/in/auto/in_content_list.json"\n',
    )
    monkeypatch.setenv("HT_LENS_MINERU_BIN", str(fake))
    monkeypatch.setenv("MINERU_TASK_RESULT_TIMEOUT_SECONDS", "9999")
    run_mineru(pdf, out, timeout_s=14400)
    assert "task=[9999]" in (tmp_path / "t.txt").read_text()  # operator value preserved


def test_run_mineru_missing_pdf_raises(tmp_path: Path) -> None:
    with pytest.raises(MineruError, match="PDF not found"):
        run_mineru(tmp_path / "nope.pdf", tmp_path / "out")
