# ScribeTeX

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
- `resolve_placement(course_hint, section_hint, subsection_hint, date)` — map to
  a course document and topic section, reporting new-vs-existing and any
  duplicate.
- `write_section(course, section_title, subsection_title, latex_body, date,
  course_number="", on_duplicate="warn")` — scaffold the course if new and add
  the note as a subsection under the given topic section.
- `save_figure(course, page_image, bbox, name)` — crop a region of a rendered
  note page into the course's `ExtFiles/` so a freehand drawing can be embedded
  with `\includegraphics`. Use only when a figure can't be faithfully
  reproduced as TikZ/pgfplots/tabular.

Each note's subsection carries a hidden `\label{note:YYYY-MM-DD}` used only for
duplicate detection.

## Install as a Claude Code plugin (recommended)

This repo is a Claude Code plugin marketplace. Anyone can add it and get the MCP
server plus the skills, from within Claude Code:

```
/plugin marketplace add evan-robles/ScribeTeX
/plugin install scribetex@scribetex
```

On first session the plugin's `SessionStart` hook installs the Python
dependencies (`fastmcp`, `pymupdf`, `python-dateutil`) if they are missing, and
the MCP server is launched via `python3 -m scribetex.server` with
`PYTHONPATH=${CLAUDE_PLUGIN_ROOT}/src` — no manual `pip install` required.

## Skills

The plugin bundles four self-contained skills (each a `SKILL.md` + `scripts/`):

- **process-note** — render a note export and file a transcription under a topic
  section of a course document (the end-to-end workflow).
- **new-course** — scaffold a new course document (title page + preamble +
  sidecars) up front.
- **list-courses** — inventory the courses, their topic sections, and note counts.
- **compile-course** — build a course's `main.tex` to PDF via
  `pdflatex → biber → pdflatex → pdflatex` (requires a local TeX install; this is
  the only place ScribeTeX compiles).

## Figures

When a note contains a chart, table, or graph, reproduce it in LaTeX first —
TikZ/pgfplots for plots and diagrams, `tabular` for tables — so it stays
editable and renders crisply. Only fall back to embedding a cropped image of a
freehand drawing (something that genuinely can't be redrawn in LaTeX) via
`save_figure(course, page_image, bbox, name)`, where `bbox` is
`[x0, y0, x1, y1]` as fractions in `[0,1]` of the page (origin top-left); this
crops the region into the course's `ExtFiles/` and returns a ready
`\includegraphics` snippet. Prose description is the last resort, when neither
LaTeX reproduction nor a figure crop is practical.

## Configuration

- `SCRIBETEX_NOTES_ROOT` — parent folder holding one repo per course.
  Default: `~/Desktop/College/Notes`.

## Register with an MCP client

First install the package so the `scribetex` console command resolves:

```bash
pip install -e .
```

Then add to your MCP client config (e.g. Claude Code `.mcp.json`, or the
`mcpServers` block of `~/.claude.json`):

```json
{
  "mcpServers": {
    "ScribeTeX": {
      "command": "scribetex"
    }
  }
}
```

Or run directly: `python -m scribetex.server`. The server ships an
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
