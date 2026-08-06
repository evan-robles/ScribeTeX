from scribetex.transcription_brief import build_brief


def test_brief_states_figure_priority():
    b = build_brief().lower()
    assert "tikz" in b and "pgfplots" in b
    assert "save_figure" in b
    assert "prose" in b
    # priority ordering mentioned
    assert b.index("tikz") < b.index("save_figure") < b.index("prose")


def test_brief_documents_bbox_fractions():
    b = build_brief()
    assert "x0" in b and "x1" in b
    assert "0" in b and "1" in b  # fractions in [0,1]


def test_brief_still_body_only_and_extracts():
    b = build_brief()
    assert "BODY ONLY" in b
    assert "subsection" in b and "section" in b and "date" in b
