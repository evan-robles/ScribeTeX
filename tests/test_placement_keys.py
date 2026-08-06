# tests/test_placement_keys.py
from scribetex import placement as P


def test_note_slug_basic():
    assert P.note_slug("Muscles and Movement") == "muscles-and-movement"
    assert P.note_slug("  Réceptors!!  ") == "r-ceptors"
    assert P.note_slug("") == ""
    assert P.note_slug("---A---B---") == "a-b"


def test_note_key_composite():
    assert P.note_key("2026-08-06", "Muscles and Movement", "Muscles") == \
        "2026-08-06:muscles-and-movement:muscles"


def test_subsection_block_uses_composite_label():
    block = P.subsection_block("Muscles", "body text", "2026-08-06", "Muscles and Movement")
    assert r"\label{note:2026-08-06:muscles-and-movement:muscles}" in block
    assert "body text" in block
    assert r"\subsection{Muscles}" in block


def test_existing_note_labels_reads_composite_and_legacy():
    tex = (
        r"\label{note:2026-08-06:muscles-and-movement:muscles}" "\n"
        r"\label{note:2025-01-02}" "\n"
    )
    assert P.existing_note_labels(tex) == [
        "2026-08-06:muscles-and-movement:muscles",
        "2025-01-02",
    ]
