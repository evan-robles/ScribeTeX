from scribetex.placement import (
    ENTRIES_START, ENTRIES_END, BODY_BEGIN, BODY_END,
    existing_sections, existing_note_labels, subsection_block, section_block,
    plan_topic_insertion,
)

EMPTY = f"""\\begin{{document}}
{ENTRIES_START}
{ENTRIES_END}
\\end{{document}}
"""


def _doc_with(sections):
    """sections: list of (section_title, [(subtitle, date_iso), ...])."""
    parts = []
    for title, subs in sections:
        subtext = "".join(subsection_block(st, f"body {st}", d, title) for st, d in subs)
        parts.append(section_block(title, subtext))
    body = "".join(parts)
    return (f"\\begin{{document}}\n{ENTRIES_START}\n{body}{ENTRIES_END}\n"
            f"\\end{{document}}\n")


def test_subsection_block_has_label_and_markers():
    blk = subsection_block("Chemical Shift", "hi", "2025-10-03", "Techniques")
    assert r"\subsection{Chemical Shift}" in blk
    assert r"\label{note:2025-10-03:techniques:chemical-shift}" in blk
    assert BODY_BEGIN in blk and BODY_END in blk
    assert "hi" in blk


def test_section_block_wraps_subsections():
    sub = subsection_block("A", "x", "2025-01-01", "Techniques")
    blk = section_block("Techniques", sub)
    assert blk.startswith(r"\section{Techniques}")
    assert r"\subsection{A}" in blk


def test_existing_sections_in_order():
    doc = _doc_with([("Techniques", [("A", "2025-01-01")]),
                     ("Mechanisms", [("B", "2025-02-01")])])
    assert existing_sections(doc) == ["Techniques", "Mechanisms"]


def test_existing_note_labels():
    doc = _doc_with([("Techniques", [("A", "2025-01-01"), ("B", "2025-02-01")])])
    assert existing_note_labels(doc) == [
        "2025-01-01:techniques:a", "2025-02-01:techniques:b",
    ]


def test_plan_new_section_into_empty():
    p = plan_topic_insertion(EMPTY, "Techniques")
    assert p["section_exists"] is False
    # insert index is the ENTRIES_END marker offset
    assert EMPTY[p["insert_index"]:].startswith(ENTRIES_END)


def test_plan_existing_section_appends_within():
    doc = _doc_with([("Techniques", [("A", "2025-01-01")]),
                     ("Mechanisms", [("B", "2025-02-01")])])
    p = plan_topic_insertion(doc, "Techniques")
    assert p["section_exists"] is True
    # insertion lands before the next \section (Mechanisms), still inside Techniques
    after = doc[p["insert_index"]:]
    assert after.lstrip().startswith("\\section{Mechanisms}")


def test_plan_missing_section_targets_region_end():
    doc = _doc_with([("Techniques", [("A", "2025-01-01")])])
    p = plan_topic_insertion(doc, "Brand New Topic")
    assert p["section_exists"] is False
    assert doc[p["insert_index"]:].startswith(ENTRIES_END)
