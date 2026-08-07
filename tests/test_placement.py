from scribetex.placement import (
    ENTRIES_START, ENTRIES_END, BODY_BEGIN, BODY_END,
    existing_note_labels, note_block, note_key, append_index,
)

EMPTY = f"""\\begin{{document}}
{ENTRIES_START}
{ENTRIES_END}
\\end{{document}}
"""


def _doc_with(notes):
    """notes: list of (source_name, date_iso, body)."""
    body = "".join(note_block(b, d, s) for s, d, b in notes)
    return (f"\\begin{{document}}\n{ENTRIES_START}\n{body}{ENTRIES_END}\n"
            f"\\end{{document}}\n")


def test_note_key_is_date_plus_filename_slug():
    assert note_key("2025-10-03", "Bio 05.pdf") == "2025-10-03:bio-05-pdf"


def test_note_block_has_label_and_markers():
    blk = note_block("\\section{Area}\nbody", "2025-10-03", "Bio 05.pdf")
    assert r"\label{note:2025-10-03:bio-05-pdf}" in blk
    assert BODY_BEGIN in blk and BODY_END in blk
    # the LLM-authored heading is carried through verbatim
    assert r"\section{Area}" in blk
    assert "body" in blk


def test_note_block_carries_multiple_sections():
    body = "\\section{Area}\nA\n\\section{Volume}\nV"
    blk = note_block(body, "2025-01-01", "geo.pdf")
    assert r"\section{Area}" in blk and r"\section{Volume}" in blk


def test_existing_note_labels_in_order():
    doc = _doc_with([("a.pdf", "2025-01-01", "x"), ("b.pdf", "2025-02-01", "y")])
    assert existing_note_labels(doc) == [
        "2025-01-01:a-pdf", "2025-02-01:b-pdf",
    ]


def test_append_index_is_entries_end():
    assert EMPTY[append_index(EMPTY):].startswith(ENTRIES_END)


def test_list_notes_returns_key_date_sections():
    from scribetex.placement import list_notes
    doc = _doc_with([
        ("bio.pdf", "2026-08-06", "\\section{Receptors}\nx\n\\section{Muscles}\ny"),
        ("geo.pdf", "2026-08-07", "\\section{Area}\nz"),
    ])
    notes = list_notes(doc)
    assert [n["key"] for n in notes] == ["2026-08-06:bio-pdf", "2026-08-07:geo-pdf"]
    assert notes[0]["date"] == "2026-08-06"
    assert notes[0]["sections"] == ["Receptors", "Muscles"]
    assert notes[1]["sections"] == ["Area"]
