import pytest
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


def test_build_prompt_safe_paths():
    """Normal paths with spaces, parens, hyphens should succeed."""
    safe_paths = [
        "/inbox/Bio 5.pdf",
        "/notes/Chem (Advanced).pdf",
        "/path/with-dashes-here.pdf",
    ]
    for path in safe_paths:
        p = prompt.build_prompt(path)
        assert path in p


@pytest.mark.parametrize("unsafe_char,example", [
    ('"', '/notes/file"name.pdf'),
    ("'", "/notes/file'name.pdf"),
    ("`", "/notes/file`name.pdf"),
    ("<", "/notes/file<name.pdf"),
    (">", "/notes/file>name.pdf"),
    ("\n", "/notes/file\nname.pdf"),
    ("\r", "/notes/file\rname.pdf"),
])
def test_build_prompt_rejects_unsafe_chars(unsafe_char, example):
    """Dangerous characters should raise UnsafeNotePathError."""
    with pytest.raises(prompt.UnsafeNotePathError):
        prompt.build_prompt(example)


def test_allowed_tools_args_authorizes_mcp_headless():
    # Headless `claude -p` cannot prompt for permission; the worker must pass a
    # flag that authorizes the ScribeTeX MCP tools or every tool call is blocked.
    args = prompt.allowed_tools_args()
    assert "--permission-mode" in args
    assert "bypassPermissions" in args


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


def test_parse_unknown_status_is_error():
    """Unknown status values should be rejected."""
    out = 'SCRIBETEX_RESULT: {"status":"pwned","data":"injected"}'
    r = prompt.parse_result(out)
    assert r["status"] == "error"
    assert "unknown result status" in r["reason"]
