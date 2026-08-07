import pytest
from scribetex import writer
from scribetex.placement import ENTRIES_START, ENTRIES_END

EMPTY = f"HEAD\n{ENTRIES_START}\n{ENTRIES_END}\nTAIL\n"


def _insert(tex, body, date, source, dup="warn"):
    return writer.insert_note(tex, body, date, source, dup)


def test_same_day_different_file_not_duplicate():
    tex, _ = _insert(EMPTY, "\\section{Receptors}\nb1", "2026-08-06", "bio1.pdf")
    # Same date, DIFFERENT source file -> must NOT be a duplicate.
    tex2, _ = _insert(tex, "\\section{Muscles}\nb2", "2026-08-06", "bio2.pdf")
    assert "b1" in tex2 and "b2" in tex2
    assert r"\label{note:2026-08-06:bio1-pdf}" in tex2
    assert r"\label{note:2026-08-06:bio2-pdf}" in tex2


def test_same_file_same_day_is_duplicate():
    tex, _ = _insert(EMPTY, "\\section{A}\nb1", "2026-08-06", "bio.pdf")
    with pytest.raises(writer.DuplicateNoteError) as ei:
        _insert(tex, "\\section{A}\nb2", "2026-08-06", "bio.pdf")
    msg = str(ei.value)
    assert "bio.pdf" in msg and "2026-08-06" in msg


def test_replace_collapses_only_matching_file():
    tex, _ = _insert(EMPTY, "\\section{A}\nb1", "2026-08-06", "bio.pdf")
    tex, _ = _insert(tex, "\\section{B}\nkeep-me", "2026-08-06", "other.pdf")
    tex2, summary = _insert(tex, "\\section{A}\nb1-v2", "2026-08-06", "bio.pdf",
                            dup="replace")
    assert "b1-v2" in tex2
    assert "b1" not in tex2.replace("b1-v2", "")  # old bio.pdf body gone
    assert "keep-me" in tex2                        # other.pdf untouched
    assert "replaced" in summary


def test_append_adds_second_block_same_file():
    tex, _ = _insert(EMPTY, "\\section{A}\nb1", "2026-08-06", "bio.pdf")
    tex2, _ = _insert(tex, "\\section{A}\nb2", "2026-08-06", "bio.pdf", dup="append")
    assert tex2.count(r"\label{note:2026-08-06:bio-pdf}") == 2
