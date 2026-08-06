"""Pure LaTeX placement logic for the topic-based model.

No I/O. All functions operate on the main.tex text as a string.

Documents are organized by TOPIC: content lives under top-level ``\\section``s
(e.g. "Characterization Techniques") within the ENTRIES region; each transcribed
note is one or more ``\\subsection``s placed under a chosen section. Every
inserted subsection carries a hidden ``\\label{note:YYYY-MM-DD}`` used only for
duplicate detection (the date no longer drives ordering).
"""
from __future__ import annotations
import re

ENTRIES_START = "% >>> ENTRIES"
ENTRIES_END = "% <<< ENTRIES"

BODY_BEGIN = "% --- begin transcribed body ---"
BODY_END = "% --- end transcribed body ---"

_SECTION_RE = re.compile(r"\\section\{(.*?)\}")
# Composite key: date, then optional :section-slug:subsection-slug. Legacy
# date-only labels (no colons after the date) are matched too.
_NOTE_LABEL_RE = re.compile(r"\\label\{note:(\d{4}-\d{2}-\d{2}(?::[a-z0-9-]*){0,2})\}")


def note_slug(text: str) -> str:
    """Lowercase, hyphenated, ASCII-safe reduction of a title for a note key."""
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower())
    return s.strip("-")


def note_key(date_iso: str, section_title: str, subsection_title: str) -> str:
    """Composite duplicate-detection key: date + section slug + subsection slug."""
    return f"{date_iso}:{note_slug(section_title)}:{note_slug(subsection_title)}"


def _entries_region(main_tex: str) -> tuple[int, int]:
    """Return (start, end) character offsets of the text BETWEEN the ENTRIES
    markers (start = just after the ENTRIES_START line; end = index of the
    ENTRIES_END marker)."""
    start_marker = main_tex.index(ENTRIES_START)
    start = start_marker + len(ENTRIES_START)
    if start < len(main_tex) and main_tex[start] == "\n":
        start += 1
    end = main_tex.index(ENTRIES_END, start)
    return start, end


def existing_sections(main_tex: str) -> list[str]:
    """Titles of top-level ``\\section``s within the ENTRIES region, in order."""
    start, end = _entries_region(main_tex)
    return _SECTION_RE.findall(main_tex[start:end])


def existing_note_labels(main_tex: str) -> list[str]:
    """Composite note keys from ``\\label{note:...}`` anchors, in document order.

    Each key is the text after ``note:`` — either a composite
    ``date:section-slug:subsection-slug`` or a legacy date-only label.
    """
    return _NOTE_LABEL_RE.findall(main_tex)


def subsection_block(title: str, body: str, date_iso: str, section_title: str) -> str:
    """A single ``\\subsection`` with a hidden composite note-label + body markers."""
    key = note_key(date_iso, section_title, title)
    return (
        f"\\subsection{{{title}}}\n"
        f"\\label{{note:{key}}}\n"
        f"{BODY_BEGIN}\n"
        f"{body}\n"
        f"{BODY_END}\n"
    )


def section_block(section_title: str, subsections_text: str) -> str:
    """A new top-level ``\\section`` wrapping already-rendered subsection text."""
    return f"\\section{{{section_title}}}\n{subsections_text}"


def plan_topic_insertion(main_tex: str, section_title: str) -> dict:
    """Decide where a note's subsections go for the given topic section.

    Returns ``{"section_exists": bool, "insert_index": int}``. When the section
    exists, ``insert_index`` is the offset at the END of that section (just
    before the next ``\\section`` or the ENTRIES_END marker), so new subsections
    append within it. When it does not exist, ``insert_index`` is the ENTRIES_END
    marker offset, so a new section is appended at the end of the region.
    """
    start, end = _entries_region(main_tex)
    region = main_tex[start:end]

    # Locate the target section by exact title within the region.
    target = f"\\section{{{section_title}}}"
    rel = region.find(target)
    if rel == -1:
        return {"section_exists": False, "insert_index": end}

    sec_abs = start + rel
    # The section runs until the next top-level \section after it, or the region end.
    next_rel = region.find("\\section{", rel + len(target))
    section_end = start + next_rel if next_rel != -1 else end
    return {"section_exists": True, "insert_index": section_end}
