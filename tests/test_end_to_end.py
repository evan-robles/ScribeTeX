import fitz
from scribetex import server
from scribetex.placement import existing_note_labels


def test_full_flow(tmp_path, monkeypatch):
    monkeypatch.setenv("SCRIBETEX_NOTES_ROOT", str(tmp_path))
    # 1. prepare a (blank) note PDF
    pdf = tmp_path / "chem.pdf"
    d = fitz.open(); d.new_page(); d.save(str(pdf)); d.close()
    prep = server._prepare_note("file", str(pdf))
    assert prep["page_images"]

    # 2. agent "transcribes" + infers course/date -> resolve
    res = server._resolve_placement("Organic Chemistry", "Oct 3 2025", "chem.pdf")
    assert res["course_status"] == "new"
    assert res["date_iso"] == "2025-10-03"

    # 3. write after user confirms — the body carries the LLM's own headings,
    # and a single note may span SEVERAL sections.
    body1 = ("\\section{Characterization}\n\\subsection{NMR}\nNMR is...\n"
             "\\section{Reaction Mechanisms}\n\\subsection{Addition}\nMarkovnikov...")
    w = server._write_section(res["course"], body1, res["date_iso"],
                              source_name="chem.pdf")
    assert w["written"] is True

    main_tex = (tmp_path / "Organic-Chemistry" / "main.tex").read_text()
    # both sections from the one note are present
    assert r"\section{Characterization}" in main_tex
    assert r"\section{Reaction Mechanisms}" in main_tex

    # 4. a second, different note file on another date is appended
    server._write_section("Organic Chemistry", "\\section{Kinetics}\nrate laws...",
                          "2025-10-05", source_name="lecture2.pdf")
    main_tex = (tmp_path / "Organic-Chemistry" / "main.tex").read_text()
    assert existing_note_labels(main_tex) == [
        "2025-10-03:chem-pdf",
        "2025-10-05:lecture2-pdf",
    ]
    assert r"\section{Kinetics}" in main_tex
