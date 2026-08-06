from scribe_tex.placement import (
    ENTRIES_START, ENTRIES_END, existing_dates, section_block, plan_insertion,
)

EMPTY = f"""\\begin{{document}}
{ENTRIES_START}
{ENTRIES_END}
\\end{{document}}
"""


def _doc_with(dates):
    blocks = "\n".join(
        section_block(d, d, f"body {d}") for d in dates
    )
    return f"\\begin{{document}}\n{ENTRIES_START}\n{blocks}\n{ENTRIES_END}\n\\end{{document}}\n"


def test_section_block_has_label_and_markers():
    blk = section_block("2025-10-03", "October 3, 2025", "hi")
    assert r"\section{October 3, 2025}" in blk
    assert r"\label{sec:2025-10-03}" in blk
    assert "begin transcribed body" in blk
    assert "end transcribed body" in blk
    assert "hi" in blk


def test_existing_dates_in_order():
    doc = _doc_with(["2025-09-28", "2025-10-03"])
    assert existing_dates(doc) == ["2025-09-28", "2025-10-03"]


def test_first_insertion_into_empty():
    p = plan_insertion(EMPTY, "2025-10-03")
    assert p["duplicate"] is False
    assert p["after_date"] is None
    # insert_index points just after the ENTRIES_START line
    assert EMPTY[:p["insert_index"]].rstrip().endswith(ENTRIES_START)


def test_insert_between_keeps_order():
    doc = _doc_with(["2025-09-28", "2025-10-10"])
    p = plan_insertion(doc, "2025-10-03")
    assert p["duplicate"] is False
    assert p["after_date"] == "2025-09-28"


def test_insert_before_all():
    doc = _doc_with(["2025-10-03"])
    p = plan_insertion(doc, "2025-09-01")
    assert p["after_date"] is None


def test_insert_after_all():
    doc = _doc_with(["2025-09-01", "2025-10-03"])
    p = plan_insertion(doc, "2025-12-01")
    assert p["after_date"] == "2025-10-03"


def test_duplicate_detected():
    doc = _doc_with(["2025-10-03"])
    p = plan_insertion(doc, "2025-10-03")
    assert p["duplicate"] is True


def test_insert_is_order_independent():
    # Build a document whose blocks are NOT in ascending document order.
    from scribe_tex.placement import section_block, ENTRIES_START, ENTRIES_END
    blocks = "\n".join(section_block(d, d, f"body {d}")
                       for d in ["2025-10-10", "2025-09-01", "2025-09-28"])
    doc = f"\\begin{{document}}\n{ENTRIES_START}\n{blocks}\n{ENTRIES_END}\n\\end{{document}}\n"
    p = plan_insertion(doc, "2025-10-03")
    assert p["duplicate"] is False
    assert p["after_date"] == "2025-09-28"  # latest date strictly earlier than 10-03, by value
