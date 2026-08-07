"""Sanitize untrusted note-derived text before it reaches main.tex.

Note titles and bodies come (via the transcribing agent) from UNTRUSTED
handwritten content. Titles are placed inside ``\\section{...}`` / ``\\subsection{...}``
arguments, so any unescaped LaTeX special can break out of the braces and inject
arbitrary markup — which becomes a code/file-read vector when the separate
compile-course skill later runs pdflatex. Bodies are meant to *be* LaTeX, so they
cannot be blindly escaped, but a small set of primitives (shell escape, arbitrary
file input, premature document end) must never appear in transcribed content.
"""
from __future__ import annotations
import re

MAX_TITLE_LEN = 200


class UnsafeLatexError(ValueError):
    """Raised when note-derived LaTeX contains a disallowed construct."""


# LaTeX specials that must be escaped inside a title argument. Order matters:
# backslash first so we don't double-escape the replacements we insert.
_TITLE_ESCAPES = [
    ("\\", r"\textbackslash{}"),
    ("&", r"\&"),
    ("%", r"\%"),
    ("$", r"\$"),
    ("#", r"\#"),
    ("_", r"\_"),
    ("{", r"\{"),
    ("}", r"\}"),
    ("~", r"\textasciitilde{}"),
    ("^", r"\textasciicircum{}"),
]


def escape_title(title: str) -> str:
    """Escape LaTeX specials in a title and collapse newlines, length-capped.

    A title is a single-line argument to \\section/\\subsection; embedded
    newlines or unescaped braces would either corrupt the structure or let an
    untrusted title break out of the heading. Returns a safe single-line string.
    """
    s = (title or "").replace("\r", " ").replace("\n", " ").strip()
    for raw, rep in _TITLE_ESCAPES:
        s = s.replace(raw, rep)
    if len(s) > MAX_TITLE_LEN:
        s = s[:MAX_TITLE_LEN].rstrip()
    return s


# Body-level constructs an untrusted transcription must never carry. These enable
# shell execution, arbitrary file reads/writes at compile time, or breaking out of
# the document body. Matched case-insensitively on the command name, with a
# trailing boundary (?![A-Za-z]) so a forbidden command isn't matched as a prefix
# of a legitimate longer one — e.g. \include must NOT flag \includegraphics, and
# \write must NOT flag \write18-free \writefoo (write18 is listed explicitly).
_FORBIDDEN_BODY = re.compile(
    r"\\(?:write18|input|include|openin|openout|read|write|"
    r"immediate|catcode|csname|def|let|expandafter)(?![A-Za-z])"
    r"|\\end\s*\{\s*document\s*\}",
    re.IGNORECASE,
)


def check_body(body: str) -> str:
    """Return the body unchanged, or raise UnsafeLatexError on a forbidden construct.

    The body is legitimately LaTeX (math, tikz, tabular, \\includegraphics), so it
    is not escaped — but it must not contain compile-time-dangerous primitives or
    a premature \\end{document}. This is the enforced half of the "treat note
    content as untrusted" contract; the compile-course skill should additionally
    run with -no-shell-escape as defense in depth.
    """
    m = _FORBIDDEN_BODY.search(body or "")
    if m:
        raise UnsafeLatexError(
            f"transcribed body contains a disallowed LaTeX construct "
            f"{m.group(0)!r}; refusing to write it into the document"
        )
    return body
