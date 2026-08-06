import pytest
from scribe_tex.writer import (
    insert_section, DuplicateDateError, MalformedDocumentError,
)
from scribe_tex.placement import ENTRIES_START, ENTRIES_END, existing_dates

BASE = f"\\begin{{document}}\n{ENTRIES_START}\n{ENTRIES_END}\n\\end{{document}}\n"


def test_insert_first_section():
    out, summary = insert_section(BASE, "2025-10-03", "hello")
    assert existing_dates(out) == ["2025-10-03"]
    assert r"\section{October 3, 2025}" in out
    assert "hello" in out
    assert "inserted" in summary.lower()


def test_insert_keeps_date_order():
    out, _ = insert_section(BASE, "2025-10-10", "b")
    out, _ = insert_section(out, "2025-09-28", "a")
    out, _ = insert_section(out, "2025-10-03", "c")
    assert existing_dates(out) == ["2025-09-28", "2025-10-03", "2025-10-10"]


def test_duplicate_warn_raises():
    out, _ = insert_section(BASE, "2025-10-03", "x")
    with pytest.raises(DuplicateDateError):
        insert_section(out, "2025-10-03", "y", on_duplicate="warn")


def test_duplicate_replace_swaps_body():
    out, _ = insert_section(BASE, "2025-10-03", "OLD")
    out, _ = insert_section(out, "2025-10-03", "NEW", on_duplicate="replace")
    assert "NEW" in out and "OLD" not in out
    assert existing_dates(out) == ["2025-10-03"]


def test_duplicate_append_adds_second():
    out, _ = insert_section(BASE, "2025-10-03", "first")
    out, _ = insert_section(out, "2025-10-03", "second", on_duplicate="append")
    assert existing_dates(out) == ["2025-10-03", "2025-10-03"]
    assert "first" in out and "second" in out


def test_malformed_missing_markers_raises():
    with pytest.raises(MalformedDocumentError):
        insert_section("\\begin{document}\n\\end{document}\n", "2025-10-03", "x")
