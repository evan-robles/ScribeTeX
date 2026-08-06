from scribetex.preamble import (
    PREAMBLE_BODY,
    ALLOWED_MACROS,
    ALLOWED_PACKAGES,
    render_preamble,
)


def test_preamble_is_self_contained_for_standalone_folder():
    # The full preamble is used verbatim; its bib resource and graphics path
    # are LOCAL (main.bib / ExtFiles/), created beside main.tex by the scaffold,
    # never a parent-directory path. Assert against the RENDERED output (the raw
    # PREAMBLE_BODY has doubled braces for str.format).
    rendered = render_preamble(footer_name="Robles", course_number="X")
    assert r"\addbibresource{main.bib}" in rendered
    assert r"\graphicspath{{ExtFiles/}}" in rendered
    assert "../main.bib" not in rendered
    assert "../ExtFiles" not in rendered


def test_preamble_keeps_core_math_packages():
    for pkg in ("amsmath", "amssymb", "mathtools", "physics", "biblatex",
                "subfiles", "braket"):
        assert pkg in ALLOWED_PACKAGES


def test_allowed_macros_include_custom_commands():
    for macro in (r"\R", r"\pKa", r"\Dstroke", r"\ee", r"\asym", r"\chemint"):
        assert macro in ALLOWED_MACROS


def test_render_fills_placeholders():
    out = render_preamble(footer_name="Robles", course_number="MATH 257")
    assert "Robles" in out
    assert "MATH 257" in out
    assert "{footer_name}" not in out
    assert "{course_number}" not in out


def test_render_is_valid_when_no_stray_braces_break_format():
    # Ensures literal LaTeX braces were escaped so .format only sees our 2 fields.
    render_preamble(footer_name="X", course_number="Y")  # must not raise
