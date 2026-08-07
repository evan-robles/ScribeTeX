"""Apply a note insertion to a course main.tex, returning new text + summary.

A note is a self-contained block of LLM-authored LaTeX (carrying its own
``\\section``/``\\subsection`` headings) appended into the ENTRIES region under a
hidden ``\\label{note:DATE:filename-slug}``. Re-filing the same source file
replaces its prior block rather than duplicating it.
"""
from __future__ import annotations

from .placement import (
    ENTRIES_START, ENTRIES_END, BODY_BEGIN, BODY_END,
    note_block, note_key, existing_note_labels, append_index,
)


class DuplicateNoteError(Exception):
    def __init__(self, date_iso: str, source_name: str):
        super().__init__(
            f"a note for source '{source_name}' on {date_iso} already exists"
        )
        self.date_iso = date_iso
        self.source_name = source_name


class MalformedDocumentError(Exception):
    pass


def _require_markers(main_tex: str) -> None:
    if ENTRIES_START not in main_tex or ENTRIES_END not in main_tex:
        raise MalformedDocumentError("ENTRIES markers not found")


def _replace_note(main_tex: str, body: str, date_iso: str, source_name: str) -> str:
    """Replace the single note block carrying ``\\label{note:key}`` in place.

    The block spans from its label line to the line after its BODY_END. The label
    is unique per (date, source-filename), so exactly one block matches. Content
    outside the block is untouched.
    """
    key = note_key(date_iso, source_name)
    label = f"\\label{{note:{key}}}"
    label_pos = main_tex.find(label)
    if label_pos == -1:
        # Nothing to replace; fall back to a plain append.
        idx = append_index(main_tex)
        block = note_block(body, date_iso, source_name)
        return main_tex[:idx] + block + main_tex[idx:]
    # Block starts at the label line; ends after the first BODY_END past it.
    end_pos = main_tex.index(BODY_END, label_pos)
    block_end = main_tex.index("\n", end_pos) + 1
    new_block = note_block(body, date_iso, source_name)
    return main_tex[:label_pos] + new_block + main_tex[block_end:]


def insert_note(main_tex: str, body: str, date_iso: str, source_name: str,
                on_duplicate: str = "warn") -> tuple[str, str]:
    """Insert a transcribed note block. Returns (new_main_tex, diff_summary)."""
    _require_markers(main_tex)

    key = note_key(date_iso, source_name)
    if key in existing_note_labels(main_tex):
        if on_duplicate == "warn":
            raise DuplicateNoteError(date_iso, source_name)
        if on_duplicate == "replace":
            new = _replace_note(main_tex, body, date_iso, source_name)
            return new, f"replaced note '{source_name}' ({date_iso})"
        if on_duplicate == "append":
            pass  # fall through to a second block with the same label
        else:
            raise ValueError(f"unknown on_duplicate: {on_duplicate}")

    idx = append_index(main_tex)
    block = note_block(body, date_iso, source_name)
    new = main_tex[:idx] + block + main_tex[idx:]
    return new, f"added note '{source_name}' ({date_iso})"
