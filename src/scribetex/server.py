"""FastMCP server: prepare_note, resolve_placement, write_section."""
from __future__ import annotations

from fastmcp import FastMCP

from .config import notes_root
from .classify import parse_date, display_date, match_course, course_slug
from .discovery import known_courses
from .transcription_brief import build_brief
from .sources.base import get_source
from .scaffold import scaffold_course
from .writer import insert_note, DuplicateNoteError, MalformedDocumentError
from .placement import existing_sections, existing_note_labels

SERVER_INSTRUCTIONS = r"""
ScribeTeX turns a handwritten note export (PDF or image, e.g. from GoodNotes or
another iPad app) into typeset LaTeX, filed into a per-course document. Notes are
organized BY TOPIC: content lives under top-level \section headings (e.g.
"Characterization Techniques", "Reaction Mechanisms") and each note becomes one
or more \subsection under a chosen section. The document uses a fixed template
(full title page + table of contents + the course preamble).

YOU (the calling agent) do the vision transcription. This server never runs a
model, never makes a network call, and never compiles LaTeX; it only renders
pages to images, tells you how to transcribe, and does the deterministic
file/LaTeX placement. Follow this exact workflow:

STEP 1 — prepare_note(source="file", ref="<path to the PDF/image>")
  Use source="file" for any local export; source="goodnotes" is an alias for the
  same (GoodNotes PDF/PNG/JPG/HEIC exports). Returns: page_images, a
  transcription `brief`, notes_root, and known_courses. On {"error": ...}, report
  it and stop.

STEP 2 — TRANSCRIBE (you, from the page images)
  Read EVERY page image and transcribe to LaTeX, obeying the `brief`:
  - Output the BODY ONLY — no preamble, no \documentclass, no
    \begin{document}/\end{document}, and DO NOT write the \section or \label
    line (the server adds those).
  - Structure the note's content with \subsection{...} (and lower) per topic.
  - Use $...$ / align / equation for math. \ce{...} (mhchem) is available.
  - Use ONLY the packages/macros the brief lists as available.
  - Transcribe faithfully; NEVER invent content not on the page. Render
    hand-drawn diagrams you cannot reproduce as faithful prose + equations, and
    tell the user which drawings were described rather than reproduced.
  - Also DECIDE and EXTRACT: a course hint; a top-level SECTION title naming the
    note's overall theme; a concise SUBSECTION title for this note; and the class
    date. If the course, section, or date is missing/ambiguous, ASK THE USER —
    do not guess.

STEP 3 — resolve_placement(course_hint=..., section_hint=..., date=...)
  Returns the resolved course, course_status ("existing"/"new"), the target
  section and section_status ("existing"/"new"), target_path, date_iso,
  duplicate (a note with that date-label already exists), match_confidence, and
  existing_sections (to help you reuse a section rather than duplicate one). SHOW
  the user: course, chosen section (new vs existing), date, target file, and any
  duplicate — and get confirmation BEFORE writing. If confidence is "low", the
  course/section is "new", or date_iso is null, resolve it with the user first.

STEP 4 — write_section(course=..., course_number=..., section_title=...,
                       subsection_title=..., latex_body=..., date=...,
                       on_duplicate="warn")
  Only after the user confirms. Pass the course NAME as `course` (e.g.
  "<Course Name>") and the course NUMBER as `course_number` (e.g. "DEPT 10100") —
  both go on the title page/header when a new course is scaffolded. Scaffolds the
  course if new (full template: title page + TOC + preamble, plus main.bib and
  ExtFiles/ so it compiles standalone), then adds your \subsection under
  section_title — appending within it if it exists, or creating that \section at
  the end if not. Returns
  {"written": true, target_path, diff_summary, compiled: false}. If a note with
  the same date-label already exists it returns {"written": false, "error": ...}:
  relay the conflict and ask whether to use on_duplicate="replace" (collapse to
  one), "append" (add another), or skip.

AFTER WRITING
  Report provenance honestly: what you transcribed, which drawings were described
  vs. reproduced, the chosen section, and the target_path. The server is
  WRITE-ONLY. If the user wants a PDF, offer to compile main.tex yourself with a
  local TeX toolchain (pdflatex → biber → pdflatex twice, because the template
  uses biblatex/biber); that requires a TeX installation and is your action.

Notes root defaults to ~/Desktop/College/Notes (override with env
SCRIBETEX_NOTES_ROOT). Each note's \subsection carries a hidden
\label{note:YYYY-MM-DD} for duplicate detection; duplicates are never silently
overwritten.
"""

mcp = FastMCP("ScribeTeX", instructions=SERVER_INSTRUCTIONS)


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


