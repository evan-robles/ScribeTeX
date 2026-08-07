import pytest
from scribetex import server
from scribetex.placement import existing_note_labels


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.setenv("SCRIBETEX_NOTES_ROOT", str(tmp_path))
    return tmp_path


def test_resolve_new_course(root):
    r = server._resolve_placement("Organic Chemistry", "Oct 3 2025", "note.pdf")
    assert r["course_status"] == "new"
    assert r["date_iso"] == "2025-10-03"
    assert r["date_display"] == "October 3, 2025"
    assert r["duplicate"] is False


def test_resolve_bad_date(root):
    r = server._resolve_placement("Whatever", "someday", "n.pdf")
    assert r["match_confidence"] == "low"
    assert r["date_iso"] is None


def test_write_scaffolds_and_inserts(root):
    body = "\\section{Techniques}\n\\subsection{NMR}\nhello"
    r = server._write_section("Organic Chemistry", body, "2025-10-03",
                              source_name="nmr.pdf")
    assert r["written"] is True
    assert r["compiled"] is False
    main_tex = (root / "Organic-Chemistry" / "main.tex").read_text()
    assert existing_note_labels(main_tex) == ["2025-10-03:nmr-pdf"]
    # the LLM's own headings are carried through
    assert r"\section{Techniques}" in main_tex
    assert r"\subsection{NMR}" in main_tex
    assert "hello" in main_tex


def test_write_then_resolve_sees_existing_course(root):
    server._write_section("Organic Chemistry", "\\section{T}\nx", "2025-10-03",
                          source_name="a.pdf")
    r = server._resolve_placement("organic chemistry", "2025-10-10", "b.pdf")
    assert r["course_status"] == "existing"
    assert r["course"] == "Organic Chemistry"


def test_write_duplicate_warns(root):
    server._write_section("Organic Chemistry", "\\section{T}\nx", "2025-10-03",
                          source_name="nmr.pdf")
    r = server._write_section("Organic Chemistry", "\\section{T}\ny", "2025-10-03",
                              source_name="nmr.pdf")
    assert r["written"] is False
    assert "already exists" in r["error"].lower() or "duplicate" in r["error"].lower()


def test_resolve_duplicate_flag(root):
    server._write_section("Organic Chemistry", "\\section{T}\nx", "2025-10-03",
                          source_name="nmr.pdf")
    r = server._resolve_placement("organic chemistry", "2025-10-03", "nmr.pdf")
    assert r["course_status"] == "existing"
    assert r["duplicate"] is True


def test_resolve_same_date_different_file_not_duplicate(root):
    server._write_section("Organic Chemistry", "\\section{T}\nx", "2025-10-03",
                          source_name="one.pdf")
    r = server._resolve_placement("organic chemistry", "2025-10-03", "two.pdf")
    assert r["duplicate"] is False


def test_prepare_note_reports_root_and_courses(root):
    server._write_section("Organic Chemistry", "\\section{T}\nx", "2025-10-03",
                          source_name="a.pdf")
    import fitz
    pdf = root / "note.pdf"
    d = fitz.open(); d.new_page(); d.save(str(pdf)); d.close()
    r = server._prepare_note("file", str(pdf))
    assert len(r["page_images"]) == 1
    assert r["notes_root"] == str(root)
    assert "Organic Chemistry" in r["known_courses"]
    assert "section" in r["brief"].lower()


def test_write_uses_course_number_in_scaffold(root):
    server._write_section("Organic Chemistry", "\\section{C}\nbody", "2025-10-03",
                          source_name="a.pdf", course_number="CHEM 22100")
    main_tex = (root / "Organic-Chemistry" / "main.tex").read_text()
    assert r"\fancyhead[R]{CHEM 22100}" in main_tex
    assert "CHEM 22100" in main_tex
    assert r"{\Huge\bfseries Organic Chemistry\par}" in main_tex


def test_prepare_note_accepts_path_via_source_fallback(root):
    # Robustness for a flaky MCP client that only exposes `source`: passing the
    # PATH as source (with no ref) must still render pages.
    import fitz
    pdf = root / "fallback.pdf"
    d = fitz.open(); d.new_page(); d.save(str(pdf)); d.close()
    r = server._prepare_note(source=str(pdf))
    assert len(r["page_images"]) == 1
    assert "error" not in r


def test_prepare_note_goodnotes_alias(root):
    import fitz
    pdf = root / "gn.pdf"
    d = fitz.open(); d.new_page(); d.save(str(pdf)); d.close()
    r = server._prepare_note("goodnotes", str(pdf))
    assert len(r["page_images"]) == 1
    assert "error" not in r


def test_write_rejects_dangerous_body(root):
    r = server._write_section("Bio", "ok text \\write18{rm -rf ~} more",
                              "2026-08-06", source_name="a.pdf")
    assert r["written"] is False
    assert "disallowed" in r["error"].lower()
    assert not (root / "Bio" / "main.tex").exists()  # nothing written


def test_write_rejects_end_document_in_body(root):
    r = server._write_section("Bio", "text \\end{document} trailing",
                              "2026-08-06", source_name="a.pdf")
    assert r["written"] is False


def test_scaffold_escapes_untrusted_course_name(root):
    # The course name lands on the title page verbatim; a `}` must not break out.
    server._write_section("Bad}\\input{/etc/passwd", "\\section{T}\nbody",
                          "2026-08-06", source_name="a.pdf", course_number="N")
    from scribetex.classify import course_slug
    main_tex = (root / course_slug("Bad}\\input{/etc/passwd") / "main.tex").read_text()
    assert "\\input{/etc/passwd}" not in main_tex
    assert "\\}" in main_tex


def test_write_rejects_empty_course_slug(root):
    r = server._write_section("!!!", "\\section{T}\nbody", "2026-08-06",
                              source_name="a.pdf")
    assert r["written"] is False
    assert "usable filename" in r["error"]


def test_concurrent_writes_do_not_lose_notes(root):
    # Two threads filing DIFFERENT source files into the SAME course must both
    # land — the per-target lock + atomic replace prevents last-writer-wins loss.
    import threading
    server._write_section("Bio", "\\section{S}\nb0", "2026-08-06",
                          source_name="n0.pdf")  # scaffold once

    def worker(i):
        server._write_section("Bio", f"\\section{{S}}\nbody{i}", "2026-08-06",
                              source_name=f"n{i}.pdf")

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(1, 9)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    main_tex = (root / "Bio" / "main.tex").read_text()
    for i in range(1, 9):
        assert f"body{i}" in main_tex, f"lost note body{i}"
