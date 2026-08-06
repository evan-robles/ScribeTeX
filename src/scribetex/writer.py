"""Apply a note insertion to a course main.tex, returning new text + summary.

Topic-based model: a note becomes a ``\\subsection`` placed under a chosen
top-level ``\\section``. If the section exists the subsection is appended within
it; otherwise a new section is created at the end of the ENTRIES region. Each
subsection carries a hidden ``\\label{note:YYYY-MM-DD}`` used for duplicate
detection.
"""
from __future__ import annotations

from .placement import (
    ENTRIES_START, ENTRIES_END, BODY_END,
    plan_topic_insertion, subsection_block, section_block, existing_note_labels,
    note_key,
)


class DuplicateNoteError(Exception):
    def __init__(self, date_iso: str, section_title: str, subsection_title: str):
        super().__init__(
            f"a note for section '{section_title}' / subsection "
            f"'{subsection_title}' on {date_iso} already exists"
        )
        self.date_iso = date_iso
        self.section_title = section_title
        self.subsection_title = subsection_title


class MalformedDocumentError(Exception):
    pass


def _require_markers(main_tex: str) -> None:
    if ENTRIES_START not in main_tex or ENTRIES_END not in main_tex:
        raise MalformedDocumentError("ENTRIES markers not found")


def _replace_note(main_tex: str, subsection_title: str, body: str,
                  date_iso: str, section_title: str) -> str:
    """Collapse every existing subsection carrying the composite
    ``\\label{note:key}`` into a single new subsection, positioned where the
    first such block sits. Other content is untouched.
    """
    key = note_key(date_iso, section_title, subsection_title)
    label = f"\\label{{note:{key}}}"
    spans = []
    search_from = 0
    while True:
        label_pos = main_tex.find(label, search_from)
        if label_pos == -1:
            break
        sub_pos = main_tex.rindex("\\subsection{", 0, label_pos)
        end_pos = main_tex.index(BODY_END, label_pos)
        block_end = main_tex.index("\n", end_pos) + 1
        spans.append((sub_pos, block_end))
        search_from = block_end

    result = main_tex
    for sub_pos, block_end in reversed(spans):
        result = result[:sub_pos] + result[block_end:]

    insert_at = spans[0][0]
    block = subsection_block(subsection_title, body, date_iso, section_title)
    return result[:insert_at] + block + result[insert_at:]


def insert_note(main_tex: str, section_title: str, subsection_title: str,
                body: str, date_iso: str,
                on_duplicate: str = "warn") -> tuple[str, str]:
    """Insert a transcribed note as a subsection under a topic section.

    Returns (new_main_tex, diff_summary).
    """
    _require_markers(main_tex)

    key = note_key(date_iso, section_title, subsection_title)
    if key in existing_note_labels(main_tex):
        if on_duplicate == "warn":
            raise DuplicateNoteError(date_iso, section_title, subsection_title)
        if on_duplicate == "replace":
            new = _replace_note(main_tex, subsection_title, body, date_iso, section_title)
            return new, f"replaced note '{subsection_title}' under '{section_title}' ({date_iso})"
        if on_duplicate == "append":
            pass  # fall through to normal insertion (adds another subsection)
        else:
            raise ValueError(f"unknown on_duplicate: {on_duplicate}")

    plan = plan_topic_insertion(main_tex, section_title)
    sub = subsection_block(subsection_title, body, date_iso, section_title)

    if plan["section_exists"]:
        idx = plan["insert_index"]
        new = main_tex[:idx] + sub + main_tex[idx:]
        summary = (f"added subsection '{subsection_title}' under existing "
                   f"section '{section_title}'")
    else:
        idx = plan["insert_index"]  # ENTRIES_END offset
        new_section = section_block(section_title, sub)
        new = main_tex[:idx] + new_section + main_tex[idx:]
        summary = (f"created section '{section_title}' with subsection "
                   f"'{subsection_title}'")
    return new, summary
