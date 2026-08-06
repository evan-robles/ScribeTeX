import fitz
from scribe_tex import server
from scribe_tex.placement import existing_dates


def test_full_flow(tmp_path, monkeypatch):
    monkeypatch.setenv("SCRIBE_TEX_NOTES_ROOT", str(tmp_path))
    # 1. prepare a (blank) note PDF
    pdf = tmp_path / "linalg.pdf"
    d = fitz.open(); d.new_page(); d.save(str(pdf)); d.close()
    prep = server._prepare_note("file", str(pdf))
    assert prep["page_images"]

    # 2. agent "transcribes" + infers -> resolve
    res = server._resolve_placement("MATH 257 Linear Algebra", "Oct 3 2025")
    assert res["course_status"] == "new"
    assert res["date_iso"] == "2025-10-03"

    # 3. write after user confirms
    w = server._write_section(res["course"], res["date_iso"],
                              r"\subsection{Vector spaces} A field...")
    assert w["written"] is True

    # 4. a second, earlier date lands before the first
    server._write_section("MATH 257 Linear Algebra", "2025-09-28", "intro")
    main_tex = (tmp_path / "MATH-257-Linear-Algebra" / "main.tex").read_text()
    assert existing_dates(main_tex) == ["2025-09-28", "2025-10-03"]
