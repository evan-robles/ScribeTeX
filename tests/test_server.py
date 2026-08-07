import pytest
from scribetex import server
from scribetex.placement import existing_sections, existing_note_labels


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.setenv("SCRIBETEX_NOTES_ROOT", str(tmp_path))
    return tmp_path


def test_resolve_new_course(root):
    r = server._resolve_placement("Organic Chemistry", "Techniques", "NMR",
                                  "Oct 3 2025")
    assert r["course_status"] == "new"
    assert r["section_title"] == "Techniques"
    assert r["subsection_title"] == "NMR"
    assert r["date_iso"] == "2025-10-03"
    assert r["date_display"] == "October 3, 2025"
    assert r["duplicate"] is False


def test_resolve_bad_date(root):
    r = server._resolve_placement("Whatever", "Topic", "Sub", "someday")
    assert r["match_confidence"] == "low"
    assert r["date_iso"] is None


def test_write_scaffolds_and_inserts(root):
    r = server._write_section("Organic Chemistry", "Techniques", "NMR",
                              "hello", "2025-10-03")
    assert r["written"] is True
    assert r["compiled"] is False
    main_tex = (root / "Organic-Chemistry" / "main.tex").read_text()
    assert existing_sections(main_tex) == ["Techniques"]
    assert existing_note_labels(main_tex) == ["2025-10-03:techniques:nmr"]
    assert "hello" in main_tex
    assert r"\subsection{NMR}" in main_tex


def test_write_then_resolve_sees_existing_course_and_section(root):
    server._write_section("Organic Chemistry", "Techniques", "NMR", "x",
                          "2025-10-03")
    r = server._resolve_placement("organic chemistry", "Techniques", "NMR",
                                  "2025-10-10")
    assert r["course_status"] == "existing"
    assert r["course"] == "Organic Chemistry"
    assert r["section_status"] == "existing"
    assert "Techniques" in r["existing_sections"]


def test_resolve_new_section_in_existing_course(root):
    server._write_section("Organic Chemistry", "Techniques", "NMR", "x",
                          "2025-10-03")
    r = server._resolve_placement("organic chemistry", "Mechanisms", "Addition",
                                  "2025-10-10")
    assert r["course_status"] == "existing"
    assert r["section_status"] == "new"


def test_write_duplicate_warns(root):
    server._write_section("Organic Chemistry", "Techniques", "NMR", "x",
                          "2025-10-03")
    r = server._write_section("Organic Chemistry", "Techniques", "NMR", "y",
                              "2025-10-03")
    assert r["written"] is False
    assert "already exists" in r["error"].lower() or "duplicate" in r["error"].lower()


def test_resolve_duplicate_flag(root):
    server._write_section("Organic Chemistry", "Techniques", "NMR", "x",
                          "2025-10-03")
    r = server._resolve_placement("organic chemistry", "Techniques", "NMR",
                                  "2025-10-03")
    assert r["course_status"] == "existing"
    assert r["duplicate"] is True


def test_prepare_note_reports_root_and_courses(root):
    server._write_section("Organic Chemistry", "Techniques", "NMR", "x",
                          "2025-10-03")
    import fitz
    pdf = root / "note.pdf"
    d = fitz.open(); d.new_page(); d.save(str(pdf)); d.close()
    r = server._prepare_note("file", str(pdf))
    assert len(r["page_images"]) == 1
    assert r["notes_root"] == str(root)
    assert "Organic Chemistry" in r["known_courses"]
    assert "section" in r["brief"].lower()


def test_write_uses_course_number_in_scaffold(root):
    server._write_section("Organic Chemistry", "Characterization", "NMR",
                          "body", "2025-10-03", course_number="CHEM 22100")
    main_tex = (root / "Organic-Chemistry" / "main.tex").read_text()
    # course number appears in the running header and the title page
    assert r"\fancyhead[R]{CHEM 22100}" in main_tex
    assert "CHEM 22100" in main_tex
    # course name is the big title
    assert r"{\Huge\bfseries Organic Chemistry\par}" in main_tex


def test_prepare_note_goodnotes_alias(root):
    import fitz
    pdf = root / "gn.pdf"
    d = fitz.open(); d.new_page(); d.save(str(pdf)); d.close()
    r = server._prepare_note("goodnotes", str(pdf))
    assert len(r["page_images"]) == 1
    assert "error" not in r


def test_write_escapes_latex_specials_in_titles(root):
    # Untrusted titles must be escaped so a `}` can't break out of \section{}.
    server._write_section("Bio", "Sneaky}\\input{/etc/passwd}", "Sub{x}",
                          "safe body", "2026-08-06")
    main_tex = (root / "Bio" / "main.tex").read_text()
    # The raw breakout must NOT appear; the escaped form must.
    assert "\\section{Sneaky}\\input{/etc/passwd}" not in main_tex
    assert "\\input{/etc/passwd}" not in main_tex
    assert "\\}" in main_tex  # brace was escaped


def test_write_rejects_dangerous_body(root):
    r = server._write_section("Bio", "Topic", "Sub",
                              "ok text \\write18{rm -rf ~} more", "2026-08-06")
    assert r["written"] is False
    assert "disallowed" in r["error"].lower()
    assert not (root / "Bio" / "main.tex").exists()  # nothing written


def test_write_rejects_end_document_in_body(root):
    r = server._write_section("Bio", "Topic", "Sub",
                              "text \\end{document} trailing", "2026-08-06")
    assert r["written"] is False


def test_scaffold_escapes_untrusted_course_name(root):
    # The course name lands on the title page verbatim; a `}` must not break out.
    server._write_section("Bad}\\input{/etc/passwd", "Topic", "Sub",
                          "body", "2026-08-06", course_number="N")
    # dir is slugged from the raw name; the title page must carry the escaped form
    from scribetex.classify import course_slug
    main_tex = (root / course_slug("Bad}\\input{/etc/passwd") / "main.tex").read_text()
    assert "\\input{/etc/passwd}" not in main_tex
    assert "\\}" in main_tex


def test_write_rejects_empty_course_slug(root):
    r = server._write_section("!!!", "Topic", "Sub", "body", "2026-08-06")
    assert r["written"] is False
    assert "usable filename" in r["error"]


def test_concurrent_writes_do_not_lose_notes(root):
    # Two threads filing different subsections into the SAME course must both
    # land — the per-target lock + atomic replace prevents last-writer-wins loss.
    import threading
    server._write_section("Bio", "Topic", "First", "b1", "2026-08-06")  # scaffold once

    def worker(i):
        server._write_section("Bio", "Topic", f"Sub{i}", f"body{i}",
                              "2026-08-06", on_duplicate="append")

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    main_tex = (root / "Bio" / "main.tex").read_text()
    for i in range(8):
        assert f"body{i}" in main_tex, f"lost note body{i}"
