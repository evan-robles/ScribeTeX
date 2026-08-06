# ScribeTeX auto-ingest (folder watch + scheduled sweep) — design

**Date:** 2026-08-06
**Author:** Evan S. Robles

## Context

ScribeTeX today is pull-based: the user invokes the agent and drives the
process-note pipeline (prepare_note → transcribe pages → resolve_placement →
write_section, embedding figures via save_figure). This design makes it
push-based on macOS: a note PDF/image dropped into a watched inbox triggers a
headless Claude run that files the transcription into the right course document
and notifies the user.

Two triggers, per the user's decision:
- **A — instant folder watch** (launchd `WatchPaths`): fires the moment the
  inbox changes.
- **E — scheduled sweep** (launchd `StartInterval`, every 10 min): safety net
  for anything the watcher missed (missed event, Mac asleep, partial sync).

## Decisions (from brainstorming)

- **Autonomy:** fully automatic write + notify. No pre-write approval gate.
- **Ambiguity:** if the agent cannot confidently resolve course/section/date, it
  does NOT guess — the file is moved to `NeedsReview/` with a sidecar note and
  the user is notified.
- **Trigger wiring:** two native launchd agents (WatchPaths + StartInterval).
  No Homebrew/fswatch dependency, survives reboot.
- **Inbox is provider-agnostic and configurable** (the user is undecided between
  Box / Google Drive / iCloud / a plain local folder). The watcher watches a
  configured path; it does not care which sync client owns it.
- **Ready check:** a file is processed only when its size is stable across two
  reads a few seconds apart AND it opens as a valid PDF (or is a valid image).
  This skips partial/placeholder/still-syncing files across any provider.
- **File lifecycle:** originals are never deleted. On success the PDF moves to
  `Done/YYYY-MM-DD/`; on ambiguity to `NeedsReview/`; on error it stays put for
  the next sweep.
- **Engine:** `claude -p` headless (reuses the shipped ScribeTeX plugin/MCP,
  skills, and the composite-key dedup / resolve-predicts-write guards), NOT a
  bespoke API script.
- **Notifications:** macOS `osascript` (built-in; no install).
- **Sweep interval:** every 10 minutes.

## Non-goals

- No Overleaf/GitHub publishing (separate future capability). This stops at
  "LaTeX filed into the local notes tree."
- No cross-platform support (macOS/launchd only for the triggers; the worker
  itself is plain Python and portable, but the installers are macOS).
- No change to the ScribeTeX MCP server or existing skills' behavior.

## Architecture

All new code lives under `automation/` plus one new skill.

```
inbox/ (configured path; Box/Drive/iCloud/local)
  ├─ new-note.pdf        ← drop target
  ├─ Done/YYYY-MM-DD/    ← moved here on success
  └─ NeedsReview/        ← moved here on ambiguity (+ .txt sidecar)

launchd:
  com.scribetex.watch  (WatchPaths=inbox) ──▶ ingest.py --once
  com.scribetex.sweep  (StartInterval=600) ─▶ ingest.py --sweep
                                                    │
                                                    ▼
                                   for each READY, unseen file:
                                     claude -p "<process prompt>"  (plugin loaded)
                                        → transcribe + resolve + write_section
                                     parse outcome → move file → osascript notify
```

### Components

**1. `automation/config.py` — configuration.**
- Reads a small config: inbox dir, notes root (delegates to
  `scribetex.config.notes_root` unless overridden), sweep interval, settle
  seconds, `claude` binary path, log path.
- Source of truth is env vars + an optional `~/.config/scribetex/automation.toml`
  (stdlib `tomllib`), so the inbox path is a one-line change when the user picks
  Box vs Drive. Sensible defaults; never raises on a missing optional file.
- Exposes typed getters: `inbox_dir()`, `done_dir()`, `needs_review_dir()`,
  `state_file()`, `lock_file()`, `log_file()`, `claude_bin()`,
  `settle_seconds()`, `sweep_seconds()`.

