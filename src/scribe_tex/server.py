"""FastMCP server: prepare_note, resolve_placement, write_section."""
from __future__ import annotations

from fastmcp import FastMCP

from .config import notes_root
from .classify import parse_date, display_date, match_course, course_slug
from .discovery import known_courses
from .transcription_brief import build_brief
from .sources.base import get_source
from .scaffold import scaffold_course
from .writer import insert_section, DuplicateDateError, MalformedDocumentError
from .placement import plan_insertion

SERVER_INSTRUCTIONS = r"""
scribe-tex turns a handwritten note export (PDF or image) into a typeset LaTeX
section, filed into a per-course document — one dated \section per class, kept in
date order, matching a fixed course-notes template.

YOU (the calling agent) do the vision transcription. This server never runs a
model, never makes a network call, and never compiles LaTeX; it only renders
pages to images, tells you how to transcribe, and does the deterministic
file/LaTeX placement. Follow this exact workflow:

STEP 1 — prepare_note(source="file", ref="<path to the PDF/image>")
  Returns: page_images (PNG paths), a transcription `brief`, the notes_root, and
  known_courses (existing course documents). If it returns an {"error": ...},
  report it and stop.

STEP 2 — TRANSCRIBE (you, from the page images)
  Read EVERY page image and transcribe the note to LaTeX, obeying the `brief`:
  - Output the SECTION BODY ONLY — no preamble, no \documentclass, no
    \begin{document}/\end{document}, and DO NOT write the \section or \label
    line (write_section adds those).
  - Use $...$ / align / equation for math, \subsection{...} for each topic.
  - Use ONLY the packages/macros the brief lists as available (the template
    loads amsmath, mathtools, physics, mhchem, siunitx, tikz, braket, biblatex,
    etc.). \ce{...} (mhchem) is available for chemistry; use it for formulae and
    reactions.
  - Transcribe faithfully. Hand-drawn diagrams (spectra, mechanism arrows,
    skeletal structures) that you cannot reproduce exactly should be rendered as
    faithful prose + equations (or chemfig/tikz only if clean); NEVER invent
    content that is not on the page. When you finish, tell the user plainly which
    drawings were described rather than reproduced.
  - Also EXTRACT from the note: a course hint and the class date (look for a
    written date header). If either is missing or ambiguous, ASK THE USER — do
    not guess a course or a date.

STEP 3 — resolve_placement(course_hint="<hint>", date="<date>")
  Returns the resolved course, course_status ("existing"/"new"), target_path,
  date_iso, date_display, insert_position, duplicate, and match_confidence.
  SHOW the user this result — course, date, target file, new-vs-existing, and
  whether that date already exists — and get their confirmation BEFORE writing.
  If match_confidence is "low", if the course is "new" (you're about to create a
  folder), or if date_iso is null, resolve the ambiguity with the user first.

STEP 4 — write_section(course=..., date=..., latex_body=..., on_duplicate="warn")
  Only after the user confirms. Scaffolds the course if new (creating main.tex
  with the full template preamble + title page + "Topics" TOC, plus a main.bib
  and ExtFiles/ so it compiles standalone), then inserts your section in date
  order. Returns {"written": true, target_path, diff_summary, compiled: false}.
  On a duplicate date it returns {"written": false, "error": ...}: relay the
  conflict and ask the user whether to use on_duplicate="replace" (collapse to
  one section for that date), "append" (add a second), or skip.

AFTER WRITING
  Report the method provenance honestly: what you transcribed, which drawings
  were described vs. reproduced, and the exact target_path. The server is
  WRITE-ONLY — it does not compile. If the user wants a PDF, offer to compile
  the course's main.tex yourself with a local TeX toolchain (pdflatex → biber →
  pdflatex twice, because the template uses biblatex/biber); note that requires
  a TeX installation and is your action, not the server's.

Notes root defaults to ~/Desktop/College/Notes (override with the env var
SCRIBE_TEX_NOTES_ROOT). Each date becomes \section{Month D, YYYY} with an ISO
\label{sec:YYYY-MM-DD}; sections stay in ascending date order and duplicates are
never silently overwritten.
"""

mcp = FastMCP("scribe-tex", instructions=SERVER_INSTRUCTIONS)


def _prepare_note(source: str = "file", ref: str = "") -> dict:
    try:
        pages = get_source(source).fetch_pages(ref)
    except (FileNotFoundError, ValueError, NotImplementedError) as e:
        return {"error": str(e), "page_images": []}
    root = notes_root()
    return {
        "page_images": [str(p) for p in pages],
        "brief": build_brief(),
        "notes_root": str(root),
        "known_courses": known_courses(root),
    }


