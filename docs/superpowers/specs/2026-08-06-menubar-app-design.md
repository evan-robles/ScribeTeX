# ScribeTeX Mac menu-bar app + iPad Shortcut — design

**Date:** 2026-08-06
**Author:** Evan S. Robles

## Context

ScribeTeX's auto-ingest (folder watch + sweep) works but is developer-facing:
CLI install, a TOML config, launchd agents. This design adds two friendly
front-ends so the user (and a few classmates) can use it without touching the
terminal:

1. A **native macOS menu-bar app** (SwiftUI `MenuBarExtra`) that drives the
   existing Python engine.
2. An **iPad Share-Sheet Shortcut** that sends a GoodNotes PDF into the watched
   inbox with one tap.

Audience: the user + a few (semi-technical) classmates. Distribution is FREE and
UNSIGNED — no Apple Developer Program ($99) required. Classmates open the
unsigned `.app` via right-click → Open once (Gatekeeper), or build from source in
Xcode with a free Apple ID.

## Decisions (from brainstorming)

- **Menu-bar app is native Swift/SwiftUI**, shelling out to the Python engine.
- **Engine invocation requires the Claude Code CLI** (`claude -p`) + the
  ScribeTeX plugin — no Anthropic API keys. The app detects it and guides setup.
- **v1 features:** status + filed count; pick inbox folder + start/stop watcher;
  review NeedsReview items; drag-drop / manual "Process a file…".
- **Build reality:** this repo's tooling is Python; Swift needs Xcode. The agent
  writes complete Swift source + an Xcode project + exact build instructions, but
  CANNOT compile or run-test the `.app`. Therefore the architecture pushes ALL
  logic into a Python JSON bridge (fully testable here); the Swift layer is a
  thin renderer of that bridge's JSON.
- **Distribution: free/unsigned.** Build instructions cover the one-time
  right-click→Open Gatekeeper step. Signing/notarization is explicitly out of
  scope (documented as an optional future step).
- **iPad Shortcut** is delivered as a step-by-step build recipe (Apple does not
  allow programmatically generating a signed `.shortcut`); it saves the shared
  PDF into the configured inbox folder.

## Architecture

```
iPad GoodNotes ──share──▶ Shortcut "Save File" ──▶ inbox (cloud-synced)
                                                       │
Mac menu-bar app (Swift) ──shell out──▶ appcli.py (JSON) ──▶ automation/ engine
   status / pick-inbox / start-stop / review / process        (existing, tested)
                                                       │
                                                launchd watcher + sweep (existing)
```

The Swift app never imports or reimplements engine logic. It runs
`python3 -m automation.appcli <cmd> [args]` and renders the JSON. That JSON
bridge is the ONLY new Python code, and it is fully unit-testable in this repo.

### Part A — `automation/appcli.py` (new, testable Python)

A JSON-in/JSON-out CLI. Every subcommand prints a single JSON object to stdout
and exits 0 (errors are reported as `{"ok": false, "error": ...}` with exit 0 so
the Swift side always gets parseable JSON; unexpected crashes exit nonzero).

Subcommands:
- `status` → `{ok, watcher_running, inbox_dir, filed_today, filed_total,
  needs_review_count, claude_ok, settle_seconds, sweep_seconds}`.
  - `watcher_running`: both launchd plists exist (via `install.plist_paths`).
  - `filed_today` / `filed_total`: count files under `done_dir(cfg)` (today =
    the `Done/YYYY-MM-DD/` matching a passed-in or injected date; total = all).
  - `needs_review_count`: count note files under `needs_review_dir(cfg)`
    (excluding the `.review.txt` / `.error.txt` sidecars).
  - `claude_ok`: `shutil.which(cfg["claude_bin"])` resolves.
- `needs-review` → `{ok, items: [{name, path, reason, kind}]}` where kind is
  "ambiguous" (`.review.txt`) or "error" (`.error.txt`); reason read from the
  sidecar; items without a sidecar still listed with reason null.
- `process --path <p>` → run one file through the engine now
  (reuse `process_inbox` semantics for a single file, or a focused
  `process_one`), return `{ok, outcome, result}`.
- `set-inbox --path <p>` → write `~/.config/scribetex/automation.toml` with
  `inbox_dir` (preserving other keys if present), create the folder +
  Done/NeedsReview/.scribetex, return `{ok, inbox_dir}`.
- `install` / `uninstall` → wrap `install.main([...])`, return `{ok, watcher_running}`.
- `sweep` → `process_inbox(cfg)`, return `{ok, processed: [...]}`.

