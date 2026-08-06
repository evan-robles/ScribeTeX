import fitz
from scribetex import server
from scribetex.placement import existing_sections, existing_note_labels


def test_full_flow(tmp_path, monkeypatch):
    monkeypatch.setenv("SCRIBETEX_NOTES_ROOT", str(tmp_path))
    # 1. prepare a (blank) note PDF
    pdf = tmp_path / "chem.pdf"
    d = fitz.open(); d.new_page(); d.save(str(pdf)); d.close()
    prep = server._prepare_note("file", str(pdf))
    assert prep["page_images"]

    # 2. agent "transcribes" + infers course/section/date -> resolve
    res = server._resolve_placement("Organic Chemistry", "Characterization", "Oct 3 2025")
    assert res["course_status"] == "new"
    assert res["date_iso"] == "2025-10-03"

    # 3. write after user confirms
    w = server._write_section(res["course"], res["section_title"], "NMR",
                              r"NMR is an analytical technique...", res["date_iso"])
    assert w["written"] is True

    # 4. a second note under a NEW section is appended at the end
    server._write_section("Organic Chemistry", "Reaction Mechanisms",
                          "Electrophilic Addition", "Markovnikov...", "2025-10-05")
    main_tex = (tmp_path / "Organic-Chemistry" / "main.tex").read_text()
    assert existing_sections(main_tex) == ["Characterization", "Reaction Mechanisms"]
    assert existing_note_labels(main_tex) == ["2025-10-03", "2025-10-05"]

    # 5. a third note under an EXISTING section appends within it
    server._write_section("Organic Chemistry", "Characterization",
                          "Chromatography", "TLC and GC...", "2025-10-04")
    main_tex = (tmp_path / "Organic-Chemistry" / "main.tex").read_text()
    assert existing_sections(main_tex) == ["Characterization", "Reaction Mechanisms"]
    assert r"\subsection{Chromatography}" in main_tex
