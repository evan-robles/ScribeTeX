"""Pure LaTeX placement logic.

No I/O. All functions operate on the main.tex text as a string.

A transcribed note is appended into the ENTRIES region as a self-contained block
that carries its OWN heading structure (``\\section``/``\\subsection`` authored by
the transcribing LLM from the note's real topics — one note may span several
sections, e.g. "Area" and "Volume"). The server no longer imposes a single
section/subsection wrapper. Each block is tagged with a hidden
``\\label{note:DATE:filename-slug}`` used only for duplicate detection (re-filing
the same source file replaces its prior block).
"""
from __future__ import annotations
import re

ENTRIES_START = "% >>> ENTRIES"
ENTRIES_END = "% <<< ENTRIES"

BODY_BEGIN = "% --- begin transcribed body ---"
BODY_END = "% --- end transcribed body ---"

# Composite note key: date + source-filename slug.
_NOTE_LABEL_RE = re.compile(r"\\label\{note:(\d{4}-\d{2}-\d{2}:[a-z0-9-]*)\}")


def note_slug(text: str) -> str:
    """Lowercase, hyphenated, ASCII-safe reduction of text for a note key."""
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower())
    return s.strip("-")


def note_key(date_iso: str, source_name: str) -> str:
    """Duplicate-detection key: date + slug of the source filename.

    Re-filing the same source file (same name) on the same date replaces the
    prior block; two genuinely different notes on the same date coexist.
    """
    return f"{date_iso}:{note_slug(source_name)}"


def _entries_region(main_tex: str) -> tuple[int, int]:
    """(start, end) char offsets BETWEEN the ENTRIES markers (start = just after
    the ENTRIES_START line; end = index of the ENTRIES_END marker)."""
    start_marker = main_tex.index(ENTRIES_START)
    start = start_marker + len(ENTRIES_START)
    if start < len(main_tex) and main_tex[start] == "\n":
        start += 1
    end = main_tex.index(ENTRIES_END, start)
    return start, end


def existing_note_labels(main_tex: str) -> list[str]:
    """Composite note keys from ``\\label{note:...}`` anchors, in document order."""
    return _NOTE_LABEL_RE.findall(main_tex)


_SECTION_RE = re.compile(r"\\section\{(.*?)\}")


def document_sections(main_tex: str) -> list[str]:
    """All ``\\section`` titles within the ENTRIES region, in document order.

    Sections are authored by the LLM inside note blocks (not imposed by the
    server), so this reads whatever headings the filed notes contain — useful
    for an inventory/table-of-contents view."""
    start, end = _entries_region(main_tex)
    return _SECTION_RE.findall(main_tex[start:end])


def note_block(body: str, date_iso: str, source_name: str) -> str:
    """A self-contained note block: a hidden date+filename label followed by the
    LLM-authored LaTeX (which carries its own \\section/\\subsection headings),
    fenced by BODY markers so it can be located and replaced as a unit."""
    key = note_key(date_iso, source_name)
    return (
        f"\\label{{note:{key}}}\n"
        f"{BODY_BEGIN}\n"
        f"{body}\n"
        f"{BODY_END}\n"
    )


def append_index(main_tex: str) -> int:
    """Offset at the END of the ENTRIES region (the ENTRIES_END marker), where a
    new note block is appended."""
    _, end = _entries_region(main_tex)
    return end
