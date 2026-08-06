from scribetex.preamble import render_preamble, ALLOWED_PACKAGES


def test_pgfplots_loaded_and_configured():
    tex = render_preamble(footer_name="Robles", course_number="BIOS 20200")
    assert r"\usepackage{pgfplots}" in tex
    assert r"\pgfplotsset{compat=1.18}" in tex


def test_pgfplots_in_allowed_list():
    assert "pgfplots" in ALLOWED_PACKAGES


def test_preamble_still_renders_fields():
    tex = render_preamble(footer_name="Robles", course_number="BIOS 20200")
    assert "BIOS 20200" in tex
    assert "Robles" in tex
