# ScribeTeX product frontend — design

**Status:** approved via visual brainstorming (2026-08-07)
**Goal:** turn the menu-bar-popover utility into a product-grade macOS app with a
real main window where outputs (compiled PDF, study guide, flashcards) are viewed
*in the app*, and review/correction happen *inline* — while keeping the menu-bar
icon for at-a-glance status and quick "process a note".

---

## Decisions locked in the visual session

1. **Shell:** two-pane main window (sidebar · detail). Keep the menu-bar icon.
2. **Detail organization:** a top tab bar — **Notes · PDF · Study Guide ·
   Flashcards**. One view full-pane at a time (calm, not IDE-dense).
3. **Flashcards:** flip-card **study mode** (one card, flip Q/A, prev/next,
   progress) plus an "Export to Anki" button.
4. **Review & Correct:** folded **inline** into the detail pane — no more
   separate `NSWindow`s.

---

## Architecture

The app becomes a normal windowed SwiftUI app **plus** the existing menu-bar
extra. The Python bridge (`automation.appcli`) is unchanged — the frontend is
purely additive on top of the same JSON commands, with a few **new read-only
commands** to feed the viewers (list courses with metadata, read flashcards,
locate/produce PDFs).

- `ScribeTeXApp` gains a `WindowGroup` (the main window) alongside the
  `MenuBarExtra`. `LSUIElement` stays true; the main window is opened from the
  menu ("Open ScribeTeX") and via the Dock when visible. (We keep menu-bar mode;
  activation-policy flips to `.regular` while the main window is open, same
  pattern already used for the AppKit windows.)
- The three bolt-on AppKit windows (`ReviewWindowController`,
  `CorrectionWindowController`) are **retired** — their SwiftUI views
  (`ReviewWindow`, `CorrectionWindow` bodies) are refactored into inline detail
  panels reused inside the main window. The controllers/`NSWindow` plumbing is
  deleted.
- All long actions continue to route through `AppModel.perform(label){…}` (named
  status + elapsed timer + completion notification, already built).

### New Swift files
- `MainWindow.swift` — the `WindowGroup` scene + two-pane `NavigationSplitView`
  (sidebar + detail), owns the selected-course / selected-tab state.
- `Sidebar.swift` — courses list + "Needs review" section (badge count).
- `DetailPane.swift` — the top tab bar and switch between the four tab views +
  the two inline panels (review, correct).
- `NotesTab.swift` — the notes list for a course (date + section titles + figure/
  uncertain counts + a "Correct…" affordance per note).
- `PDFTab.swift` — PDFKit preview of the course PDF, with Compile / Compile+fix /
  Open-externally controls and a "not compiled yet" empty state.
- `FlashcardsTab.swift` — flip-card study deck (parses `flashcards.tsv`) +
  Generate / Export-to-Anki.
- `StudyGuideTab.swift` — Generate + PDFKit preview of `study-guide.pdf`
  (compiles `study-guide.tex` on demand).
- `ReviewPanel.swift` / `CorrectPanel.swift` — the inline review & correct views
  (refactored from the retired windows).

### Reused as-is
- `Bridge.swift` (add wrappers for new commands), `Models.swift` (add
  `CourseInfo`, reuse `NoteRef`/`ReviewItem`), `AppModel` (add
  selection state), `MenuContent.swift` (slims down — the rich actions move into
  the window; the menu keeps status + "Open ScribeTeX" + "Process a file" +
  Start/Stop watcher).

### New appcli commands (read-only unless noted)
- `courses-info` → `[{name, note_count, needs_review, has_pdf, pdf_path,
  has_guide, guide_pdf, flashcard_count}]` — powers the sidebar + tab enablement.
  (Composes existing `known_courses`, `list_notes`, filesystem checks.)
- `read-flashcards --course` → `{ok, cards:[{q,a}]}` — parses `flashcards.tsv`.
- `compile-guide --course` → compile `study-guide.tex` to PDF (new: the compile
  primitive currently targets `main.tex`; generalize `compile_course(main_tex)` —
  it already takes a path, so add a thin appcli command pointing at the guide).
