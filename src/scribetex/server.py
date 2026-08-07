"""FastMCP server: prepare_note, resolve_placement, write_section."""
from __future__ import annotations

import os
import re
import threading
from pathlib import Path

from fastmcp import FastMCP

from .config import notes_root
from .classify import parse_date, display_date, match_course, course_slug
from .discovery import known_courses
from .transcription_brief import build_brief
from .sources.base import get_source
from .scaffold import scaffold_course
from .writer import (insert_note, replace_note_body_by_key, DuplicateNoteError,
                     MalformedDocumentError, NoteNotFoundError)
from .placement import existing_note_labels, note_key
from .sanitize import check_body, UnsafeLatexError
from .compile import compile_course as _compile
from . import figures

SERVER_INSTRUCTIONS = r"""
ScribeTeX turns a handwritten note export (PDF or image, e.g. from GoodNotes or
another iPad app) into typeset LaTeX, filed into a per-course document. YOU (the
transcribing agent) build the note's heading structure: a single note is
transcribed into LaTeX with its OWN \section{...}/\subsection{...} headings that
reflect its real topics — one note may span SEVERAL sections (e.g. a class
covering "Area" and "Volume" yields a \section for each). The server does not
impose or add any section/subsection; it appends your structured block into the
course document under a hidden date+filename label. The document uses a fixed
template (title page + table of contents + course preamble).

YOU do the vision transcription. This server never runs a model, never makes a
network call, and never compiles LaTeX; it only renders pages to images, tells
you how to transcribe, and does the deterministic file/LaTeX placement. Follow
this exact workflow:

STEP 1 — prepare_note(source="file", ref="<path to the PDF/image>")
  Use source="file" for any local export; source="goodnotes" is an alias for the
  same (GoodNotes PDF/PNG/JPG/HEIC exports). Returns: page_images, a
  transcription `brief`, notes_root, and known_courses. On {"error": ...}, report
  it and stop.

STEP 2 — TRANSCRIBE (you, from the page images)
  Read EVERY page image and transcribe to LaTeX, obeying the `brief`:
  - Output the BODY with its OWN heading structure: use \section{...} for each
    major topic in the note and \subsection{...} beneath as needed. Do NOT output
    a preamble, \documentclass, \begin{document}/\end{document}, or a \label line
    (the server adds the hidden label).
  - Use $...$ / align / equation for math. \ce{...} (mhchem) is available.
  - Use ONLY the packages/macros the brief lists as available.
  - Transcribe faithfully; NEVER invent content not on the page. For any
    drawing/diagram/sketch, CROP THE ORIGINAL by default: call save_figure to
    crop it out of the page image into ExtFiles/ and \includegraphics it. Use
    TikZ/pgfplots ONLY for a genuine data chart (bar/line/scatter with
    recoverable numbers); NEVER redraw a hand-drawn diagram from imagination.
    Prose is a last resort. Tell the user which path each drawing took.
  - Also DECIDE and EXTRACT: a course hint and the class date. The section
    structure is yours to author from content (above) — it is NOT a placement
    input. If the course or date is missing/ambiguous, ASK THE USER — do not guess.

STEP 3 — resolve_placement(course_hint=..., date=..., source_name=...)
  Returns the resolved course, course_status ("existing"/"new"), target_path,
  date_iso, date_display, duplicate (this source file was already filed on this
  date — keys on the SAME date+filename label write_section uses, so it predicts
  the outcome exactly), and match_confidence. SHOW the user: course (new vs
  existing), date, target file, and any duplicate — and get confirmation BEFORE
  writing. If confidence is "low", the course is "new", or date_iso is null,
  resolve it with the user first.

STEP 4 — write_section(course=..., course_number=..., latex_body=..., date=...,
                       source_name=..., on_duplicate="warn")
  Only after the user confirms. Pass the course NAME as `course` and the course
  NUMBER as `course_number` (both go on the title page/header when a new course
  is scaffolded). `latex_body` is your transcription WITH its own
  \section/\subsection headings. `source_name` is the original note filename
  (with the date it is the dedup key). Scaffolds the course if new (full
  template: title page + TOC + preamble, plus main.bib and ExtFiles/ so it
  compiles standalone), then appends your block. Returns {"written": true,
  target_path, diff_summary, compiled: false}. If this file was already filed on
  this date it returns {"written": false, "error": ...}: relay the conflict and
  ask whether to use on_duplicate="replace", "append", or skip.

AFTER WRITING
  Report provenance honestly: what you transcribed, which drawings were cropped
  vs. reproduced, the sections you created, and the target_path. The server is
  WRITE-ONLY. If the user wants a PDF, offer to compile main.tex yourself with a
  local TeX toolchain (pdflatex → biber → pdflatex twice); that requires a TeX
  installation and is your action.

Notes root defaults to ~/Desktop/College/Notes (override with env
SCRIBETEX_NOTES_ROOT). Each note carries a hidden \label{note:DATE:filename-slug}
for duplicate detection; duplicates are never silently overwritten.
"""

