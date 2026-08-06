import pytest
from scribe_tex.scaffold import build_main_tex, scaffold_course, DEFAULT_FOOTER_NAME
from scribe_tex.placement import ENTRIES_START, ENTRIES_END


def test_build_main_tex_shape():
    doc = build_main_tex("MATH 257 Linear Algebra", "MATH 257")
    assert doc.count(r"\begin{document}") == 1
    assert doc.count(r"\end{document}") == 1
    assert ENTRIES_START in doc and ENTRIES_END in doc
    assert doc.index(ENTRIES_START) < doc.index(ENTRIES_END)
    assert "Topics" in doc                 # renamed contents heading
    assert "MATH 257 Linear Algebra" in doc  # title
    assert DEFAULT_FOOTER_NAME in doc
    # entries region starts empty
    region = doc[doc.index(ENTRIES_START) + len(ENTRIES_START):doc.index(ENTRIES_END)]
    assert region.strip() == ""


def test_scaffold_creates_file(tmp_path):
    p = scaffold_course(tmp_path, "MATH 257 Linear Algebra", "MATH 257")
    assert p.exists()
    assert p.parent.name == "MATH-257-Linear-Algebra"
    assert p.name == "main.tex"


def test_scaffold_refuses_overwrite(tmp_path):
    scaffold_course(tmp_path, "MATH 257 Linear Algebra", "MATH 257")
    with pytest.raises(FileExistsError):
        scaffold_course(tmp_path, "MATH 257 Linear Algebra", "MATH 257")
