#!/usr/bin/env python3
"""Prepare a handwritten note export for transcription.

Renders a note (PDF or image; GoodNotes/Notability/etc. exports) to page images
and prints the transcription brief, the notes root, and the known courses, so
the calling agent can read the images, transcribe to LaTeX, and then resolve +
write via the scribe-tex MCP tools.

Usage:
    python run.py <path-to-note.pdf-or-image> [--source file|goodnotes]

Requires the ``scribe_tex`` package importable (the plugin sets PYTHONPATH).
"""
from __future__ import annotations

import argparse
import json
import sys

from scribe_tex import server


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