**2. `automation/readiness.py` — the ready check (pure, testable).**
- `is_ready(path, settle_seconds, now_fn, size_fn) -> bool`: size stable across
  two observations `settle_seconds` apart. (Injectable clock/size fns so tests
  don't sleep.)
- `is_valid_note(path) -> bool`: extension in the supported set AND, for `.pdf`,
  it opens with `fitz` (page count ≥ 1); for images, it opens with PIL. Malformed
  / zero-byte / placeholder → False.
- `_supported_ext` mirrors `scribetex.sources.file_source` (pdf, png, jpg, jpeg,
  heic).

**3. `automation/state.py` — idempotency + locking (pure where possible).**
- `load_seen(state_file) -> set[str]` / `mark_seen(state_file, key)`: a JSON set
  of processed identities. Identity = `f"{path.name}:{size}:{mtime_ns}"` so a
  re-dropped edited file re-processes but an unchanged one does not.
- `acquire_lock(lock_file) -> bool` / `release_lock(lock_file)`: an atomic
  `O_CREAT|O_EXCL` lockfile with the holder PID, so the watcher and the sweep
  never process concurrently. Stale-lock detection: if the PID is dead, reclaim.

**4. `automation/prompt.py` — the headless prompt contract.**
- `build_prompt(note_path) -> str`: returns the exact instruction handed to
  `claude -p`. It tells the agent to:
  - process EXACTLY this one file with the ScribeTeX tools (prepare_note →
    read every page image → transcribe per the brief → resolve_placement →
    write_section; embed drawings via save_figure per the figure priority);
  - if course/section/date is ambiguous or unresolvable, DO NOT guess — print a
    single line `SCRIBETEX_RESULT: {"status":"ambiguous","reason":"..."}` and
    stop without writing;
  - on a successful write, print a single line
    `SCRIBETEX_RESULT: {"status":"filed","course":"...","section":"...","subsection":"...","date":"...","target":"...","figures":N}`;
  - on any hard error, print `SCRIBETEX_RESULT: {"status":"error","reason":"..."}`.
- The `SCRIBETEX_RESULT:` line is the machine-readable contract the worker parses
  (last such line in stdout wins). Rationale: the worker must route the file
  without re-reading the notes tree.

**5. `automation/ingest.py` — the worker (the orchestrator).**
- `run_once()` (WatchPaths) and `run_sweep()` (StartInterval): both call the same
  `process_inbox()`; `--once` exists so the watcher reacts immediately, `--sweep`
  is identical in behavior (idempotency makes double-fire safe).
- `process_inbox()`:
  1. `acquire_lock()`; if not acquired, exit 0 (another run is active).
  2. List candidate files in `inbox_dir()` (top level only; ignore `Done/`,
     `NeedsReview/`, dotfiles).
  3. For each: skip if seen; skip if not `is_valid_note`; skip if not `is_ready`.
  4. `invoke_claude(note_path)` → capture stdout, parse the last
     `SCRIBETEX_RESULT:` JSON line via `parse_result(stdout)`.
  5. Route: `filed` → move to `Done/YYYY-MM-DD/`, notify success;
     `ambiguous` → move to `NeedsReview/`, write `<name>.review.txt` with the
     reason, notify; `error`/unparseable → leave in place, log, notify error
     (sweep retries).
  6. `mark_seen()` for `filed`/`ambiguous` (terminal outcomes) so they aren't
     redone; do NOT mark `error` (allow retry).
  7. `release_lock()` in a `finally`.
- `invoke_claude(note_path) -> str`: runs
  `[claude_bin, "-p", build_prompt(path)]` with a timeout, cwd = notes root,
  returns stdout. Errors (nonzero exit, timeout) become an `error` result.
- `parse_result(stdout) -> dict`: finds the last `SCRIBETEX_RESULT:` line,
  `json.loads` the payload; missing/malformed → `{"status":"error",...}`.
- `notify(title, message)`: `osascript -e 'display notification ...'`; failures
  are swallowed (never block ingest).
- Every run appends structured lines to `log_file()`.

**6. `automation/install.py` (or `.sh`) — the installer.**
- Renders `com.scribetex.watch.plist` (WatchPaths=inbox, ProgramArguments =
  `claude`-less: `python -m automation.ingest --once`) and
  `com.scribetex.sweep.plist` (StartInterval = sweep_seconds,
  `... --sweep`) with the configured inbox path substituted in.
- Writes them to `~/Library/LaunchAgents/`, `launchctl unload` (if present) then
  `launchctl load`.
- Pre-flight checks and FAILS LOUDLY if: `claude` not found on the launchd PATH,
  the ScribeTeX plugin not installed, the inbox dir doesn't exist, or Python
  can't import `automation`/`scribetex`. Prints exactly what to fix.
- Creates `inbox/Done/` and `inbox/NeedsReview/` if missing.
- `--uninstall` unloads and removes both plists.

**7. `skills/watch-inbox/` — a skill (SKILL.md + scripts).**
- Documents: what the automation does, the config file + env vars, how to set the
  inbox path (Box/Drive/iCloud/local examples), install/uninstall commands,
  where logs and Done/NeedsReview live, and the cost/handwriting caveats.
- `scripts/run.py`: a convenience CLI wrapping install/uninstall/status and a
  manual `--sweep` (self-locating like the other skills).

## Testing strategy

The worker's logic is pure/injectable so tests never sleep, never call `claude`,
never touch launchd:
- `readiness`: stable-size logic via injected size/clock fns; valid/invalid PDF
  via tiny fixtures (a real 1-page PDF, a zero-byte file, a truncated file).
- `state`: seen-set round-trip; identity changes when size/mtime change; lock
  acquire/blocked/stale-reclaim.
- `prompt`: contains the file path, the tool workflow, and the exact
  `SCRIBETEX_RESULT` contract + the "do not guess / ambiguous" instruction.
- `parse_result`: filed / ambiguous / error / missing-line / malformed-json /
  multiple-lines-last-wins.
- `ingest.process_inbox`: with `invoke_claude` monkeypatched to return canned
  `SCRIBETEX_RESULT` lines, assert routing — success moves to Done/, ambiguous
  moves to NeedsReview/ + sidecar, error leaves in place; seen-set prevents
  reprocessing; not-ready/invalid files are skipped; lock prevents concurrent
  runs. `osascript` is monkeypatched.
- `install`: renders plists with the configured path (assert WatchPaths /
  StartInterval / ProgramArguments); does NOT actually `launchctl load` in tests.

## Reuse (do not reimplement)

`scribetex.config.notes_root`, `scribetex.sources.file_source` supported
extensions, the process-note skill's workflow (invoked via `claude -p`, not
duplicated), `scribetex.classify.parse_date`/`course_slug` if the worker needs
to interpret a result.

## Risks / caveats (carry into README + skill)

- **Token cost:** each auto-run spends vision tokens; the seen-set + ready-check
  bound it, but it is real and unattended.
- **Handwriting misreads:** fully-auto means a wrong transcription can land; the
  notification + git history are the undo path (user chose auto over an approval
  gate).
- **launchd context:** headless `claude` runs under the user's launchd
  environment; it needs `claude` on PATH and the plugin installed there. The
  installer verifies and fails loudly otherwise.
- **Cloud sync partials:** the ready check mitigates but cannot perfectly
  guarantee a fully-synced file on every provider; the sweep re-attempts anything
  that was mid-sync.
- **Single-machine:** only runs while the Mac is awake; the sweep catches drops
  that arrived while asleep once it wakes.

## Verification

- `pytest -q` green (existing 103 + new automation tests).
- `python -m automation.ingest --sweep` on a temp inbox with a fixture PDF and a
  stubbed `claude` routes correctly (manual smoke).
- Installer dry-run renders valid plists containing the configured inbox path.
- `claude plugin validate .` still clean (new skill added).
