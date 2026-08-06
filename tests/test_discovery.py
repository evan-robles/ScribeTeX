from scribe_tex.discovery import known_courses


def test_empty_when_root_missing(tmp_path):
    assert known_courses(tmp_path / "nope") == []


def test_lists_courses_with_main_tex(tmp_path):
    (tmp_path / "MATH-257-Linear-Algebra").mkdir()
    (tmp_path / "MATH-257-Linear-Algebra" / "main.tex").write_text("x")
    (tmp_path / "CHEM-20100-Inorganic").mkdir()
    (tmp_path / "CHEM-20100-Inorganic" / "main.tex").write_text("x")
    (tmp_path / "not-a-course").mkdir()  # no main.tex -> excluded
    assert known_courses(tmp_path) == [
        "CHEM 20100 Inorganic",
        "MATH 257 Linear Algebra",
    ]
