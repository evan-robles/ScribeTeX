import pytest
from scribetex.writer import (
    insert_note, DuplicateNoteError, MalformedDocumentError,
)
from scribetex.placement import ENTRIES_START, ENTRIES_END, existing_note_labels

BASE = f"\\begin{{document}}\n{ENTRIES_START}\n{ENTRIES_END}\n\\end{{document}}\n"


def test_insert_appends_llm_authored_block():
    body = "\\section{Area}\nhello\n\\section{Volume}\nmore"
    out, summary = insert_note(BASE, body, "2025-10-03", "geo.pdf")
    # The note's own headings are carried through verbatim (one note, two sections).
    assert r"\section{Area}" in out and r"\section{Volume}" in out
    assert r"\label{note:2025-10-03:geo-pdf}" in out
    assert "hello" in out
    assert "added note" in summary.lower()


def test_second_note_appends_after_first():
    out, _ = insert_note(BASE, "\\section{A}\na", "2025-10-03", "one.pdf")
    out, _ = insert_note(out, "\\section{B}\nb", "2025-10-04", "two.pdf")
    assert existing_note_labels(out) == [
        "2025-10-03:one-pdf", "2025-10-04:two-pdf",
    ]
    assert "a" in out and "b" in out


def test_duplicate_label_warn_raises():
    out, _ = insert_note(BASE, "\\section{A}\nx", "2025-10-03", "note.pdf")
    with pytest.raises(DuplicateNoteError):
        insert_note(out, "\\section{A}\ny", "2025-10-03", "note.pdf",
                    on_duplicate="warn")


def test_duplicate_replace_collapses_to_one():
    out, _ = insert_note(BASE, "\\section{A}\nOLD", "2025-10-03", "note.pdf")
    out, _ = insert_note(out, "\\section{A}\nNEW", "2025-10-03", "note.pdf",
                         on_duplicate="replace")
    assert existing_note_labels(out) == ["2025-10-03:note-pdf"]
    assert "NEW" in out and "OLD" not in out


def test_duplicate_append_adds_second():
    out, _ = insert_note(BASE, "\\section{A}\nfirst", "2025-10-03", "note.pdf")
    out, _ = insert_note(out, "\\section{A}\nsecond", "2025-10-03", "note.pdf",
                         on_duplicate="append")
    assert existing_note_labels(out) == [
        "2025-10-03:note-pdf", "2025-10-03:note-pdf",
    ]
    assert "first" in out and "second" in out


def test_different_files_same_date_coexist():
    out, _ = insert_note(BASE, "\\section{A}\na", "2025-10-03", "one.pdf")
    out, _ = insert_note(out, "\\section{B}\nb", "2025-10-03", "two.pdf")
    assert existing_note_labels(out) == [
        "2025-10-03:one-pdf", "2025-10-03:two-pdf",
    ]


def test_malformed_missing_markers_raises():
    with pytest.raises(MalformedDocumentError):
        insert_note("\\begin{document}\n\\end{document}\n", "x", "2025-10-03",
                    "note.pdf")
