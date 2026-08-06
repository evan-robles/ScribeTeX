import pytest
from scribe_tex import server
from scribe_tex.placement import existing_dates


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.setenv("SCRIBE_TEX_NOTES_ROOT", str(tmp_path))
    return tmp_path


def test_resolve_new_course(root):
    r = server._resolve_placement("Organic Chemistry", "Oct 3 2025")
    assert r["course_status"] == "new"
    assert r["date_iso"] == "2025-10-03"
    assert r["date_display"] == "October 3, 2025"
    assert r["duplicate"] is False


def test_resolve_bad_date(root):
    r = server._resolve_placement("Whatever", "someday")
    assert r["match_confidence"] == "low"
    assert r["date_iso"] is None


def test_write_scaffolds_and_inserts(root):
    r = server._write_section("MATH 257 Linear Algebra", "2025-10-03", "hello")
    assert r["written"] is True
    assert r["compiled"] is False
    main_tex = (root / "MATH-257-Linear-Algebra" / "main.tex").read_text()
    assert existing_dates(main_tex) == ["2025-10-03"]
    assert "hello" in main_tex


def test_write_then_resolve_sees_existing(root):
    server._write_section("MATH 257 Linear Algebra", "2025-10-03", "x")
    r = server._resolve_placement("linear algebra", "2025-10-10")
    assert r["course_status"] == "existing"
    assert r["course"] == "MATH 257 Linear Algebra"
    assert r["insert_position"] == "after section dated 2025-10-03"


def test_write_duplicate_warns(root):
    server._write_section("MATH 257 Linear Algebra", "2025-10-03", "x")
    r = server._write_section("MATH 257 Linear Algebra", "2025-10-03", "y")
    assert r["written"] is False
    assert "duplicate" in r["error"].lower()


def test_prepare_note_reports_root_and_courses(root):
    server._write_section("MATH 257 Linear Algebra", "2025-10-03", "x")
    # use a tiny generated PDF via FileSource path
    import fitz
    pdf = root / "note.pdf"
    d = fitz.open(); d.new_page(); d.save(str(pdf)); d.close()
    r = server._prepare_note("file", str(pdf))
    assert len(r["page_images"]) == 1
    assert r["notes_root"] == str(root)
    assert "MATH 257 Linear Algebra" in r["known_courses"]
    assert "course" in r["brief"].lower()
