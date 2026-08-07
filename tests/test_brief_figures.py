from scribetex.transcription_brief import build_brief


def test_brief_makes_cropping_the_default():
    b = build_brief().lower()
    assert "save_figure" in b and "tikz" in b and "pgfplots" in b
    assert "prose" in b
    # Cropping the original (save_figure) is the DEFAULT and must come BEFORE
    # the TikZ branch — the reverse ordering is what caused the worker to redraw
    # hand-drawn diagrams from imagination.
    assert b.index("save_figure") < b.index("tikz")
    assert b.index("save_figure") < b.index("prose")


def test_brief_forbids_redrawing_diagrams():
    b = build_brief().lower()
    # Must explicitly prohibit reconstructing/inventing a hand-drawn diagram.
    assert "never" in b
    assert "invent" in b or "reconstruct" in b or "imagination" in b


def test_brief_scopes_tikz_to_data_charts():
    b = build_brief().lower()
    # TikZ is allowed only for genuine data charts, not arbitrary diagrams.
    assert "data" in b and ("chart" in b or "bar" in b or "scatter" in b)


def test_brief_documents_bbox_fractions():
    b = build_brief()
    assert "x0" in b and "x1" in b
    assert "0" in b and "1" in b  # fractions in [0,1]


def test_brief_still_body_only_and_extracts():
    b = build_brief()
    assert "BODY ONLY" in b
    assert "subsection" in b and "section" in b and "date" in b
