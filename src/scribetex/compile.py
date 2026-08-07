"""Compile a course main.tex to PDF and parse LaTeX errors into structured form.

This is the ONE place ScribeTeX compiles LaTeX; the MCP server stays write-only
except for the explicit, opt-in compile_course tool that calls in here. Both the
compile-course skill and that tool share this module (no duplicated toolchain
logic).

Beyond running the toolchain, this parses the LaTeX log into structured errors
(file, line, message) so an error-recovery pass can map each failure back to the
note block that caused it and fix only that block.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

# Per-step wall-clock cap. pdflatex with -halt-on-error normally returns fast on
# error, but a pathological input (or a prompt it can't satisfy in nonstopmode)
# could hang; bound it so a compile can never wedge the caller.
STEP_TIMEOUT_S = 180

REQUIRED_TOOLS = ("pdflatex", "biber")

# A LaTeX error line: "! Undefined control sequence." etc.
_ERR_RE = re.compile(r"^! (.+)$")
# The line marker LaTeX prints for many errors: "l.123 <context>".
_LINE_RE = re.compile(r"^l\.(\d+)\s?(.*)$")
# "LaTeX Warning" / "Overfull" are not fatal; we only collect ! errors.


def toolchain_missing() -> str | None:
    """Return the name of the first required TeX tool not on PATH, or None."""
    for tool in REQUIRED_TOOLS:
        if shutil.which(tool) is None:
            return tool
    return None


def parse_errors(log_text: str) -> list[dict]:
    """Extract structured errors from pdflatex log/stdout text.

    Each error is {message, line (int|None), context (str)}. LaTeX prints an
    error as `! <message>` followed (often) by an `l.<n> <source excerpt>` line;
    we pair them. Line numbers are relative to the .tex file pdflatex was reading.
    """
    errors: list[dict] = []
    lines = log_text.splitlines()
    i = 0
    while i < len(lines):
        m = _ERR_RE.match(lines[i])
        if not m:
            i += 1
            continue
        message = m.group(1).strip()
        line_no: int | None = None
        context = ""
        # Scan a few following lines for the l.<n> marker.
        for j in range(i + 1, min(i + 12, len(lines))):
            lm = _LINE_RE.match(lines[j].strip())
            if lm:
                line_no = int(lm.group(1))
                context = lm.group(2).strip()
                break
        errors.append({"message": message, "line": line_no, "context": context})
        i += 1
    return errors


def compile_course(main_tex: Path, timeout_s: int = STEP_TIMEOUT_S) -> dict:
    """Run the biblatex/biber toolchain on `main_tex`. Returns a result dict:

    {compiled: bool, pdf: str|None, exists: bool,
     failed_step: str|None, errors: [ {message,line,context} ], log_tail: str}

    On a toolchain-missing or file-missing condition, compiled=False with an
    `error` key. On a LaTeX failure, `errors` carries the parsed diagnostics and
    `log_tail` the last lines of combined stdout+stderr.
    """
    main_tex = Path(main_tex)
    if not main_tex.exists():
        return {"compiled": False, "error": f"main.tex not found: {main_tex}"}
    missing = toolchain_missing()
    if missing:
        return {"compiled": False,
                "error": f"'{missing}' not found on PATH. Install a TeX "
                         f"distribution (MacTeX / TeX Live) to compile."}

    workdir = main_tex.parent
    stem = main_tex.stem
    steps = [
        ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", main_tex.name],
        ["biber", stem],
        ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", main_tex.name],
        ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", main_tex.name],
    ]
    for step in steps:
        try:
            proc = subprocess.run(step, cwd=workdir, capture_output=True,
                                  text=True, timeout=timeout_s)
        except subprocess.TimeoutExpired:
            return {"compiled": False, "failed_step": " ".join(step),
                    "errors": [], "log_tail": f"timed out after {timeout_s}s"}
        combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
        if proc.returncode != 0:
            return {
                "compiled": False,
                "failed_step": " ".join(step),
                "errors": parse_errors(combined),
                "log_tail": "\n".join(combined.splitlines()[-30:]),
            }

    pdf = workdir / f"{stem}.pdf"
    return {"compiled": True, "pdf": str(pdf), "exists": pdf.exists(),
            "errors": [], "log_tail": ""}
