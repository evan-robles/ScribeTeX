"""Crop a rendered page region into a course's ExtFiles/ for \\includegraphics."""
from __future__ import annotations
import re
import tempfile
from pathlib import Path

from .classify import course_slug
from .config import notes_root


def sanitize_name(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_-]+", "-", (name or "")).strip("-")
    return s or "figure"


def _page_image_allowed(page: Path, base: Path) -> bool:
    """Whether a page_image path is permitted: its resolved (symlink-followed)
    real path must sit under the notes root, or under a scribetex render dir
    (a ``scribetex_*`` directory inside the system temp dir). This guards
    crop_to_extfiles from reading an arbitrary caller-supplied path
    (confused-deputy): legitimate pages come only from prepare_note, which
    renders/stages every page under one of these roots."""
    rp = page.resolve()
    notes = Path(base).resolve()
    try:
        rp.relative_to(notes)
        return True
    except ValueError:
        pass
    tmp = Path(tempfile.gettempdir()).resolve()
    try:
        rel = rp.relative_to(tmp)
    except ValueError:
        return False
    # First path component under the temp dir must be a scribetex render dir.
    return bool(rel.parts) and rel.parts[0].startswith("scribetex_")


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
    base = (root if root is not None else notes_root())
    if not _page_image_allowed(page, base):
        raise ValueError(
            "page_image must be a rendered page from prepare_note "
            "(under a scribetex_* temp dir) or a file under the notes root; "
            f"refusing to read {page}"
        )
    x0, y0, x1, y1 = validate_bbox(bbox)
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
