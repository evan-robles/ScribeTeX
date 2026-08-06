from scribe_tex.transcription_brief import build_brief
from scribe_tex.preamble import ALLOWED_MACROS


def test_brief_lists_macros_and_rules():
    brief = build_brief()
    for macro in ALLOWED_MACROS:
        assert macro in brief
    # asks for the topic-model extraction fields
    assert "course" in brief.lower()
    assert "section" in brief.lower()
    assert "subsection" in brief.lower()
    assert "date" in brief.lower()
    # must instruct body-only (no preamble)
    assert "begin{document}" in brief  # referenced in a "do NOT include" rule
