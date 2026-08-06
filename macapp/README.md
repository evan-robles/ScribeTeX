# ScribeTeX menu-bar app (macOS)

A tiny native SwiftUI menu-bar app that drives the ScribeTeX automation bridge.
It lives in the macOS menu bar (no Dock icon), shows how many notes were filed,
lets you start/stop the inbox watcher, pick your iPad inbox folder, review items
that couldn't be auto-filed, and process a single file on demand.

The app is a thin front-end: every action shells out to the Python bridge
(`python3 -m automation.appcli <command>`) inside your ScribeTeX checkout and
renders the JSON it returns. All the real work — filing, watching, Claude Code
invocation — happens in the repo, not in Swift.

---

## Prerequisites

1. **macOS 13 (Ventura) or newer.** The app uses SwiftUI's `MenuBarExtra`,
   which is only available on macOS 13+.
2. **A ScribeTeX repository checkout** on this Mac (you point the app at it on
   first run).
3. **Python 3** available at `/usr/bin/python3` (the system Python) or set a
   custom interpreter — see [Configuration](#configuration).
4. **Claude Code CLI + the ScribeTeX plugin installed.** Filing notes into LaTeX
   is performed by Claude Code, so the `claude` CLI must be installed and on your
   `PATH`, with the ScribeTeX plugin enabled. If it is missing, the app shows a
   setup warning ("Claude Code CLI + ScribeTeX plugin not detected") and filing
   will fail until you install it. Install Claude Code from Anthropic's official
   instructions, then run `Refresh` in the menu.
5. **Xcode 15+** and **XcodeGen** to build (see below).

---

## Build

The Xcode project is generated from `project.yml` with
[XcodeGen](https://github.com/yonaskolb/XcodeGen), so there is no checked-in
`.xcodeproj` to drift out of sync.

```bash
# 1. Install XcodeGen (once).
brew install xcodegen

# 2. Generate the Xcode project from the spec.
cd macapp
xcodegen generate

# 3. Open it in Xcode.
open ScribeTeX.xcodeproj
```

In Xcode: select the **ScribeTeX** scheme, then **Build/Run** (⌘R). The app has
no window — look for the ScribeTeX document icon in your menu bar (top-right).

> The target is configured `LSUIElement = true` (a menu-bar "agent" app), so it
> deliberately has **no Dock icon and no main window** — everything is in the
> menu-bar popover.

---

## First run

1. **Locate ScribeTeX…** — the first thing the menu shows is a prompt to locate
   your ScribeTeX repository checkout. Click it and choose the repo root
   (the folder containing the `automation` package / `src`). This path is
   remembered in `UserDefaults`.
2. **Pick Inbox…** — choose the folder your iPad drops handwritten notes into
   (e.g. an iCloud Drive folder). This calls `set-inbox` on the bridge.
3. **Start Watcher** — begins watching the inbox (`install`). Stop it any time
   with **Stop Watcher** (`uninstall`).
4. Drop a file onto the popover, or use **Process a File…**, to file a single
   note immediately.

If the **Claude Code** warning is showing, install the CLI + plugin first;
filing will not work without it.

---

## Review window

Some notes can't be auto-filed — the transcriber couldn't confidently infer the
course or date, so they're parked in a review queue instead of guessed into the
wrong place.

- **Notifications.** When new notes land in review, the app posts a native macOS
  notification ("N ScribeTeX note(s) need review"). macOS **prompts for
  notification permission on first launch**; if you decline, the queue still
  works — you just won't get banners. Tapping a notification brings the app
  forward and opens the Review window.
- **Opening it manually.** Use **Review Notes…** in the menu (shown whenever the
  queue is non-empty).
- **Re-filing.** Each parked note shows its name and the reason it was held,
  plus an editable form: a **Course** picker (populated from the courses already
  on disk, with a **New course…** option), **Section** / **Subsection** fields,
  and a **Date** picker. These are pre-filled from the transcriber's best-effort
  guesses when available. Click **Re-file** to file it with your corrections, or
  **Discard** to drop it from the queue without filing.

> ⚠️ **Re-filing re-transcribes the note.** It re-runs Claude on the image, so
> it **spends tokens and takes ~2 minutes.** The button is disabled while a
> bridge action is in flight.

---

## Free / unsigned distribution (no Apple Developer account)

You do **not** need a paid Apple Developer account to run or share this app.
The build is ad-hoc signed (`CODE_SIGN_IDENTITY = "-"`), which is fine for
personal use and sharing with a colleague.

To share the built app:

1. In Xcode, **Product ▸ Show Build Folder in Finder**, find `ScribeTeX.app`.
2. Zip it and send it to the other Mac.

On the receiving Mac, Gatekeeper will refuse to open an app from an
"unidentified developer" if you just double-click it. To get past this the
first time:

- **Right-click** (or Control-click) the `ScribeTeX.app` icon in Finder and
  choose **Open** from the context menu.
- In the dialog that appears, click **Open** again.

macOS then remembers your choice, and afterwards the app launches normally with
a plain double-click. (This right-click → **Open** step is only needed on the
first launch of an unsigned app.)

> **Optional, future step:** signing with a Developer ID certificate and
> notarizing the app would remove the right-click step entirely, but it is
> **not required** for this app and needs a paid Apple Developer account.

---

## Configuration

Two `UserDefaults` keys control the bridge invocation (both optional):

| Key | Meaning | Default |
| --- | --- | --- |
| `ScribeTeXRepoRoot` | Absolute path to the ScribeTeX checkout | set via **Locate ScribeTeX…** |
| `ScribeTeXPython` | Python interpreter used to run the bridge | `/usr/bin/python3` |

To use a virtualenv / Homebrew Python instead of the system one:

```bash
defaults write com.scribetex.menubar ScribeTeXPython /opt/homebrew/bin/python3
```

The bridge runs with `PYTHONPATH` set to `<repoRoot>:<repoRoot>/src` and the
working directory set to the repo root, so `python3 -m automation.appcli` is
importable without installing the package.

---

## What each menu action runs

Every action maps to one frozen `automation.appcli` command:

| Menu item | Bridge command |
| --- | --- |
| status header / Refresh | `status` |
| Needs Review submenu | `needs-review` |
| Pick Inbox… | `set-inbox --path <dir>` |
| Process a File… / drag-drop / review item | `process --path <file>` |
| Review window course picker | `known-courses` |
| Review window **Re-file** | `refile --path <file> --course C --section S --subsection Sub --date D` |
| Review window **Discard** | `discard --path <file>` |
| Start Watcher | `install` |
| Stop Watcher | `uninstall` |

---

## Files

| File | Purpose |
| --- | --- |
| `ScribeTeX/ScribeTeXApp.swift` | `@main` `MenuBarExtra` app + polling `AppModel` + notifications |
| `ScribeTeX/MenuContent.swift` | The menu-bar popover UI |
| `ScribeTeX/ReviewWindow.swift` | The Review window (re-file / discard parked notes) |
| `ScribeTeX/Bridge.swift` | `Process`-based wrapper around `automation.appcli` |
| `ScribeTeX/Models.swift` | `Codable` structs matching the bridge JSON contract |
| `ScribeTeX/Info.plist` | Bundle metadata (`LSUIElement`) |
| `project.yml` | XcodeGen spec that generates `ScribeTeX.xcodeproj` |
