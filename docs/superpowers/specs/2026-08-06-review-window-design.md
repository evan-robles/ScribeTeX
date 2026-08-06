# ScribeTeX notification → Review window → inline re-file (design)

**Date:** 2026-08-06
**Author:** Evan S. Robles

## Context

When the auto-ingest watcher can't confidently determine a note's course /
section / date, it parks the PDF in `NeedsReview/` and (today) fires an
`osascript` notification. Two problems surfaced in real use:

1. **Clicking the notification opens Script Editor** — an `osascript`-posted
   notification is "owned" by Script Editor, so a click launches it (useless).
2. **No way to resolve a parked note from the UI** — the user must hand-edit
   files or re-drop the PDF, and a dateless note just bounces back to
   `NeedsReview/` (most handwritten notes have no written date).

This feature makes a parked note resolvable in one flow: **notification →
dedicated Review window → set course/section/date → Re-file**.

## Decisions (from brainstorming)

- **Review UI:** a dedicated **Review window** (a real `Window`, not the
  menu-bar popover — popovers are cramped for a form and awkward to auto-open).
- **Re-file mechanics:** **re-transcribe on re-file.** The sidecar saves the
  reason + Claude's best-guess course/section/date to **prefill** the form; on
  Re-file, Claude re-transcribes with the user-confirmed date/course (so real
  figure crops land in the now-known course). No LaTeX body is saved.
- **Course entry:** dropdown of **known courses** (from the notes tree) + free
  text for a new course, to avoid duplicate/misspelled course folders.
- **Notifications:** **the app owns notifications** (native
  `UNUserNotificationCenter`), fixing the Script Editor bug at the root and
  enabling click-to-Review. The headless launchd watcher **stays quiet** — the
  NeedsReview count is waiting when the user next opens the app.
- **Figures in parked notes:** because re-file re-transcribes, figures are
  handled correctly at re-file time (real crops into the resolved course). The
  parked sidecar itself stores no figures.

## Architecture

```
launchd watcher parks a note ─▶ NeedsReview/<name>.pdf
                                 NeedsReview/<name>.review.json  (reason + guesses)

Menu-bar app (running) ─ refresh ─▶ appcli needs-review ─▶ sees parked notes
   posts a native notification "N note(s) need review"
   click ─▶ opens the Review window
              ├─ lists parked notes (name, reason, prefilled course/section/date)
              ├─ course = dropdown(known courses) + free text
              └─ Re-file ─▶ appcli refile --path ... --course ... --date ...
                              └─ re-transcribes via claude, files into course,
                                 moves PDF to Done/<date>/, removes sidecar
```

The Swift app is a thin UI over new/So-far-tested appcli commands. All file/
placement logic stays in Python and is unit-tested here; only the notification
posting + the Review window are authored Swift verified by the user in Xcode.

## Part A — Python: richer parking sidecar (`.review.json`)

Today `route_file` writes `<name>.review.txt` with only a reason. Replace/augment
with a structured **`<name>.review.json`**:

```json
{
  "reason": "No class date could be determined ...",
  "kind": "ambiguous",
  "guess": {"course": "BIOS 20200", "section": "Receptors",
            "subsection": "Receptors", "date": null}
}
```

Changes:
- **`prompt.build_prompt`**: the ambiguous result shape gains best-guess fields:
  `{"status":"ambiguous","reason":...,"course":...,"section":...,"subsection":...,"date":...}`
  (any of course/section/subsection/date may be null). The instruction still says
  "do NOT write anything" when ambiguous — it just reports its guesses.
- **`prompt.parse_result`**: unchanged validation, but now tolerates the extra
  keys (already does — it returns the dict as-is once status is valid).
- **`ingest.route_file`** (ambiguous branch) and **`give_up_file`** (error
  branch): write `<name>.review.json` with `reason`, `kind`
  ("ambiguous"/"error"), and a `guess` object built from the result's
  course/section/subsection/date (nulls when absent). Keep writing the human
  `.review.txt`/`.error.txt` too (harmless, still readable) OR consolidate — the
  plan will consolidate to `.review.json` and drop the `.txt`, updating the
  needs-review reader accordingly.

## Part B — Python: `appcli` review + refile

- **`appcli needs-review`** item shape gains the prefill data (frozen-contract
  update): `{name, path, reason, kind, course, section, subsection, date}` where
  course/section/subsection/date come from the sidecar `guess` (null if unknown).
  Reads `.review.json` (falls back to legacy `.review.txt`/`.error.txt` for old
  parked notes: reason only, guesses null).
- **`appcli known-courses`** (new): returns `{"ok": true, "courses": [...]}` —
  the existing course folder names under the notes root (via
  `scribetex.discovery.known_courses` / `config.notes_root`). Powers the Review
  window's course dropdown.
