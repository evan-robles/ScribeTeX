"""FastMCP server: prepare_note, resolve_placement, write_section."""
from __future__ import annotations

import os
import threading
from pathlib import Path

from fastmcp import FastMCP

from .config import notes_root
from .classify import parse_date, display_date, match_course, course_slug
from .discovery import known_courses
from .transcription_brief import build_brief
from .sources.base import get_source
from .scaffold import scaffold_course
from .writer import insert_note, DuplicateNoteError, MalformedDocumentError
from .placement import existing_sections, existing_note_labels, note_key
from .sanitize import escape_title, check_body, UnsafeLatexError
from . import figures

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
  - Transcribe faithfully; NEVER invent content not on the page. For hand-drawn
    diagrams, prefer this priority: (1) reproduce faithfully as TikZ/pgfplots if
    feasible; (2) otherwise call save_figure to crop the drawing out of the page
    image into ExtFiles/ and \includegraphics it; (3) only as a last resort,
    describe it in prose + equations. Tell the user which path each drawing took.
  - Also DECIDE and EXTRACT: a course hint; a top-level SECTION title naming the
    note's overall theme; a concise SUBSECTION title for this note; and the class
    date. If the course, section, or date is missing/ambiguous, ASK THE USER —
    do not guess.

STEP 3 — resolve_placement(course_hint=..., section_hint=..., subsection_hint=...,
                           date=...)
  Returns the resolved course, course_status ("existing"/"new"), the target
  section and section_status ("existing"/"new"), target_path, date_iso,
  duplicate (a note with that date+section+subsection label already exists —
  this keys on the SAME composite date+section+subsection key write_section
  uses, so it predicts write_section's outcome exactly), match_confidence, and
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


def _resolve_placement(course_hint: str, section_hint: str,
                       subsection_hint: str, date: str) -> dict:
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
        if date_iso:
            key = note_key(date_iso, section_hint, subsection_hint)
            duplicate = key in existing_note_labels(text)

    if not date_iso:
        confidence = "low"

    return {
        "course": course,
        "course_status": status,
        "section_title": section_hint,
        "subsection_title": subsection_hint,
        "section_status": section_status,
        "existing_sections": sections,
        "target_path": str(target),
        "date_iso": date_iso,
        "date_display": display_date(date_iso) if date_iso else None,
        "duplicate": duplicate,
        "match_confidence": confidence,
    }


# Per-target-path locks serialize concurrent write_section calls to the SAME
# main.tex. FastMCP tools can be invoked concurrently; without this the
# read-modify-write below interleaves and the second writer clobbers the first,
# silently losing a note. Keyed by the resolved target path string.
_write_locks: dict[str, threading.Lock] = {}
_write_locks_guard = threading.Lock()


def _lock_for(target: Path) -> threading.Lock:
    key = str(target.resolve() if target.exists() else target)
    with _write_locks_guard:
        lock = _write_locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _write_locks[key] = lock
        return lock


def _write_section(course: str, section_title: str, subsection_title: str,
                   latex_body: str, date: str, course_number: str = "",
                   on_duplicate: str = "warn") -> dict:
    root = notes_root()
    date_iso = parse_date(date)
    if not date_iso:
        return {"written": False, "error": f"unparseable date: {date!r}"}

    slug = course_slug(course)
    if not slug:
        return {"written": False,
                "error": f"course name {course!r} has no usable filename characters"}

    # Untrusted note-derived text: escape titles (they sit inside \section{}/
    # \subsection{} args) and reject compile-time-dangerous body constructs.
    section_title = escape_title(section_title)
    subsection_title = escape_title(subsection_title)
    try:
        latex_body = check_body(latex_body)
    except UnsafeLatexError as e:
        return {"written": False, "error": str(e)}

    target = root / slug / "main.tex"
    # Serialize per-target so two concurrent writes to this course can't lose a
    # note; write atomically (temp + os.replace) so a crash mid-write can't
    # truncate an existing document.
    with _lock_for(target):
        if not target.exists():
            # Prefer an explicit course_number; else infer a digit-bearing token
            # from the course name; else fall back to the course name.
            number = (course_number.strip()
                      or next((t for t in course.split()
                               if any(c.isdigit() for c in t)), course))
            scaffold_course(root, course, number)

        try:
            new_text, summary = insert_note(
                target.read_text(encoding="utf-8"), section_title, subsection_title,
                latex_body, date_iso, on_duplicate,
            )
        except DuplicateNoteError as e:
            return {"written": False,
                    "error": f"a note for section '{e.section_title}' / subsection "
                             f"'{e.subsection_title}' on {e.date_iso} already exists; "
                             f"choose on_duplicate='replace' or 'append', or skip."}
        except MalformedDocumentError as e:
            return {"written": False, "error": f"malformed document: {e}"}

        tmp = target.with_suffix(".tex.tmp")
        tmp.write_text(new_text, encoding="utf-8")
        os.replace(tmp, target)

    return {"written": True, "target_path": str(target),
            "diff_summary": summary, "compiled": False}


def _save_figure(course: str, page_image: str, bbox, name: str) -> dict:
    try:
        res = figures.crop_to_extfiles(page_image, bbox, course, name)
    except (FileNotFoundError, ValueError) as e:
        return {"saved": False, "error": str(e)}
    res["include"] = f"\\includegraphics[width=0.8\\linewidth]{{{res['filename'][:-4]}}}"
    return res


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
def resolve_placement(course_hint: str, section_hint: str,
                      subsection_hint: str, date: str) -> dict:
    """Resolve which course document and which topic section a note goes under,
    so its placement can be confirmed with the user before writing.

    Args:
        course_hint: the course name/number you inferred.
        section_hint: the top-level SECTION title this note belongs under.
        subsection_hint: the concise SUBSECTION title for THIS note; used
            together with section_hint and date to predict duplicates exactly
            as write_section will (the same composite date+section+subsection
            key).
        date: the class date (any common format; normalized to ISO; used with
            section_hint and subsection_hint as the hidden duplicate-detection
            label).
    Returns: course, course_status ("existing"/"new"), section_title,
    subsection_title, section_status ("existing"/"new"), existing_sections
    (list, to help you reuse one), target_path, date_iso, date_display,
    duplicate (bool), match_confidence. Show this to the user and confirm
    before write_section. If match_confidence is "low", the course/section is
    "new", or date_iso is null, clear it up with the user first — do not
    assume."""
    return _resolve_placement(course_hint, section_hint, subsection_hint, date)


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
        on_duplicate: "warn" (default; refuse if a note with the same date +
            section + subsection already exists), "replace" (collapse that exact
            note to one), or "append" (add another).
    Returns {"written": true, target_path, diff_summary, compiled: false}, or
    {"written": false, "error": ...} on a duplicate/malformed document. The
    server is write-only and never compiles LaTeX."""
    return _write_section(course, section_title, subsection_title, latex_body,
                          date, course_number, on_duplicate)


@mcp.tool
def save_figure(course: str, page_image: str, bbox: list[float], name: str) -> dict:
    """Crop a region of a rendered note page into the course's ExtFiles/ so a
    freehand drawing can be embedded with \\includegraphics. Use this only when a
    figure cannot be faithfully reproduced as TikZ/pgfplots/tabular.

    Args:
        course: the course NAME (same value you pass to write_section); the crop
            is written under that course's ExtFiles/.
        page_image: absolute path to a page PNG returned by prepare_note.
        bbox: [x0, y0, x1, y1] as fractions in [0,1] of the page width/height,
            origin top-left (e.g. [0.1, 0.4, 0.9, 0.7] = a middle horizontal band).
        name: base filename (no extension); sanitized to [A-Za-z0-9_-].
    Returns {"saved": true, filename, path, include (a ready \\includegraphics
    snippet)} or {"saved": false, "error": ...}. \\graphicspath already points at
    ExtFiles/, so \\includegraphics{<name>} resolves without a path prefix."""
    return _save_figure(course, page_image, bbox, name)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
