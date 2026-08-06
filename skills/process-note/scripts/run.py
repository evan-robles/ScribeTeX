#!/usr/bin/env python3
"""Prepare a handwritten note export for transcription.

Renders a note (PDF or image; GoodNotes/Notability/etc. exports) to page images
and prints the transcription brief, the notes root, and the known courses, so
the calling agent can read the images, transcribe to LaTeX, and then resolve +
write via the ScribeTeX MCP tools.

Usage:
    python run.py <path-to-note.pdf-or-image> [--source file|goodnotes]

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

from scribetex import server


def main() -> int:
    ap = argparse.ArgumentParser(description="Prepare a note export for transcription.")
    ap.add_argument("note", help="Path to the note PDF or image.")
    ap.add_argument("--source", default="file", choices=["file", "goodnotes"],
                    help="Note source type (default: file).")
    args = ap.parse_args()

    result = server._prepare_note(args.source, args.note)
    print(json.dumps(result, indent=2))
    return 1 if result.get("error") else 0


if __name__ == "__main__":
    sys.exit(main())
