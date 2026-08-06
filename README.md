# scribe-tex

A FastMCP server that files agent-transcribed handwritten notes into per-course
LaTeX documents, one dated `\section` per class, in date order.

The calling agent (e.g. Claude Code) does the vision transcription; this server
does deterministic, offline LaTeX placement only — it never compiles LaTeX and
never makes a network call.

## Install

```bash
pip install -e ".[dev]"
```

## MCP tools

- `prepare_note(source="file", ref)` — render a note export to page PNGs and
  return a transcription brief + known courses.
- `resolve_placement(course_hint, date)` — map to a course document and report
  where the dated section will land (and whether that date already exists).
- `write_section(course, date, latex_body, on_duplicate="warn")` — scaffold the
  course if new and insert the section in date order.

## Configuration

- `SCRIBE_TEX_NOTES_ROOT` — parent folder holding one repo per course.
  Default: `~/Desktop/College/Notes`.

## Register with an MCP client

Add to your MCP client config (e.g. Claude Code `.mcp.json`):

```json
{
  "mcpServers": {
    "scribe-tex": {
      "command": "scribe-tex"
    }
  }
}
```

Or run directly: `python -m scribe_tex.server`.

## Workflow

1. Drop a handwritten note export path into chat: *"process ~/Downloads/linalg-oct3.pdf"*.
2. The agent calls `prepare_note`, reads the page images, transcribes to LaTeX,
   and infers the course + date.
3. The agent calls `resolve_placement` and shows you the detected course, date,
   target file, and whether that date already exists — you confirm.
4. The agent calls `write_section`; the note is filed into the course's
   `main.tex` as a dated section, in date order.
