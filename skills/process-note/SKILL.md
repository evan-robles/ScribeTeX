---
name: process-note
description: Turn a handwritten iPad/GoodNotes note export into a typeset LaTeX subsection filed under a topic section of a per-course document.
category: general
---

# Process Note

## Goal
Take one handwritten note export (PDF or image, e.g. from GoodNotes) and file a
faithful LaTeX transcription of it into the correct per-course document — as a
`\subsection` under a chosen top-level topic `\section`, using the course's fixed
template. Transcription is done by you (the calling agent) from the rendered page
images; placement and file writing are deterministic.

## Instructions

1. **Prepare the note** — render its pages and get the transcription brief:

   ```bash
   python skills/process-note/scripts/run.py <path-to-note.pdf-or-image> --source file
   ```

   Use `--source goodnotes` for a GoodNotes export (same handling; documents
   intent). The script prints JSON: `page_images` (PNG paths), `brief` (the rules
   you must follow), `notes_root`, and `known_courses`. If it prints an `error`,
   report it and stop.

2. **Transcribe (you).** Read EVERY page image and transcribe to LaTeX, obeying
   the `brief`: body only (no preamble, no `\section`/`\subsection`/`\label` —
   the server adds those), `\subsection` structure per topic, `$...$`/`align`
   for math, `\ce{...}` for chemistry, only the listed packages/macros.
   Transcribe faithfully; never invent content. Render hand-drawn diagrams you
   cannot reproduce as faithful prose/equations, and tell the user which ones.
   Also decide: the **course**, a top-level **section** title (the theme), a
   concise **subsection** title, and the **date**. Ask the user if any is
   ambiguous.

3. **Resolve + confirm.** Call the `resolve_placement` MCP tool with the course,
   section, and date. Show the user the resolved course (new/existing), the
   chosen section (new/existing), the date, and any duplicate — get confirmation.

4. **Write.** Call the `write_section` MCP tool (course, course_number,
   section_title, subsection_title, latex_body, date). Report the target path and
   what was described vs. reproduced.

## Examples

Prepare a GoodNotes chemistry note for transcription:
```bash
python skills/process-note/scripts/run.py ~/Downloads/chem-nmr.pdf --source goodnotes
```

## Constraints
- **Environment**: requires the `scribe_tex` package importable and its deps
  (`fastmcp`, `pymupdf`, `python-dateutil`); the plugin's SessionStart hook
  installs them.
- **Agent-transcribed**: this skill never runs a vision model itself; you do the
  transcription from the page images.
- **Write-only**: this skill does not compile LaTeX. Use the `compile-course`
  skill to build a PDF.

---

**Author:** Evan S. Robles
**Contact:** [GitHub @evan-robles](https://github.com/evan-robles)