def _resolve_placement(course_hint: str, date: str) -> dict:
    root = notes_root()
    known = known_courses(root)
    date_iso = parse_date(date)
    matched, confidence = match_course(course_hint, known)

    if matched is not None:
        course = matched
        status = "existing"
    else:
        course = course_hint
        status = "new"
        # a new course is a confident placement decision only if the date parsed
        confidence = "high" if date_iso else "low"

    slug = course_slug(course)
    target = root / slug / "main.tex"

    duplicate = False
    insert_position = "start (first section)"
    if date_iso and status == "existing" and target.exists():
        plan = plan_insertion(target.read_text(encoding="utf-8"), date_iso)
        duplicate = plan["duplicate"]
        if duplicate:
            insert_position = f"duplicate of existing section dated {date_iso}"
        elif plan["after_date"]:
            insert_position = f"after section dated {plan['after_date']}"

    if not date_iso:
        confidence = "low"

    return {
        "course": course,
        "course_status": status,
        "target_path": str(target),
        "date_iso": date_iso,
        "date_display": display_date(date_iso) if date_iso else None,
        "insert_position": insert_position,
        "duplicate": duplicate,
        "match_confidence": confidence,
    }


def _write_section(course: str, date: str, latex_body: str,
                   on_duplicate: str = "warn") -> dict:
    root = notes_root()
    date_iso = parse_date(date)
    if not date_iso:
        return {"written": False, "error": f"unparseable date: {date!r}"}

    slug = course_slug(course)
    target = root / slug / "main.tex"
    if not target.exists():
        # infer a course number token (first token containing a digit) for the header
        number = next((t for t in course.split() if any(c.isdigit() for c in t)), course)
        scaffold_course(root, course, number)

    try:
        new_text, summary = insert_section(
            target.read_text(encoding="utf-8"), date_iso, latex_body, on_duplicate
        )
    except DuplicateDateError as e:
        return {"written": False,
                "error": f"duplicate date {e.date_iso}; choose on_duplicate="
                         f"'replace' or 'append', or skip."}
    except MalformedDocumentError as e:
        return {"written": False, "error": f"malformed document: {e}"}

    target.write_text(new_text, encoding="utf-8")
    return {"written": True, "target_path": str(target),
            "diff_summary": summary, "compiled": False}


@mcp.tool
def prepare_note(source: str = "file", ref: str = "") -> dict:
    """STEP 1. Render a handwritten note export to page images so you can
    transcribe it, and return the transcription brief + placement context.

    Args:
        source: note source type; use "file" for a local PDF/image path.
        ref: the path to the note (PDF, PNG, JPG). For a PDF, every page is
            rendered to a PNG.
    Returns a dict with: page_images (PNG paths to read and transcribe),
    brief (the rules you must follow when transcribing), notes_root, and
    known_courses (existing course docs, to help you infer the course). On bad
    input returns {"error": ..., "page_images": []}.
    After calling this, READ every page image and transcribe it yourself."""
    return _prepare_note(source, ref)


@mcp.tool
def resolve_placement(course_hint: str, date: str) -> dict:
    """STEP 3. Resolve which course document and where in it a note's section
    will go, so you can confirm placement with the user BEFORE writing.

    Args:
        course_hint: the course name/number you inferred from the note.
        date: the class date you inferred (any common format; normalized to ISO).
    Returns: course, course_status ("existing"/"new"), target_path, date_iso,
    date_display, insert_position, duplicate (bool), match_confidence
    ("high"/"low"). Show this to the user and confirm before write_section. If
    match_confidence is "low", course_status is "new", or date_iso is null,
    clear it up with the user first — do not assume."""
    return _resolve_placement(course_hint, date)


@mcp.tool
def write_section(course: str, date: str, latex_body: str,
                  on_duplicate: str = "warn") -> dict:
    """STEP 4. Scaffold the course if new and insert your transcribed section in
    date order. Call only AFTER the user confirms the placement.

    Args:
        course: the confirmed course name/number.
        date: the confirmed class date.
        latex_body: your transcribed LaTeX — SECTION BODY ONLY (no preamble, no
            \\section/\\label line; the server adds those).
        on_duplicate: "warn" (default; refuse and report if the date exists),
            "replace" (collapse that date to one new section), or "append" (add
            a second section for that date).
    Returns {"written": true, target_path, diff_summary, compiled: false}, or
    {"written": false, "error": ...} on a duplicate/malformed document. The
    server is write-only and never compiles LaTeX."""
    return _write_section(course, date, latex_body, on_duplicate)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
