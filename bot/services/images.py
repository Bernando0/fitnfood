"""Downscale a photo and base64-encode it for the vision API."""
from __future__ import annotations

import base64
import io

from PIL import Image

MAX_SIDE = 1024  # resizing before the vision call is the main lever on input tokens


def to_jpeg_base64(raw: bytes) -> str:
    img = Image.open(io.BytesIO(raw))
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")

    w, h = img.size
    scale = min(1.0, MAX_SIDE / max(w, h))
    if scale < 1.0:
        img = img.resize((int(w * scale), int(h * scale)))

    out = io.BytesIO()
    img.save(out, format="JPEG", quality=85)
    return base64.standard_b64encode(out.getvalue()).decode("ascii")
