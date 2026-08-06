#!/usr/bin/env python3
"""Scaffold a new per-course LaTeX document (title page + preamble + sidecars).

Creates ``<notes-root>/<Course-Slug>/main.tex`` plus the ``main.bib`` and
``ExtFiles/`` sidecars the template's preamble references, so it compiles
standalone. Use this to set a course up before adding notes; ``process-note``
also scaffolds on first use, so this is optional.

Usage:
    python run.py --name "<Course Name>" --number "DEPT 10100" \
        [--author "Evan S. Robles"] [--affiliation "University of Chicago"]

Self-locating: prepends ../../../src to sys.path, so no external PYTHONPATH is required.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

_SRC = pathlib.Path(__file__).resolve().parents[3] / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from scribetex.config import notes_root
from scribetex.scaffold import (
    scaffold_course, DEFAULT_AUTHOR, DEFAULT_AFFILIATION,
)


def main() -> int:
    ap = argparse.ArgumentParser(description="Scaffold a new course document.")
    ap.add_argument("--name", required=True, help="Course name, e.g. '<Course Name>'.")
    ap.add_argument("--number", required=True, help="Course number, e.g. 'DEPT 10100'.")
    ap.add_argument("--author", default=DEFAULT_AUTHOR)
    ap.add_argument("--affiliation", default=DEFAULT_AFFILIATION)
    args = ap.parse_args()

    root = notes_root()
    try:
        path = scaffold_course(root, args.name, args.number,
                               author=args.author, affiliation=args.affiliation)
    except FileExistsError as e:
        print(json.dumps({"created": False,
                          "error": f"course already exists: {e}"}, indent=2))
        return 1

    print(json.dumps({
        "created": True,
        "course": args.name,
        "course_number": args.number,
        "main_tex": str(path),
        "notes_root": str(root),
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
