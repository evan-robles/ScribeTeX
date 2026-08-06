"""FileSource: render a local PDF/image note export to page PNGs."""
from __future__ import annotations
import tempfile
from pathlib import Path

from .base import register

_IMAGE_EXTS = {".png", ".jpg", ".jpeg"}


class FileSource:
    def fetch_pages(self, ref: str) -> list[Path]:
        path = Path(ref).expanduser()
        if not path.exists():
            raise FileNotFoundError(path)
        ext = path.suffix.lower()
        if ext in _IMAGE_EXTS:
            return [path]
        if ext != ".pdf":
            raise ValueError(f"unsupported note file type: {ext}")
        import fitz  # PyMuPDF
        out_dir = Path(tempfile.mkdtemp(prefix="scribe_tex_"))
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
