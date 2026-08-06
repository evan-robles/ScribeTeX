"""Discover existing course documents under the notes root."""
from __future__ import annotations
from pathlib import Path


def known_courses(root: Path) -> list[str]:
    if not root.exists():
        return []
    names = []
    for child in root.iterdir():
        if child.is_dir() and (child / "main.tex").exists():
            names.append(child.name.replace("-", " "))
    return sorted(names)