All subcommands load config from the standard TOML path. Pure helpers
(`_status_dict(cfg, ...)`, `_needs_review_items(cfg)`, `_write_inbox_config(...)`)
are separated from `main(argv)` so tests exercise logic without argparse/stdout.
Injectable seams (now_fn, which_fn, a process fn) keep tests off the network and
off `claude`.

### Part B — `macapp/` (new, Swift — author only, user builds)

A SwiftUI menu-bar app. Files:
- `macapp/README.md` — exact Build/Run in Xcode, the free/unsigned distribution
  steps (zip the `.app`, right-click→Open on first launch), and the "requires
  Claude Code CLI + ScribeTeX plugin" prerequisite.
- `macapp/ScribeTeX.xcodeproj` (or a `Package.swift` + instructions if a raw
  xcodeproj is impractical to hand-author) — a minimal menu-bar app target.
- `macapp/ScribeTeX/ScribeTeXApp.swift` — `@main` `App` with `MenuBarExtra`.
- `macapp/ScribeTeX/Bridge.swift` — runs `python3 -m automation.appcli …` via
  `Process`, decodes the JSON into Codable structs. Locates the repo/python via a
  configurable path (stored in `UserDefaults`, set on first run through a
  "Locate ScribeTeX…" picker) — because an installed `.app` doesn't know where
  the repo lives.
- `macapp/ScribeTeX/Models.swift` — Codable structs mirroring appcli JSON.
- `macapp/ScribeTeX/MenuContent.swift` — the SwiftUI menu: status header, filed
  count, Start/Stop, Pick Inbox…, NeedsReview submenu, Process a File…, and a
  setup-guard row when `claude_ok` is false.
- Drag-drop: a small window/target accepting a file drop → `process`.

The Swift is written to be correct and idiomatic, but its verification is the
user running it in Xcode. To keep that safe, the JSON contract is frozen in Part
A's tests, so the Swift Codable structs have a stable, tested shape to match.

### Part C — iPad Shortcut (documentation deliverable)

`docs/shortcut-setup.md` — a precise recipe to build a Share-Sheet Shortcut:
1. New Shortcut, enable "Show in Share Sheet", accept Images/PDFs/Files.
2. Action "Save File" → destination = the SAME cloud folder configured as the
   Mac inbox (iCloud/Drive/Box), "Ask where to save" off, overwrite off.
3. Name it "ScribeTeX". Tap Share in GoodNotes → ScribeTeX → the Mac watcher
   files it.
Also note: the inbox folder must be the cloud-synced path the Mac app watches.

## Testing strategy

- `appcli`: unit-test every subcommand's pure helper — status dict shape +
  values (filed counts via fixture Done/ dirs; watcher_running via monkeypatched
  plist_paths; claude_ok via injected which_fn), needs-review parsing (ambiguous
  vs error sidecars, missing sidecar), set-inbox writes TOML + creates dirs,
  process/sweep/install wrappers via monkeypatched engine fns. Assert every
  subcommand emits valid JSON with `ok`. NO real claude/launchd/network.
- A JSON-contract test that locks the exact keys `status` returns (so the Swift
  Codable structs can't silently drift) — mirrors the earlier schema-shape
  guard pattern.
- Swift: NOT unit-tested here (no toolchain). The README build steps are the
  verification the user performs.

## Reuse (do not reimplement)

`automation.config` (load_config + all dir helpers), `automation.ingest`
(process_inbox / route), `automation.install` (main, plist_paths, preflight),
`automation.state` (error counts). appcli is a thin JSON adapter over these.

## Risks / caveats

- **Swift is author-only**: the agent cannot compile or run the `.app`; the user
  builds in Xcode. The frozen JSON contract + thin Swift layer minimize risk.
- **Unsigned distribution**: Gatekeeper warns on first open; documented
  right-click→Open workaround. Not signed/notarized (no $99 account) — an
  explicit, accepted tradeoff.
- **App must know the repo location**: an installed `.app` stores the ScribeTeX
  repo/python path in UserDefaults (set via a first-run picker); appcli itself is
  invoked as `python3 -m automation.appcli` with that repo on PYTHONPATH.
- **Still requires Claude Code CLI**: the app guides setup but cannot install it.
- **iPad Shortcut is a recipe, not a file**: Apple doesn't allow generating a
  signed `.shortcut`; the user assembles it (one-time, ~1 min).
- No change to `src/scribetex/` or existing automation behavior.

## Verification

- `pytest -q` green (existing 164 + new appcli tests).
- `python -m automation.appcli status` prints valid JSON on a temp config.
- `claude plugin validate .` still clean.
- User: open `macapp/` in Xcode → Build/Run; import the Shortcut per the recipe
  and share a PDF from GoodNotes → confirm it files.
