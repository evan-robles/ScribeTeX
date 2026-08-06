# scribe-tex

A FastMCP server that files agent-transcribed handwritten notes into per-course
LaTeX documents. Notes are organized **by topic**: content lives under top-level
`\section` headings (e.g. "Characterization Techniques") and each note becomes
one or more `\subsection` under a chosen section. Each course document uses a
fixed template (full title page + table of contents + course preamble).

Input can be any PDF or image export from an iPad app — **GoodNotes**, Notability,
etc. (`source="file"`, or the `source="goodnotes"` alias).

The calling agent (e.g. Claude Code) does the vision transcription; this server
does deterministic, offline LaTeX placement only — it never compiles LaTeX and
never makes a network call.

## Install

```bash
pip install -e ".[dev]"
```

## MCP tools

- `prepare_note(source="file", ref)` — render a note export (PDF/PNG/JPG/HEIC)
  to page images and return a transcription brief + known courses.
  `source="goodnotes"` is an alias for GoodNotes exports.
- `resolve_placement(course_hint, section_hint, date)` — map to a course
  document and topic section, reporting new-vs-existing and any duplicate.
- `write_section(course, section_title, subsection_title, latex_body, date,
  course_number="", on_duplicate="warn")` — scaffold the course if new and add
  the note as a subsection under the given topic section.

Each note's subsection carries a hidden `\label{note:YYYY-MM-DD}` used only for
duplicate detection.

## Configuration

- `SCRIBE_TEX_NOTES_ROOT` — parent folder holding one repo per course.
  Default: `~/Desktop/College/Notes`.

## Register with an MCP client

First install the package so the `scribe-tex` console command resolves:

```bash
pip install -e .
```

Then add to your MCP client config (e.g. Claude Code `.mcp.json`, or the
`mcpServers` block of `~/.claude.json`):

```json
{
  "mcpServers": {
    "scribe-tex": {
      "command": "scribe-tex"
    }
  }
}
```

Or run directly: `python -m scribe_tex.server`. The server ships an
`instructions` prompt that tells the calling agent the exact prepare → transcribe
→ resolve → confirm → write workflow.

## Compiling a course

The server is write-only. Each course folder gets a full standalone template
(`main.tex` + a local `main.bib` + `ExtFiles/`). Because the template uses
`biblatex` with the `biber` backend, compile with:

```bash
pdflatex main && biber main && pdflatex main && pdflatex main
```

## Workflow

1. Drop a handwritten note export path into chat: *"process ~/Downloads/chem-nmr.pdf"*.
2. The agent calls `prepare_note`, reads the page images, transcribes to LaTeX,
   and decides a course, a top-level section (theme), a subsection title, and the
   date.
3. The agent calls `resolve_placement` and shows you the detected course, the
   chosen section (new vs existing), the date, and any duplicate — you confirm.
4. The agent calls `write_section`; the note is filed into the course's
   `main.tex` as a `\subsection` under the chosen topic `\section`.
