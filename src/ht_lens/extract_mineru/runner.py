"""Run MinerU on a PDF and locate its structured output (Phase 8a).

MinerU is a CPU subprocess here (GB10 Blackwell + CUDA 13 aborts every
torch/paddle GPU path via a ``cublasLt`` symbol error — validated in the
``~/mineru_test`` sandbox). ``CUDA_VISIBLE_DEVICES=""`` forces CPU.

Binary discovery (challenge §1.3 — no sandbox path baked into product
code): ``HT_LENS_MINERU_BIN`` env wins; otherwise ``mineru`` on ``PATH``;
otherwise a clear ``MineruError``.

Output discovery (challenge §2.2 — don't hard-code the layout): after the
run we *glob* for ``*_content_list.json`` under the output dir rather than
reconstructing ``<out>/<stem>/auto/<stem>_content_list.json``, so stem
sanitization or layout changes don't silently break ingest.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from ht_lens.errors import MineruError

_log = logging.getLogger("ht_lens.extract_mineru")

# Generous default; large PDFs on CPU are slow. Override via arg.
_DEFAULT_TIMEOUT_S = 3600


@dataclass(frozen=True)
class MineruResult:
    content_list_path: Path
    images_dir: Path | None
    markdown_path: Path | None
    out_dir: Path


def resolve_mineru_bin() -> str:
    """Return the MinerU executable path or raise ``MineruError``.

    Order: ``HT_LENS_MINERU_BIN`` env → ``mineru`` on ``PATH``.
    """
    env_bin = os.environ.get("HT_LENS_MINERU_BIN")
    if env_bin:
        if Path(env_bin).is_file() or shutil.which(env_bin):
            return env_bin
        raise MineruError(
            f"HT_LENS_MINERU_BIN={env_bin!r} not found. "
            "Point it at a MinerU executable or unset it to use PATH."
        )
    found = shutil.which("mineru")
    if found:
        return found
    raise MineruError(
        "MinerU not found. Install it and set HT_LENS_MINERU_BIN, "
        "or put `mineru` on PATH (Phase 8a extraction is a one-time CPU batch)."
    )


def _discover_outputs(out_dir: Path) -> MineruResult:
    matches = sorted(out_dir.rglob("*_content_list.json"))
    if not matches:
        raise MineruError(
            f"MinerU produced no *_content_list.json under {out_dir} "
            "(extraction likely failed or wrote elsewhere)."
        )
    if len(matches) > 1:
        _log.warning("multiple content_list.json under %s; using %s", out_dir, matches[0])
    content_list = matches[0]
    auto_dir = content_list.parent
    images = auto_dir / "images"
    images_dir = images if images.is_dir() else None
    md_matches = sorted(auto_dir.glob("*.md"))
    markdown = md_matches[0] if md_matches else None
    return MineruResult(
        content_list_path=content_list,
        images_dir=images_dir,
        markdown_path=markdown,
        out_dir=out_dir,
    )


def run_mineru(
    pdf: Path,
    out_dir: Path,
    *,
    lang: str = "en",
    backend: str = "pipeline",
    cpu: bool = True,
    timeout_s: int = _DEFAULT_TIMEOUT_S,
) -> MineruResult:
    """Extract ``pdf`` with MinerU into ``out_dir``; return discovered paths.

    Raises ``MineruError`` on missing binary, nonzero exit, timeout, or
    absent ``content_list.json`` (challenge §3.5 — partial output is never
    reported as success).
    """
    pdf = Path(pdf)
    out_dir = Path(out_dir)
    if not pdf.is_file():
        raise MineruError(f"PDF not found: {pdf}")
    out_dir.mkdir(parents=True, exist_ok=True)

    binary = resolve_mineru_bin()
    cmd = [binary, "-p", str(pdf), "-o", str(out_dir), "-b", backend, "-l", lang]
    env = {**os.environ}
    if cpu:
        env["CUDA_VISIBLE_DEVICES"] = ""

    _log.info("running MinerU: %s", " ".join(cmd))
    try:
        proc = subprocess.run(
            cmd,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise MineruError(f"MinerU timed out after {timeout_s}s on {pdf.name}") from exc
    except OSError as exc:
        raise MineruError(f"failed to launch MinerU ({binary}): {exc}") from exc

    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip()[-600:]
        raise MineruError(f"MinerU exited {proc.returncode} on {pdf.name}: {tail}")

    return _discover_outputs(out_dir)


__all__ = ["MineruResult", "resolve_mineru_bin", "run_mineru"]
