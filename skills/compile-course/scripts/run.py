#!/usr/bin/env python3
"""Compile a course's main.tex to PDF via the biblatex/biber toolchain.

Runs pdflatex -> biber -> pdflatex -> pdflatex in the course directory (the
template uses biblatex with the biber backend). This is the one place scribe-tex
compiles LaTeX; the MCP server itself stays write-only.

Usage:
    python run.py --course "<Course Name>"
    python run.py --path /abs/path/to/course/main.tex

Requires a local TeX toolchain (pdflatex + biber, e.g. MacTeX / TeX Live). Fails
gracefully with a clear message if absent. Requires the ``scribe_tex`` package
importable (the plugin sets PYTHONPATH).
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from scribe_tex.config import notes_root
from scribe_tex.classify import course_slug


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
    if main_tex is None or not main_tex.exists():
        print(json.dumps({"compiled": False,
                          "error": f"main.tex not found: {main_tex}"}, indent=2))
        return 1

    for tool in ("pdflatex", "biber"):
        if shutil.which(tool) is None:
            print(json.dumps({
                "compiled": False,
                "error": f"'{tool}' not found on PATH. Install a TeX distribution "
                         f"(MacTeX / TeX Live) to compile.",
            }, indent=2))
            return 1

    workdir = main_tex.parent
    stem = main_tex.stem
    steps = [
        ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", main_tex.name],
        ["biber", stem],
        ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", main_tex.name],
        ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", main_tex.name],
    ]
    for step in steps:
        proc = subprocess.run(step, cwd=workdir, capture_output=True, text=True)
        if proc.returncode != 0:
            tail = "\n".join((proc.stdout or proc.stderr).splitlines()[-25:])
            print(json.dumps({
                "compiled": False,
                "failed_step": " ".join(step),
                "log_tail": tail,
            }, indent=2))
            return 1

    pdf = workdir / f"{stem}.pdf"
    print(json.dumps({
        "compiled": True,
        "pdf": str(pdf),
        "exists": pdf.exists(),
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
