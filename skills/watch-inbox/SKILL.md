---
name: watch-inbox
description: Automatically transcribe and file handwritten note PDFs dropped into a watched inbox folder, via a headless Claude run triggered by macOS launchd.
category: general
---

# Watch Inbox

## Goal
Turn ScribeTeX push-based: drop a note PDF/image into a watched inbox folder and
have it automatically transcribed and filed into the right per-course LaTeX
document, with a desktop notification — no manual invocation.

## Instructions

1. **Choose an inbox folder** (any local or cloud-synced path — Box, Google
   Drive, iCloud Drive, or a plain folder). Set it in
   `~/.config/scribetex/automation.toml`:

   ```toml
   inbox_dir = "/Users/you/Library/CloudStorage/GoogleDrive-.../ScribeTeX-Inbox"
   sweep_seconds = 600
   settle_seconds = 4
   ```

   (Or the env var `SCRIBETEX_INBOX`.) Create the folder first.

2. **Install the launchd agents:**

   ```bash
   python scripts/run.py install
   ```

   This installs two agents: an instant folder-watch (fires when the inbox
   changes) and a 10-minute safety-net sweep. It refuses to install if the
   `claude` CLI, the ScribeTeX plugin, or the inbox folder are missing.

3. **Drop a note.** Export/share a PDF from GoodNotes (or any app) into the
   inbox. Within seconds the watcher transcribes and files it, then notifies you.

4. **Check status / sweep manually:**

   ```bash
   python scripts/run.py status
   python scripts/run.py sweep      # process the inbox once, now
   python scripts/run.py uninstall  # remove the agents
   ```

## Outcomes
- **Filed:** the PDF moves to `<inbox>/Done/YYYY-MM-DD/`; the LaTeX is written to
  the course document; you get a "Filed ..." notification.
- **Needs review:** if the course/section/date is ambiguous, nothing is written;
  the PDF moves to `<inbox>/NeedsReview/` with a `.review.txt` explaining why.
- **Error:** the PDF stays in the inbox and the next sweep retries.

## Constraints
- **macOS only** (uses launchd + osascript).
- **Cost:** each auto-run spends vision tokens; unattended transcription can
  misread handwriting. Filed results are reviewable via the notification and git
  history.
- **Requires** the `claude` CLI on PATH and the ScribeTeX plugin installed in the
  same environment launchd runs.
- **Write-only pipeline:** compilation is separate (`compile-course`).

---

**Author:** Evan S. Robles
**Contact:** [GitHub @evan-robles](https://github.com/evan-robles)
