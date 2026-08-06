#!/usr/bin/env python3
"""Inventory the courses under the notes root.

For each course document, prints its topic sections and how many notes
(subsections carrying a note-label) it holds, as JSON.

Usage:
    python run.py

Self-locating: prepends ../../../src to sys.path, so no external PYTHONPATH is required.
"""
from __future__ import annotations

import json
import pathlib
import sys

_SRC = pathlib.Path(__file__).resolve().parents[3] / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from scribetex.config import notes_root
from scribetex.classify import course_slug
from scribetex.discovery import known_courses
from scribetex.placement import existing_sections, existing_note_labels


def main() -> int:
    root = notes_root()
    courses = []
    for name in known_courses(root):
        main_tex = root / course_slug(name) / "main.tex"
        try:
            text = main_tex.read_text(encoding="utf-8")
        except OSError:
            continue
        courses.append({
            "course": name,
            "path": str(main_tex),
            "sections": existing_sections(text),
            "note_count": len(existing_note_labels(text)),
        })

    print(json.dumps({
        "notes_root": str(root),
        "course_count": len(courses),
        "courses": courses,
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
