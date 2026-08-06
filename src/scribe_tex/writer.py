"""Apply a section insertion to a course main.tex, returning new text + summary."""
from __future__ import annotations

from .placement import (
    ENTRIES_START, ENTRIES_END, plan_insertion, section_block, existing_dates,
)
from .classify import display_date


class DuplicateDateError(Exception):
    def __init__(self, date_iso: str):
        super().__init__(f"section for {date_iso} already exists")
        self.date_iso = date_iso


class MalformedDocumentError(Exception):
    pass


def _require_markers(main_tex: str) -> None:
    if ENTRIES_START not in main_tex or ENTRIES_END not in main_tex:
        raise MalformedDocumentError("ENTRIES markers not found")


def _block(date_iso: str, body: str) -> str:
    return section_block(date_iso, display_date(date_iso), body)


def _replace_block(main_tex: str, date_iso: str, body: str) -> str:
    """Collapse every existing block for date_iso into a single new block,
    positioned where the first such block currently sits. Blocks for other
    dates are untouched and their relative order is preserved.
    """
    label = f"\\label{{sec:{date_iso}}}"
    end_marker = "% --- end transcribed body ---"

    spans = []
    search_from = 0
    while True:
        label_pos = main_tex.find(label, search_from)
        if label_pos == -1:
            break
        sec_pos = main_tex.rindex("\\section{", 0, label_pos)
        end_pos = main_tex.index(end_marker, label_pos)
        block_end = main_tex.index("\n", end_pos) + 1
        spans.append((sec_pos, block_end))
        search_from = block_end

    # Remove spans from last to first so earlier offsets stay valid, then
    # insert the single collapsed block at the position of the first span.
    result = main_tex
    for sec_pos, block_end in reversed(spans):
        result = result[:sec_pos] + result[block_end:]

    insert_at = spans[0][0]
    return result[:insert_at] + _block(date_iso, body) + result[insert_at:]


def insert_section(main_tex: str, date_iso: str, body: str,
                   on_duplicate: str = "warn") -> tuple[str, str]:
    _require_markers(main_tex)
    plan = plan_insertion(main_tex, date_iso)

    if plan["duplicate"]:
        if on_duplicate == "warn":
            raise DuplicateDateError(date_iso)
        if on_duplicate == "replace":
            new = _replace_block(main_tex, date_iso, body)
            return new, f"replaced section dated {date_iso}"
        if on_duplicate == "append":
            # Insert a second block right after the existing same-date block.
            label = f"\\label{{sec:{date_iso}}}"
            label_pos = main_tex.index(label)
            end_marker = "% --- end transcribed body ---"
            end_pos = main_tex.index(end_marker, label_pos)
            cut = main_tex.index("\n", end_pos) + 1
            new = main_tex[:cut] + _block(date_iso, body) + main_tex[cut:]
            return new, f"appended second section dated {date_iso}"
        raise ValueError(f"unknown on_duplicate: {on_duplicate}")

    idx = plan["insert_index"]
    new = main_tex[:idx] + _block(date_iso, body) + main_tex[idx:]
    where = "at start" if plan["after_date"] is None else f"after {plan['after_date']}"
    return new, f"inserted section dated {date_iso} ({where})"
