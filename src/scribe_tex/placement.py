"""Pure LaTeX placement logic: enumerate dates, build blocks, plan insertion.

No I/O. All functions operate on the main.tex text as a string.
"""
from __future__ import annotations
import re

ENTRIES_START = "% >>> ENTRIES"
ENTRIES_END = "% <<< ENTRIES"
_LABEL_RE = re.compile(r"\\label\{sec:(\d{4}-\d{2}-\d{2})\}")


def existing_dates(main_tex: str) -> list[str]:
    """ISO dates from \\label{sec:...} anchors, in document order."""
    return _LABEL_RE.findall(main_tex)


def section_block(date_iso: str, display: str, body: str) -> str:
    """Full section block for one class date."""
    return (
        f"\\section{{{display}}}\n"
        f"\\label{{sec:{date_iso}}}\n"
        f"% --- begin transcribed body ---\n"
        f"{body}\n"
        f"% --- end transcribed body ---\n"
    )


def plan_insertion(main_tex: str, date_iso: str) -> dict:
    """Decide where a new dated block should go to keep dates ascending.

    Returns {"duplicate", "after_date", "insert_index"}.
    """
    dates = existing_dates(main_tex)
    if date_iso in dates:
        return {"duplicate": True, "after_date": None, "insert_index": -1}

    earlier = [d for d in dates if d < date_iso]
    after_date = max(earlier) if earlier else None

    if after_date is None:
        # Insert immediately after the ENTRIES_START marker line.
        idx = main_tex.index(ENTRIES_START) + len(ENTRIES_START)
        # advance past the newline
        if idx < len(main_tex) and main_tex[idx] == "\n":
            idx += 1
        return {"duplicate": False, "after_date": None, "insert_index": idx}

    # Insert after the block whose label is `after_date`: find that label,
    # then the position right after its end-of-body marker (next end marker
    # after the label), else after the label line.
    label = f"\\label{{sec:{after_date}}}"
    label_pos = main_tex.index(label)
    end_marker = "% --- end transcribed body ---"
    end_pos = main_tex.find(end_marker, label_pos)
    if end_pos == -1:
        cut = main_tex.index("\n", label_pos) + 1
    else:
        cut = main_tex.index("\n", end_pos) + 1
    return {"duplicate": False, "after_date": after_date, "insert_index": cut}
