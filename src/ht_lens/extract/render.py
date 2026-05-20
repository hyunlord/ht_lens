"""Page PNG rendering with atomic writes."""

from __future__ import annotations

import contextlib
import os
import tempfile
from pathlib import Path

from ht_lens.extract._fitz import FitzDoc, render_png


def render_page_png(doc: FitzDoc, page_idx: int, out_path: Path, dpi: int = 200) -> int:
    """Render a single page (0-indexed) to ``out_path``. Returns byte size."""
    data = render_png(doc, page_idx, dpi)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        prefix=f"{out_path.stem}.", suffix=".png.tmp", dir=str(out_path.parent)
    )
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, out_path)
    except Exception:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp)
        raise
    return len(data)
