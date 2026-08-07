import pytest
from scribetex import server
from scribetex.classify import match_course


def _course(tmp_path, monkeypatch):
    monkeypatch.setenv("SCRIBETEX_NOTES_ROOT", str(tmp_path))


def test_resolve_duplicate_matches_write_outcome(tmp_path, monkeypatch):
    _course(tmp_path, monkeypatch)
    # First write scaffolds + inserts.
    r1 = server._write_section("Bio", "\\section{Receptors}\nb1", "2026-08-06",
                               source_name="bio1.pdf", course_number="BIOS 20200")
    assert r1["written"] is True

    # Same date, DIFFERENT source file: resolve says not-duplicate AND write succeeds.
    res = server._resolve_placement("Bio", "2026-08-06", "bio2.pdf")
    assert res["duplicate"] is False
    r2 = server._write_section("Bio", "\\section{Muscles}\nb2", "2026-08-06",
                               source_name="bio2.pdf", course_number="BIOS 20200")
    assert r2["written"] is True

    # Same date + same source file: resolve says duplicate AND write refuses.
    res2 = server._resolve_placement("Bio", "2026-08-06", "bio1.pdf")
    assert res2["duplicate"] is True
    r3 = server._write_section("Bio", "\\section{Receptors}\nb1-again", "2026-08-06",
                               source_name="bio1.pdf", course_number="BIOS 20200")
    assert r3["written"] is False


def test_resolve_reports_course_and_date(tmp_path, monkeypatch):
    _course(tmp_path, monkeypatch)
    res = server._resolve_placement("Bio", "2026-08-06", "bio.pdf")
    assert res["course"] == "Bio"
    assert res["date_iso"] == "2026-08-06"


def test_match_course_exact_name_is_high_confidence():
    # A single-word course name is an exact case-insensitive match to itself,
    # so it must short-circuit to high confidence.
    assert match_course("Bio", ["Bio"]) == ("Bio", "high")
    assert match_course("bio", ["Bio"]) == ("Bio", "high")
    # A genuine non-match still behaves as before.
    assert match_course("Bio", ["Chem"])[0] is None