mcp = FastMCP("ScribeTeX", instructions=SERVER_INSTRUCTIONS)


_VALID_SOURCES = {"file", "goodnotes"}


def _prepare_note(source: str = "file", ref: str = "") -> dict:
    # Robustness: the path is supposed to arrive in `ref`, but if a caller (or a
    # flaky client that only exposes `source`) passes the PATH as `source`
    # instead, recover gracefully — treat a source that isn't a known source
    # keyword as the ref, and default source to "file". This makes prepare_note
    # work whether the path comes in via ref OR source.
    if source not in _VALID_SOURCES and not ref:
        ref, source = source, "file"
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


def _resolve_placement(course_hint: str, date: str, source_name: str = "") -> dict:
    """Resolve where a note goes: course + date + duplicate check.

    The note's internal section/subsection structure is authored by the
    transcribing LLM from the note's content, so placement no longer takes or
    resolves section/subsection hints — only the course document and the date,
    plus whether this source file was already filed on this date.
    """
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
    if status == "existing" and target.exists() and date_iso and source_name:
        text = target.read_text(encoding="utf-8")
        duplicate = note_key(date_iso, source_name) in existing_note_labels(text)

    if not date_iso:
        confidence = "low"

    return {
        "course": course,
        "course_status": status,
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


def _write_section(course: str, latex_body: str, date: str,
                   source_name: str = "", course_number: str = "",
                   on_duplicate: str = "warn") -> dict:
    """File a transcribed note into a course document.

    The note's LaTeX body is authored by the transcribing LLM and carries its OWN
    \\section/\\subsection headings (one note may span several sections). The
    server does not impose a section/subsection wrapper; it appends the block
    under a hidden date+filename label. `source_name` (the original note filename)
    forms the dedup key with the date.
    """
    root = notes_root()
    date_iso = parse_date(date)
    if not date_iso:
        return {"written": False, "error": f"unparseable date: {date!r}"}

    slug = course_slug(course)
    if not slug:
        return {"written": False,
                "error": f"course name {course!r} has no usable filename characters"}

    # The body is LLM-authored LaTeX (its own headings, math, tikz, figures) so
    # it is not escaped — but reject compile-time-dangerous constructs.
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
            # scaffold_course escapes the name/number for the title-page argument
            # positions while slugging the directory from the raw name.
            number = (course_number.strip()
                      or next((t for t in course.split()
                               if any(c.isdigit() for c in t)), course))
            scaffold_course(root, course, number)

        try:
            new_text, summary = insert_note(
                target.read_text(encoding="utf-8"), latex_body, date_iso,
                source_name, on_duplicate,
            )
        except DuplicateNoteError as e:
            return {"written": False,
                    "error": f"a note for source '{e.source_name}' on {e.date_iso} "
                             f"already exists; choose on_duplicate='replace' or "
                             f"'append', or skip."}
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


_HEADER_NUM_RE = re.compile(r"\\fancyhead\[R\]\{([^}]*)\}")


def _course_number_from_main(main_tex: Path) -> str:
    """Recover the course number from an existing main.tex's running header, so a
    regenerated study guide carries the same number. Empty if not found."""
    try:
        m = _HEADER_NUM_RE.search(main_tex.read_text(encoding="utf-8"))
        return m.group(1) if m else ""
    except OSError:
        return ""


def _write_study_aid(course: str, kind: str, content: str) -> dict:
    """Write flashcards (a .tsv sidecar) or a study guide (a SEPARATE, standalone
    compilable study-guide.tex — not embedded in main.tex)."""
    slug = course_slug(course)
    if not slug:
        return {"written": False, "error": f"course {course!r} has no usable slug"}
    course_dir = notes_root() / slug
    target = course_dir / "main.tex"
    if not target.exists():
        return {"written": False, "error": f"course document not found: {target}"}
    if kind == "flashcards":
        out = course_dir / "flashcards.tsv"
        out.write_text(content, encoding="utf-8")
        return {"written": True, "kind": "flashcards", "path": str(out)}
    # guide: write a standalone study-guide.tex (its own document, sharing the
    # course preamble + ExtFiles/); regenerating overwrites it, not main.tex.
    try:
        body = check_body(content)
    except UnsafeLatexError as e:
        return {"written": False, "error": str(e)}
    from .scaffold import build_study_guide_tex
    number = _course_number_from_main(target)
    doc = build_study_guide_tex(course, number, body)
    out = course_dir / "study-guide.tex"
    tmp = out.with_suffix(".tex.tmp")
    tmp.write_text(doc, encoding="utf-8")
    os.replace(tmp, out)
    return {"written": True, "kind": "guide", "path": str(out)}


def _read_course(course: str) -> dict:
    """Return a course document's filed content + structure for a read-pass
    (study guide, verification, figure captioning)."""
    from .placement import entries_body, list_notes
    slug = course_slug(course)
    if not slug:
        return {"ok": False, "error": f"course {course!r} has no usable slug"}
    target = notes_root() / slug / "main.tex"
    if not target.exists():
        return {"ok": False, "error": f"course document not found: {target}"}
    text = target.read_text(encoding="utf-8")
    return {"ok": True, "course": course, "target_path": str(target),
            "notes": list_notes(text), "body": entries_body(text)}


def _compile_course(course: str) -> dict:
    """Compile a course's main.tex to PDF, returning structured errors on failure.

    This is the one place the server compiles LaTeX (otherwise write-only). Errors
    come back parsed (message/line/context) so a recovery pass can map each to the
    note block that caused it."""
    slug = course_slug(course)
    if not slug:
        return {"compiled": False,
                "error": f"course name {course!r} has no usable filename characters"}
    target = notes_root() / slug / "main.tex"
    return _compile(target)


def _patch_note_region(course: str, note_key_str: str, new_body: str) -> dict:
    """Surgically replace ONE note block's body (found by its date+filename key).

    Used by the compile error-recovery pass to fix only the offending note. The
    new body is sanitized (check_body) like any write, and the file is locked +
    atomically replaced."""
    slug = course_slug(course)
    if not slug:
        return {"patched": False, "error": f"course {course!r} has no usable slug"}
    target = notes_root() / slug / "main.tex"
    if not target.exists():
        return {"patched": False, "error": f"course document not found: {target}"}
    try:
        new_body = check_body(new_body)
    except UnsafeLatexError as e:
        return {"patched": False, "error": str(e)}
    with _lock_for(target):
        try:
            new_text = replace_note_body_by_key(
                target.read_text(encoding="utf-8"), note_key_str, new_body)
        except NoteNotFoundError:
            return {"patched": False,
                    "error": f"no note block with key {note_key_str!r} in {course}"}
        except MalformedDocumentError as e:
            return {"patched": False, "error": f"malformed document: {e}"}
        tmp = target.with_suffix(".tex.tmp")
        tmp.write_text(new_text, encoding="utf-8")
        os.replace(tmp, target)
    return {"patched": True, "target_path": str(target), "note_key": note_key_str}


@mcp.tool
def prepare_note(ref: str, source: str = "file") -> dict:
    """Render a handwritten note export to page images and return the
    transcription brief plus placement context, so the calling agent can read
    and transcribe it.

    Args:
        ref: REQUIRED. The filesystem path to the note (PDF or image). For a PDF,
            every page is rendered to a PNG. Pass the full path here — the tool
            cannot render anything without it. (If for any reason only `source`
            is available to you, you may pass the PATH as `source` instead and it
            will be used as the note path.)
        source: "file" (default) for a local PDF/image path; "goodnotes" is an
            alias for the same (GoodNotes PDF/PNG/JPG/HEIC exports). If given a
            filesystem path instead of "file"/"goodnotes", it is treated as the
            note path (fallback when ref is unavailable).
    Returns a dict with: page_images (PNG paths to read and transcribe),
    brief (the rules you must follow when transcribing), notes_root, and
    known_courses. On bad input returns {"error": ..., "page_images": []}.
    After calling this, READ every page image and transcribe it yourself, then
    decide the course and date (you build the section structure from content)."""
    return _prepare_note(source, ref)


@mcp.tool
def resolve_placement(course_hint: str, date: str, source_name: str = "") -> dict:
    """Resolve which course document a note goes into and its class date, so its
    placement can be confirmed with the user before writing. The note's internal
    section/subsection structure is authored by YOU during transcription (from
    the note's real topics) — it is NOT a placement input.

    Args:
        course_hint: the course name/number you inferred.
        date: the class date (any common format; normalized to ISO; forms the
            hidden duplicate-detection label with the source filename).
        source_name: the original note filename (e.g. "Bio 05.pdf"); with the
            date it predicts duplicates exactly as write_section will.
    Returns: course, course_status ("existing"/"new"), target_path, date_iso,
    date_display, duplicate (bool), match_confidence. Show this to the user and
    confirm before write_section. If match_confidence is "low", the course is
    "new", or date_iso is null, clear it up with the user first — do not assume."""
    return _resolve_placement(course_hint, date, source_name)


@mcp.tool
def write_section(course: str, latex_body: str, date: str,
                  source_name: str = "", course_number: str = "",
                  on_duplicate: str = "warn") -> dict:
    """Scaffold the course if new and file a transcribed note into it. Call only
    after the user confirms the course and date.

    The note is a self-contained block of LaTeX that YOU structure with its own
    \\section{...} and \\subsection{...} headings, reflecting the note's actual
    topics — a single note may contain SEVERAL sections (e.g. "Area" and
    "Volume" each as their own \\section). The server does not add or impose any
    section/subsection; it appends your block under a hidden date+filename label.

    Args:
        course: the confirmed course NAME (e.g. "<Course Name>"); also the folder.
        latex_body: your transcribed LaTeX — the BODY with its own
            \\section/\\subsection headings, but NO preamble, \\documentclass,
            \\begin{document}, or \\label line (the server adds the label).
        date: the confirmed class date (becomes part of the hidden \\label).
        source_name: the original note filename; with the date it is the dedup
            key (re-filing the same file replaces its prior block).
        course_number: the course NUMBER (e.g. "DEPT 10100") for the title page /
            running header; used only when scaffolding a new course. If omitted, a
            digit-bearing token from the course name is used.
        on_duplicate: "warn" (default; refuse if this file was already filed on
            this date), "replace" (replace that block), or "append" (add another).
    Returns {"written": true, target_path, diff_summary, compiled: false}, or
    {"written": false, "error": ...} on a duplicate/malformed document. The
    server is write-only and never compiles LaTeX."""
    return _write_section(course, latex_body, date, source_name,
                          course_number, on_duplicate)


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


@mcp.tool
def write_study_aid(course: str, kind: str, content: str) -> dict:
    """Write a study aid for a course. kind="guide" writes `content` (LaTeX body
    with its own \\section headings) as a SEPARATE standalone document
    study-guide.tex (its own \\documentclass/preamble is added by the server,
    sharing the course's packages + ExtFiles/; regenerating overwrites it, and it
    does NOT touch main.tex). kind="flashcards" writes `content` (tab-separated
    question<TAB>answer lines) to flashcards.tsv next to the course, for Anki.

    Args:
        course: the course NAME.
        kind: "guide" or "flashcards".
        content: for guide, the LaTeX BODY only (\\section/\\subsection + text,
            NO preamble/\\documentclass/\\begin{document}); for flashcards, TSV.
    Returns {"written": true, kind, path} or {"written": false, "error": ...}."""
    return _write_study_aid(course, kind, content)


@mcp.tool
def read_course(course: str) -> dict:
    """Read a course document's filed content and structure, for a whole-course
    pass (study guide, verification, figure captioning). Read-only.

    Args:
        course: the course NAME.
    Returns {"ok": true, course, target_path, notes: [{key,date,sections}],
    body: "<all filed note blocks as LaTeX>"} or {"ok": false, "error": ...}."""
    return _read_course(course)


@mcp.tool
def compile_course(course: str) -> dict:
    """Compile a course's main.tex to PDF (pdflatex → biber → pdflatex ×2).

    This is the ONE place the server compiles LaTeX; it is otherwise write-only.
    Requires a local TeX toolchain (MacTeX / TeX Live).

    Args:
        course: the course NAME (resolved to <notes_root>/<slug>/main.tex).
    Returns {"compiled": true, pdf, exists} on success, or {"compiled": false,
    failed_step, errors: [{message, line, context}], log_tail} on a LaTeX
    failure — the structured `errors` map each failure to the .tex line so it can
    be fixed. Returns {"compiled": false, "error": ...} if TeX or the file is
    missing."""
    return _compile_course(course)


@mcp.tool
def patch_note_region(course: str, note_key: str, new_body: str) -> dict:
    """Replace ONLY the body of one filed note (found by its date+filename key),
    leaving every other note untouched. Use to fix a single note that broke the
    build or was transcribed wrong — not to rewrite the document.

    Args:
        course: the course NAME.
        note_key: the note's composite key "DATE:filename-slug" (the text after
            `note:` in its \\label; from compile_course errors or the document).
        new_body: the corrected LaTeX body for that note (its own
            \\section/\\subsection headings, no \\label — that is preserved).
    Returns {"patched": true, target_path, note_key} or {"patched": false,
    "error": ...} (unknown key, unsafe body, or malformed document)."""
    return _patch_note_region(course, note_key, new_body)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