def _resolve_placement(course_hint: str, section_hint: str, date: str) -> dict:
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
    section_status = "new"
    sections: list[str] = []
    if status == "existing" and target.exists():
        text = target.read_text(encoding="utf-8")
        sections = existing_sections(text)
        section_status = "existing" if section_hint in sections else "new"
        if date_iso and date_iso in existing_note_labels(text):
            duplicate = True

    if not date_iso:
        confidence = "low"

    return {
        "course": course,
        "course_status": status,
        "section_title": section_hint,
        "section_status": section_status,
        "existing_sections": sections,
        "target_path": str(target),
        "date_iso": date_iso,
        "date_display": display_date(date_iso) if date_iso else None,
        "duplicate": duplicate,
        "match_confidence": confidence,
    }


def _write_section(course: str, section_title: str, subsection_title: str,
                   latex_body: str, date: str, course_number: str = "",
                   on_duplicate: str = "warn") -> dict:
    root = notes_root()
    date_iso = parse_date(date)
    if not date_iso:
        return {"written": False, "error": f"unparseable date: {date!r}"}

    slug = course_slug(course)
    target = root / slug / "main.tex"
    if not target.exists():
        # Prefer an explicit course_number; else infer a digit-bearing token from
        # the course name; else fall back to the course name.
        number = (course_number.strip()
                  or next((t for t in course.split() if any(c.isdigit() for c in t)),
                          course))
        scaffold_course(root, course, number)

    try:
        new_text, summary = insert_note(
            target.read_text(encoding="utf-8"), section_title, subsection_title,
            latex_body, date_iso, on_duplicate,
        )
    except DuplicateNoteError as e:
        return {"written": False,
                "error": f"a note labelled {e.date_iso} already exists; choose "
                         f"on_duplicate='replace' or 'append', or skip."}
    except MalformedDocumentError as e:
        return {"written": False, "error": f"malformed document: {e}"}

    target.write_text(new_text, encoding="utf-8")
    return {"written": True, "target_path": str(target),
            "diff_summary": summary, "compiled": False}


@mcp.tool
def prepare_note(source: str = "file", ref: str = "") -> dict:
    """Render a handwritten note export to page images and return the
    transcription brief plus placement context, so the calling agent can read
    and transcribe it.

    Args:
        source: "file" for a local PDF/image path; "goodnotes" is an alias for
            the same (GoodNotes PDF/PNG/JPG/HEIC exports).
        ref: the path to the note. For a PDF, every page is rendered to a PNG.
    Returns a dict with: page_images (PNG paths to read and transcribe),
    brief (the rules you must follow when transcribing), notes_root, and
    known_courses. On bad input returns {"error": ..., "page_images": []}.
    After calling this, READ every page image and transcribe it yourself, then
    decide a section title, a subsection title, and the date."""
    return _prepare_note(source, ref)


@mcp.tool
def resolve_placement(course_hint: str, section_hint: str, date: str) -> dict:
    """Resolve which course document and which topic section a note goes under,
    so its placement can be confirmed with the user before writing.

    Args:
        course_hint: the course name/number you inferred.
        section_hint: the top-level SECTION title this note belongs under.
        date: the class date (any common format; normalized to ISO; used as the
            hidden duplicate-detection label).
    Returns: course, course_status ("existing"/"new"), section_title,
    section_status ("existing"/"new"), existing_sections (list, to help you reuse
    one), target_path, date_iso, date_display, duplicate (bool),
    match_confidence. Show this to the user and confirm before write_section. If
    match_confidence is "low", the course/section is "new", or date_iso is null,
    clear it up with the user first — do not assume."""
    return _resolve_placement(course_hint, section_hint, date)


@mcp.tool
def write_section(course: str, section_title: str, subsection_title: str,
                  latex_body: str, date: str, course_number: str = "",
                  on_duplicate: str = "warn") -> dict:
    """Scaffold the course if new and add a transcribed note as a subsection
    under the given topic section. Call only after the user confirms placement.

    Args:
        course: the confirmed course NAME (e.g. "<Course Name>"); also the
            folder name.
        section_title: the top-level section to file under (appended within if it
            exists, else created at the end of the document).
        subsection_title: a concise title for this note's subsection.
        latex_body: your transcribed LaTeX — BODY ONLY (no preamble, no
            \\section/\\subsection/\\label line; the server adds those).
        date: the confirmed class date (becomes the hidden \\label{note:...}).
        course_number: the course NUMBER (e.g. "DEPT 10100") for the title page
            and running header; used only when scaffolding a new course. If
            omitted, a digit-bearing token from the course name is used.
        on_duplicate: "warn" (default; refuse if a note with that date-label
            exists), "replace" (collapse that date's notes to one), or "append"
            (add another).
    Returns {"written": true, target_path, diff_summary, compiled: false}, or
    {"written": false, "error": ...} on a duplicate/malformed document. The
    server is write-only and never compiles LaTeX."""
    return _write_section(course, section_title, subsection_title, latex_body,
                          date, course_number, on_duplicate)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
