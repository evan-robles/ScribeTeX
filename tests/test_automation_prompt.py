from automation import prompt


def test_build_prompt_mentions_path_and_contract():
    p = prompt.build_prompt("/notes/inbox/Bio 5.pdf")
    assert "/notes/inbox/Bio 5.pdf" in p
    assert "prepare_note" in p and "resolve_placement" in p and "write_section" in p
    assert "save_figure" in p
    assert prompt.RESULT_PREFIX in p
    # must instruct not to guess when ambiguous
    low = p.lower()
    assert "ambiguous" in low and ("do not" in low or "don't" in low)


def test_parse_filed():
    out = 'blah\nSCRIBETEX_RESULT: {"status":"filed","course":"Bio","target":"/x/main.tex"}\ndone'
    r = prompt.parse_result(out)
    assert r["status"] == "filed"
    assert r["course"] == "Bio"


def test_parse_ambiguous():
    out = 'SCRIBETEX_RESULT: {"status":"ambiguous","reason":"course unclear"}'
    assert prompt.parse_result(out)["status"] == "ambiguous"


def test_parse_last_line_wins():
    out = ('SCRIBETEX_RESULT: {"status":"error","reason":"x"}\n'
           'SCRIBETEX_RESULT: {"status":"filed","course":"C"}')
    assert prompt.parse_result(out)["status"] == "filed"


def test_parse_missing_line_is_error():
    assert prompt.parse_result("no marker here")["status"] == "error"


def test_parse_malformed_json_is_error():
    out = "SCRIBETEX_RESULT: {not json}"
    r = prompt.parse_result(out)
    assert r["status"] == "error"
