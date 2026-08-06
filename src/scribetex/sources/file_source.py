"""FileSource: render a local PDF/image note export to page PNGs."""
from __future__ import annotations
import tempfile
from pathlib import Path

from .base import register

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".heic"}


class FileSource:
    """Ingest a local note export. Handles a PDF (rendered to one PNG per page)
    or a single image (.png/.jpg/.jpeg/.heic) passed straight through. This
    covers GoodNotes and other iPad apps' standard PDF/image exports."""

    def fetch_pages(self, ref: str) -> list[Path]:
        if not (ref or "").strip():
            raise ValueError("no note path provided: pass ref=<path to PDF/image>")
        path = Path(ref).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"file not found: {path}")
        ext = path.suffix.lower()
        if ext in _IMAGE_EXTS:
            return [path]
        if ext != ".pdf":
            raise ValueError(
                f"unsupported extension '{ext}'; supported: pdf, png, jpg, jpeg, heic"
            )
        import fitz  # PyMuPDF
        out_dir = Path(tempfile.mkdtemp(prefix="scribetex_"))
        doc = fitz.open(str(path))
        pages: list[Path] = []
        try:
            for i, page in enumerate(doc):
                pix = page.get_pixmap(dpi=200)
                out = out_dir / f"p{i + 1}.png"
                pix.save(str(out))
                pages.append(out)
        finally:
            doc.close()
        return pages


register("file", FileSource)
# GoodNotes exports as PDF/PNG/JPG; a dedicated alias documents that intent.
register("goodnotes", FileSource)