- **`appcli refile`** (new): `refile --path <pdf> --course C --section S
  --subsection Sub --date D`. Steps:
  1. Validate the PDF is under `NeedsReview/` and exists; parse/validate the
     date (reuse `scribetex.classify.parse_date`); error JSON if unusable.
  2. Move the PDF back to the inbox root (so the normal pipeline can process it)
     OR process it in place — plan decides; simplest is: run a focused
     single-file transcription with the user's course/section/subsection/date
     **forced** (a `refile`-specific prompt that says "the course is C, the
     section is S, the date is D — transcribe and file, do not treat as
     ambiguous").
  3. On success: PDF moves to `Done/<date>/`, sidecar (`.review.json`) removed,
     return `{"ok": true, "filed": {...}}`.
  4. On failure: leave the note in `NeedsReview/`, return `{"ok": false,
     "error": ...}`.
- A new **`prompt.build_refile_prompt(note_path, course, section, subsection,
  date)`** that hard-codes the placement so Claude only transcribes + files
  (never re-parks). Its result contract reuses `SCRIBETEX_RESULT`.

## Part C — Swift: native notifications (fixes Script Editor)

- Add notification posting via **`UNUserNotificationCenter`** in the app: when
  `refresh()` sees `needs_review_count > 0` increase, post a local notification
  ("N ScribeTeX note(s) need review"). Request authorization on first launch.
- A `UNUserNotificationCenterDelegate` handles the click →
  **opens the Review window** and brings the app forward.
- **Remove the Python `osascript` notify path from the app-driven flow.** Since
  "app owns notifications," `ingest`/`appcli` no longer post toasts (the launchd
  watcher stays quiet). Keep `ingest.notify` callable but no longer invoked by
  the app pathway (plan decides whether to delete it or leave it dormant;
  leaving it unused-but-tested is fine, but the osascript call should not be the
  user-facing notifier anymore).

## Part D — Swift: the Review window

- A dedicated `Window` scene (id "review"), opened via `@Environment(\.openWindow)`
  from the notification handler and from a menu item ("Review Notes…").
- Lists parked notes from `Bridge.needsReview()`; each row/detail shows: name,
  reason, and editable fields:
  - **Course**: a `Picker` populated from `Bridge.knownCourses()` + a "New
    course…" free-text option.
  - **Section**, **Subsection**: text fields (prefilled from the guess).
  - **Date**: a `DatePicker` (prefilled from the guess if present, else today).
  - **Re-file** button → `Bridge.refile(path:course:section:subsection:date:)`;
    on success the row disappears and the window refreshes.
  - **Delete** button → removes the parked note + sidecar (a new
    `appcli discard --path` command, or reuse a delete; plan decides — keep it
    simple).
- Bridge additions (Swift): `knownCourses() -> [String]`,
  `refile(...) -> ActionResult`, matching the new appcli commands + frozen JSON.

## Testing strategy

Python (fully tested here):
- `prompt.build_prompt`: ambiguous contract documents the guess fields; the
  refile prompt hard-codes course/section/date and forbids re-parking.
- `route_file`/`give_up_file`: write a valid `.review.json` with reason/kind/guess
  (guess nulls when absent); handle a result with partial guesses.
- `appcli needs-review`: returns the new fields, reading `.review.json`, with
  legacy `.txt` fallback (guesses null).
- `appcli known-courses`: returns course folder names.
- `appcli refile`: happy path (monkeypatched transcription → files, moves PDF to
  Done, removes sidecar); bad date → error JSON, note stays; missing PDF →
  error; a not-in-NeedsReview path → error.
- Frozen-contract test updated for the new needs-review item keys + refile/
  known-courses result shapes.

Swift (authored; user verifies in Xcode):
- Notification posting + click→window, and the Review window — presence test
  (files exist, Bridge references the new commands) here; Build/Run by the user.

## Reuse (do not reimplement)

`scribetex.classify.parse_date`, `scribetex.discovery.known_courses`,
`scribetex.config` dirs, `automation.ingest.invoke_claude` (for the refile
transcription), the existing `resolve_placement`/`write_section` engine.

## Risks / caveats

- **Re-file spends tokens + ~2 min** (re-transcribes). Acceptable per decision;
  the window should show a progress state and disable Re-file while running.
- **Swift is authored, not compiled here** (notifications + window). The frozen
  JSON contract keeps the Swift structs stable; the user Builds/Runs in Xcode.
- **Notification authorization**: macOS will prompt for notification permission
  on first launch; if denied, the NeedsReview count in the app is the fallback.
- **Legacy parked notes** (existing `Bio 05.pdf.review.txt`) have no `.json` —
  the reader falls back to reason-only, guesses null; still re-fileable.
- No change to `src/scribetex/` behavior beyond additive use of its functions.

## Verification

- `pytest -q` green (existing 199 + new tests).
- `appcli needs-review` / `known-courses` / `refile` emit valid JSON on temp
  fixtures; refile happy-path moves a fixture PDF to Done and removes the sidecar
  (transcription monkeypatched).
- `claude plugin validate .` clean.
- User: Build/Run in Xcode → park a note → get a native notification → click →
  Review window → set course/date → Re-file → note lands in the course.
