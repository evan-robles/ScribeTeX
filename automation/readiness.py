"""Decide whether an inbox file is fully arrived and a valid note."""
from __future__ import annotations
import time
from pathlib import Path

SUPPORTED_EXTS = {".pdf", ".png", ".jpg", ".jpeg", ".heic"}


def is_stable(path, settle_seconds, size_fn=None, sleep_fn=None) -> bool:
    size_fn = size_fn or (lambda p: Path(p).stat().st_size)
    sleep_fn = sleep_fn or time.sleep
    first = size_fn(path)
    if first <= 0:
        return False
    sleep_fn(settle_seconds)
    return size_fn(path) == first


def is_valid_note(path) -> bool:
    p = Path(path)
    ext = p.suffix.lower()
    if ext not in SUPPORTED_EXTS:
        return False
    try:
        if p.stat().st_size == 0:
            return False
    except OSError:
        return False
    try:
        if ext == ".pdf":
            import fitz
            doc = fitz.open(str(p))
            try:
                return doc.page_count >= 1
            finally:
                doc.close()
        from PIL import Image
        with Image.open(p) as img:
            img.verify()
        return True
    except Exception:
        return False


def is_ready(path, settle_seconds, size_fn=None, sleep_fn=None) -> bool:
    return is_valid_note(path) and is_stable(
        path, settle_seconds, size_fn=size_fn, sleep_fn=sleep_fn
    )
