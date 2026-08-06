import pytest
from scribetex import server
from scribetex.writer import insert_note, DuplicateNoteError
from scribetex.classify import match_course


def _course(tmp_path, monkeypatch):
    monkeypatch.setenv("SCRIBETEX_NOTES_ROOT", str(tmp_path))


def test_resolve_duplicate_matches_write_outcome(tmp_path, monkeypatch):
    _course(tmp_path, monkeypatch)
    # First write scaffolds + inserts.
    r1 = server._write_section("Bio", "Receptors", "Receptors", "b1", "2026-08-06", "BIOS 20200")
    assert r1["written"] is True

    # Same date, DIFFERENT subsection: resolve says not-duplicate AND write succeeds.
    res = server._resolve_placement("Bio", "Muscles and Movement", "Muscles", "2026-08-06")
    assert res["duplicate"] is False
    r2 = server._write_section("Bio", "Muscles and Movement", "Muscles", "b2", "2026-08-06", "BIOS 20200")
    assert r2["written"] is True

    # Same date + section + subsection: resolve says duplicate AND write refuses.
    res2 = server._resolve_placement("Bio", "Receptors", "Receptors", "2026-08-06")
    assert res2["duplicate"] is True
    r3 = server._write_section("Bio", "Receptors", "Receptors", "b1-again", "2026-08-06", "BIOS 20200")
    assert r3["written"] is False


def test_resolve_reports_subsection_in_payload(tmp_path, monkeypatch):
    _course(tmp_path, monkeypatch)
    res = server._resolve_placement("Bio", "Receptors", "Receptors", "2026-08-06")
    assert res["subsection_title"] == "Receptors"


def test_match_course_exact_name_is_high_confidence():
    # A single-word course name is an exact case-insensitive match to itself,
    # so it must short-circuit to high confidence even though the old
    # token-overlap scoring alone would call it "low" (single common word, no
    # digit) and collapse to (None, "none").
    assert match_course("Bio", ["Bio"]) == ("Bio", "high")
    assert match_course("bio", ["Bio"]) == ("Bio", "high")
    # A genuine non-match still behaves as before.
    assert match_course("Bio", ["Chem"])[0] is None
