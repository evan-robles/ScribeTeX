import pytest
from scribetex.sanitize import escape_title, check_body, UnsafeLatexError, MAX_TITLE_LEN


def test_escape_title_escapes_specials():
    out = escape_title("A & B_% {c} $x$ #1")
    # After removing the escaped forms, no bare special should remain.
    stripped = out
    for esc in ("\\&", "\\%", "\\$", "\\#", "\\_", "\\{", "\\}"):
        stripped = stripped.replace(esc, "")
    for raw in ("&", "%", "$", "#", "_", "{", "}"):
        assert raw not in stripped, f"unescaped {raw!r} remains"


def test_escape_title_collapses_newlines():
    assert "\n" not in escape_title("line1\nline2")
    assert "\r" not in escape_title("a\r\nb")


def test_escape_title_length_capped():
    assert len(escape_title("x" * 500)) <= MAX_TITLE_LEN


def test_escape_title_brace_breakout_neutralized():
    out = escape_title("T}\\input{/etc/passwd")
    assert "}" not in out.replace("\\}", "")
    # backslash is escaped to \textbackslash so \input can't survive as a command
    assert "\\input" not in out


@pytest.mark.parametrize("bad", [
    "\\write18{x}", "\\input{a}", "\\include{a}", "\\openout1=x",
    "\\end{document}", "\\csname foo\\endcsname", "\\def\\x{y}",
    "text \\INPUT{X}",  # case-insensitive
    "\\directlua{os.execute('rm -rf ~')}",  # LuaTeX shell exec
    "\\latelua{...}", "\\usepackage{shellesc}", "\\RequirePackage{x}",
    "\\special{...}", "\\endinput", "\\shellescape",
    "text ^^J more",  # TeX catcode-notation escape
])
def test_check_body_rejects_dangerous(bad):
    with pytest.raises(UnsafeLatexError):
        check_body(bad)


@pytest.mark.parametrize("ok", [
    "Plain prose.",
    "$E = mc^2$ inline math.",
    "\\begin{tikzpicture}\\draw (0,0)--(1,1);\\end{tikzpicture}",
    "\\includegraphics[width=0.8\\linewidth]{ExtFiles/fig}",
    "\\begin{tabular}{cc}a & b\\\\\\end{tabular}",
])
def test_check_body_allows_legit_latex(ok):
    assert check_body(ok) == ok
