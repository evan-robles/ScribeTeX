"""FastMCP server: prepare_note, resolve_placement, write_section."""
from __future__ import annotations
from pathlib import Path

from fastmcp import FastMCP

from .config import notes_root
from .classify import parse_date, display_date, match_course, course_slug
from .discovery import known_courses
from .transcription_brief import build_brief
from .sources.base import get_source
from .scaffold import scaffold_course
from .writer import insert_section, DuplicateDateError, MalformedDocumentError
from .placement import plan_insertion

mcp = FastMCP("scribe-tex")


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
        if plan["after_date"]:
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
    """Render a note export to page PNGs and return a transcription brief."""
    return _prepare_note(source, ref)


@mcp.tool
def resolve_placement(course_hint: str, date: str) -> dict:
    """Map a note to a course document and report where its dated section lands."""
    return _resolve_placement(course_hint, date)


@mcp.tool
def write_section(course: str, date: str, latex_body: str,
                  on_duplicate: str = "warn") -> dict:
    """Scaffold the course if new and insert the dated section in date order."""
    return _write_section(course, date, latex_body, on_duplicate)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
