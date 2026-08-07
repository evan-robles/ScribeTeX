#!/usr/bin/env python3
"""Compile a course's main.tex to PDF via the biblatex/biber toolchain.

Runs pdflatex -> biber -> pdflatex -> pdflatex in the course directory (the
template uses biblatex with the biber backend). This is the one place ScribeTeX
compiles LaTeX; the MCP server itself stays write-only.

Usage:
    python run.py --course "<Course Name>"
    python run.py --path /abs/path/to/course/main.tex

Requires a local TeX toolchain (pdflatex + biber, e.g. MacTeX / TeX Live). Fails
gracefully with a clear message if absent. Self-locating: prepends
../../../src to sys.path, so no external PYTHONPATH is required.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from pathlib import Path

_SRC = pathlib.Path(__file__).resolve().parents[3] / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from scribetex.config import notes_root
from scribetex.classify import course_slug
from scribetex.compile import compile_course as _compile_course


def _resolve_main_tex(args) -> Path | None:
    if args.path:
        return Path(args.path).expanduser()
    return notes_root() / course_slug(args.course) / "main.tex"


def main() -> int:
    ap = argparse.ArgumentParser(description="Compile a course document to PDF.")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--course", help="Course name (resolved under the notes root).")
    g.add_argument("--path", help="Direct path to a course main.tex.")
    args = ap.parse_args()

    main_tex = _resolve_main_tex(args)
    result = _compile_course(main_tex)
    print(json.dumps(result, indent=2))
    return 0 if result.get("compiled") else 1


if __name__ == "__main__":
    sys.exit(main())
