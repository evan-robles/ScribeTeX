from scribe_tex.preamble import (
    PREAMBLE_BODY,
    ALLOWED_MACROS,
    ALLOWED_PACKAGES,
    render_preamble,
)


def test_preamble_has_no_subfiles_wiring():
    # v1 uses standalone main.tex per course; subfiles machinery must be gone.
    assert "subfiles" not in PREAMBLE_BODY
    assert "subfix" not in PREAMBLE_BODY
    assert "addbibresource" not in PREAMBLE_BODY


def test_preamble_keeps_core_math_packages():
    for pkg in ("amsmath", "amssymb", "mathtools", "physics"):
        assert pkg in ALLOWED_PACKAGES


def test_allowed_macros_include_custom_commands():
    for macro in (r"\R", r"\prb", r"\e", r"\Dstroke", r"\pKa"):
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
