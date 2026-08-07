# tests/test_placement_keys.py
from scribetex import placement as P


def test_note_slug_basic():
    assert P.note_slug("Muscles and Movement") == "muscles-and-movement"
    assert P.note_slug("  Réceptors!!  ") == "r-ceptors"
    assert P.note_slug("") == ""
    assert P.note_slug("---A---B---") == "a-b"


def test_note_key_is_date_plus_filename():
    assert P.note_key("2026-08-06", "Bio 05.pdf") == "2026-08-06:bio-05-pdf"


def test_note_block_uses_date_filename_label():
    block = P.note_block("\\section{Muscles}\nbody text", "2026-08-06", "Bio 05.pdf")
    assert r"\label{note:2026-08-06:bio-05-pdf}" in block
    assert "body text" in block
    assert r"\section{Muscles}" in block  # LLM heading carried through


def test_existing_note_labels_reads_date_filename_keys():
    tex = (
        r"\label{note:2026-08-06:bio-05-pdf}" "\n"
        r"\label{note:2025-01-02:geo-pdf}" "\n"
    )
    assert P.existing_note_labels(tex) == [
        "2026-08-06:bio-05-pdf",
        "2025-01-02:geo-pdf",
    ]
