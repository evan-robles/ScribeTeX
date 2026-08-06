"""Crop a rendered page region into a course's ExtFiles/ for \\includegraphics."""
from __future__ import annotations
import re
from pathlib import Path

from .classify import course_slug
from .config import notes_root


def sanitize_name(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_-]+", "-", (name or "")).strip("-")
    return s or "figure"


def validate_bbox(bbox) -> tuple[float, float, float, float]:
    try:
        x0, y0, x1, y1 = (float(v) for v in bbox)
    except (TypeError, ValueError):
        raise ValueError("invalid bbox: expected [x0, y0, x1, y1] fractions in [0,1]")
    if not (0.0 <= x0 < x1 <= 1.0 and 0.0 <= y0 < y1 <= 1.0):
        raise ValueError(
            "invalid bbox: need 0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1; "
            f"got {bbox}"
        )
    return x0, y0, x1, y1


def crop_to_extfiles(page_image: str, bbox, course: str, name: str,
                     root: Path | None = None) -> dict:
    from PIL import Image
    page = Path(page_image).expanduser()
    if not page.exists():
        raise FileNotFoundError(f"page image not found: {page}")
    x0, y0, x1, y1 = validate_bbox(bbox)
    base = (root if root is not None else notes_root())
    ext_dir = Path(base) / course_slug(course) / "ExtFiles"
    ext_dir.mkdir(parents=True, exist_ok=True)

    img = Image.open(page)
    w, h = img.size
    box = (round(x0 * w), round(y0 * h), round(x1 * w), round(y1 * h))
    crop = img.crop(box)
    fname = f"{sanitize_name(name)}.png"
    out = ext_dir / fname
    crop.save(out)
    return {"saved": True, "filename": fname, "path": str(out)}
