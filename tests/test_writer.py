import pytest
from scribetex.writer import (
    insert_note, DuplicateNoteError, MalformedDocumentError,
)
from scribetex.placement import (
    ENTRIES_START, ENTRIES_END, existing_sections, existing_note_labels,
)

BASE = f"\\begin{{document}}\n{ENTRIES_START}\n{ENTRIES_END}\n\\end{{document}}\n"


def test_insert_creates_section_and_subsection():
    out, summary = insert_note(BASE, "Techniques", "NMR", "hello", "2025-10-03")
    assert existing_sections(out) == ["Techniques"]
    assert r"\subsection{NMR}" in out
    assert r"\label{note:2025-10-03:techniques:nmr}" in out
    assert "hello" in out
    assert "created section" in summary.lower()


def test_second_note_same_section_appends_within():
    out, _ = insert_note(BASE, "Techniques", "NMR", "a", "2025-10-03")
    out, summary = insert_note(out, "Techniques", "Chromatography", "b", "2025-10-04")
    # still exactly one section, now with two subsections
    assert existing_sections(out) == ["Techniques"]
    assert r"\subsection{NMR}" in out and r"\subsection{Chromatography}" in out
    assert "existing section" in summary.lower()


def test_new_section_appended_at_end():
    out, _ = insert_note(BASE, "Techniques", "NMR", "a", "2025-10-03")
    out, _ = insert_note(out, "Mechanisms", "Addition", "b", "2025-10-04")
    assert existing_sections(out) == ["Techniques", "Mechanisms"]


def test_duplicate_label_warn_raises():
    out, _ = insert_note(BASE, "Techniques", "NMR", "x", "2025-10-03")
    with pytest.raises(DuplicateNoteError):
        insert_note(out, "Techniques", "NMR", "y", "2025-10-03",
                    on_duplicate="warn")


def test_duplicate_replace_collapses_to_one():
    out, _ = insert_note(BASE, "Techniques", "NMR", "OLD", "2025-10-03")
    out, _ = insert_note(out, "Techniques", "NMR", "NEW", "2025-10-03",
                         on_duplicate="replace")
    assert existing_note_labels(out) == ["2025-10-03:techniques:nmr"]
    assert "NEW" in out and "OLD" not in out
    assert r"\subsection{NMR}" in out


def test_duplicate_append_adds_second():
    out, _ = insert_note(BASE, "Techniques", "NMR", "first", "2025-10-03")
    out, _ = insert_note(out, "Techniques", "NMR", "second", "2025-10-03",
                         on_duplicate="append")
    assert existing_note_labels(out) == [
        "2025-10-03:techniques:nmr", "2025-10-03:techniques:nmr",
    ]
    assert "first" in out and "second" in out


def test_malformed_missing_markers_raises():
    with pytest.raises(MalformedDocumentError):
        insert_note("\\begin{document}\n\\end{document}\n", "T", "S", "x",
                    "2025-10-03")
