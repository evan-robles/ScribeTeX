from scribetex import compile as C


def test_parse_errors_extracts_message_and_line():
    log = (
        "This is pdfTeX...\n"
        "! Undefined control sequence.\n"
        "l.42 \\badcmd\n"
        "        {x}\n"
        "? \n"
    )
    errs = C.parse_errors(log)
    assert len(errs) == 1
    assert errs[0]["message"] == "Undefined control sequence."
    assert errs[0]["line"] == 42
    assert "badcmd" in errs[0]["context"]


def test_parse_errors_handles_multiple_and_no_line():
    log = (
        "! Missing $ inserted.\n"
        "l.10 x^2\n"
        "! Emergency stop.\n"
    )
    errs = C.parse_errors(log)
    assert [e["message"] for e in errs] == ["Missing $ inserted.", "Emergency stop."]
    assert errs[0]["line"] == 10
    assert errs[1]["line"] is None


def test_parse_errors_empty_on_clean_log():
    assert C.parse_errors("Output written on main.pdf (3 pages).") == []


def test_compile_missing_file(tmp_path):
    r = C.compile_course(tmp_path / "nope" / "main.tex")
    assert r["compiled"] is False
    assert "not found" in r["error"]
