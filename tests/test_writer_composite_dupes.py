import pytest
from scribetex import writer
from scribetex.placement import ENTRIES_START, ENTRIES_END

EMPTY = f"HEAD\n{ENTRIES_START}\n{ENTRIES_END}\nTAIL\n"


def _insert(tex, section, sub, body, date, dup="warn"):
    return writer.insert_note(tex, section, sub, body, date, dup)


def test_same_day_different_topic_not_duplicate():
    tex, _ = _insert(EMPTY, "Receptors", "Receptors", "b1", "2026-08-06")
    # Same date, DIFFERENT section + subsection -> must NOT be a duplicate.
    tex2, summary = _insert(tex, "Muscles and Movement", "Muscles", "b2", "2026-08-06")
    assert r"\subsection{Receptors}" in tex2
    assert r"\subsection{Muscles}" in tex2
    assert "b1" in tex2 and "b2" in tex2


def test_exact_same_key_is_duplicate():
    tex, _ = _insert(EMPTY, "Receptors", "Receptors", "b1", "2026-08-06")
    with pytest.raises(writer.DuplicateNoteError) as ei:
        _insert(tex, "Receptors", "Receptors", "b2", "2026-08-06")
    msg = str(ei.value)
    assert "Receptors" in msg and "2026-08-06" in msg


def test_replace_collapses_only_matching_key():
    tex, _ = _insert(EMPTY, "Receptors", "Receptors", "b1", "2026-08-06")
    tex, _ = _insert(tex, "Muscles", "Muscles", "keep-me", "2026-08-06")
    tex2, summary = _insert(tex, "Receptors", "Receptors", "b1-v2", "2026-08-06", dup="replace")
    assert "b1-v2" in tex2
    assert "b1" not in tex2.replace("b1-v2", "")  # old Receptors body gone
    assert "keep-me" in tex2                        # Muscles untouched
    assert "replaced" in summary


def test_append_adds_second_subsection_same_key():
    tex, _ = _insert(EMPTY, "Receptors", "Receptors", "b1", "2026-08-06")
    tex2, _ = _insert(tex, "Receptors", "Receptors", "b2", "2026-08-06", dup="append")
    assert tex2.count(r"\label{note:2026-08-06:receptors:receptors}") == 2