- Existing commands unchanged: `status`, `needs-review`, `known-courses`,
  `list-notes`, `set-inbox`, `process`, `refile`, `discard`, `compile`, `build`,
  `open-pdf`, `study-guide`, `flashcards`, `verify`, `caption-figures`.

---

## The four tabs (detail pane)

**Notes** — the course's filed notes as cards: `date — section titles`, with
`N figures · M uncertain` metadata and a "Correct…" button that opens the inline
Correct panel. Empty state: "No notes filed yet."

**PDF** — a `PDFKit.PDFView` of `<course>/main.pdf`. Toolbar: **Compile**,
**Compile + auto-fix**, **Open in Preview**. If no PDF exists yet → empty state
with a Compile button. After a compile finishes (via `AppModel.perform`), the
view reloads the PDF. Compile errors surface in a banner (from the structured
`errors`), with a "Fix automatically" button (runs `build`).

**Study Guide** — **Generate study guide** button (runs the existing worker →
`study-guide.tex`), then a Compile-and-preview of `study-guide.pdf` in a PDFView.
Regenerating overwrites. Empty state before first generation.

**Flashcards** — flip-card study view over `flashcards.tsv`: a large card showing
the Question; **Flip** reveals the Answer; **Prev/Next** navigate; a "Card k of N"
+ progress bar. Toolbar: **Generate flashcards**, **Export to Anki** (reveals the
`.tsv` in Finder). Math renders as literal `$…$` text for v1 (no LaTeX
typesetting in-card — acceptable; the export carries the real content). Empty
state before first generation.

---

## Inline panels (replace pop-up windows)

**Review** (opened from a "Needs review" sidebar item): shows the note name, the
parked reason, a Course picker (existing courses + "New course"), a Date picker;
**Re-file** / **Discard**. Sections stay agent-generated. Reuses the current
review logic; just rendered in the detail pane instead of an `NSWindow`.

**Correct** (opened from a note's "Correct…" button): shows which note, a
multi-line plain-English instruction field, a "Re-read the original pages"
toggle, **Apply correction** / Back. Reuses the current correction logic inline.

Both run through `AppModel.perform` (named progress + notification) and, on
success, refresh the sidebar/notes and drop back to the relevant tab.

---

## Data flow

Selecting a course in the sidebar sets `AppModel.selectedCourse`; the detail pane
loads that course's notes (`list-notes`), flashcards (`read-flashcards`), and PDF
paths (`courses-info`) lazily per tab, off the main actor, applied on
`@MainActor`. Actions (compile/generate/refile/correct) call the bridge via
`perform`, then re-fetch the affected data. The 15s status poll continues to
drive the sidebar badge counts.

## Error handling

Every bridge call already returns `{ok:false,error}` or throws `BridgeError`
(with the timeout watchdog). Tabs show inline error text (not a modal); the PDF
tab shows compile errors as an actionable banner. Missing TeX toolchain →
friendly "Install MacTeX to compile" message on the PDF/Guide tabs.

## Testing

- Python: new appcli commands (`courses-info`, `read-flashcards`,
  `compile-guide`) get unit tests (JSON shape, empty/edge cases) — the Swift
  frontend is validated by the existing source-presence tests + manual ⌘R.
- Swift is authored, not unit-tested here (built in Xcode); add
  `test_macapp_review_sources`-style presence checks for the new files and Bridge
  commands so the JSON contract can't silently drift.

## Out of scope (v1)
- In-card LaTeX math typesetting (show `$…$` literally for now).
- Spaced-repetition scheduling in the flashcard viewer (export to Anki for that).
- Multi-window / tabs-per-course; iOS/iPad native app (the iPad round-trip stays
  the synced-PDF-folder approach from Batch C).

## Migration / risk notes
- Retiring the AppKit windows removes the macOS-26 `openWindow`-from-popover
  workaround; the main window is a normal `WindowGroup`, which is reliable. The
  activation-policy flip pattern is reused for showing the window from the menu.
- New Swift files require `xcodegen generate` before building (regenerates
  `project.pbxproj`).
- `NoteRef.sections` and the figure/uncertain counts: `list-notes` already
  returns sections; figure/uncertain counts need adding to `list_notes` (count
  `\includegraphics` and `\uncertain` within each note block) — small, additive.
