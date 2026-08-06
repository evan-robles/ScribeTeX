import pytest
from scribetex.scaffold import (
    build_main_tex, scaffold_course,
    DEFAULT_FOOTER_NAME, DEFAULT_AUTHOR, DEFAULT_AFFILIATION,
)
from scribetex.placement import ENTRIES_START, ENTRIES_END


def test_build_main_tex_shape():
    doc = build_main_tex("Organic Chemistry", "CHEM 22100")
    assert doc.count(r"\begin{document}") == 1
    assert doc.count(r"\end{document}") == 1
    assert ENTRIES_START in doc and ENTRIES_END in doc
    assert doc.index(ENTRIES_START) < doc.index(ENTRIES_END)
    # full title page with course name + number + author + affiliation
    assert r"\begin{titlepage}" in doc
    assert "Organic Chemistry" in doc
    assert "CHEM 22100" in doc
    assert DEFAULT_AUTHOR in doc
    assert DEFAULT_AFFILIATION in doc
    # plain-styled TOC, not the "Topics" rename
    assert r"\tableofcontents" in doc
    assert r"\thispagestyle{plain}" in doc
    assert "Topics" not in doc
    assert DEFAULT_FOOTER_NAME in doc  # from the fancy footer in the preamble
    # entries region starts empty
    region = doc[doc.index(ENTRIES_START) + len(ENTRIES_START):doc.index(ENTRIES_END)]
    assert region.strip() == ""


def test_scaffold_creates_file_and_sidecars(tmp_path):
    p = scaffold_course(tmp_path, "Organic Chemistry", "CHEM 22100")
    assert p.exists()
    assert p.parent.name == "Organic-Chemistry"
    assert p.name == "main.tex"
    # sidecars the preamble references
    assert (p.parent / "main.bib").exists()
    assert (p.parent / "ExtFiles").is_dir()


def test_scaffold_refuses_overwrite(tmp_path):
    scaffold_course(tmp_path, "Organic Chemistry", "CHEM 22100")
    with pytest.raises(FileExistsError):
        scaffold_course(tmp_path, "Organic Chemistry", "CHEM 22100")
