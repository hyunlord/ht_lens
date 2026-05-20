"""Page PNG rendering with atomic writes."""

from __future__ import annotations

import contextlib
import io
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from ht_lens.extract._fitz import FitzDoc, render_png


@dataclass(frozen=True)
class RenderResult:
    byte_size: int
    pixel_width: int
    pixel_height: int


def render_page_png(doc: FitzDoc, page_idx: int, out_path: Path, dpi: int = 200) -> RenderResult:
    """Render a single page (0-indexed) to ``out_path`` and report the pixel size."""
    data = render_png(doc, page_idx, dpi)
    with Image.open(io.BytesIO(data)) as img:
        pixel_w, pixel_h = img.size

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
    return RenderResult(byte_size=len(data), pixel_width=pixel_w, pixel_height=pixel_h)
