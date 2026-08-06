# ScribeTeX Menu-Bar App + iPad Shortcut Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a friendly front-end to ScribeTeX auto-ingest: a testable Python JSON bridge (`automation/appcli.py`), a native SwiftUI menu-bar app that renders it (authored for the user to build in Xcode), and an iPad Share-Sheet Shortcut recipe.

**Architecture:** The Swift app never reimplements engine logic — it shells out to `python3 -m automation.appcli <cmd>` which returns JSON, wrapping the existing `automation/` engine. The Python bridge is the ONLY new testable code and its JSON contract is frozen by tests so the Swift Codable structs have a stable shape. Swift + Shortcut are authored deliverables verified by the user (no Swift toolchain here).

**Tech Stack:** Python 3.11+ (stdlib json/argparse/shutil/pathlib), the existing `automation` package, SwiftUI (`MenuBarExtra`, authored only), Apple Shortcuts (recipe only).

## Global Constraints

- Work in the worktree `/Users/evane/Desktop/Projects/ScribeTeX/.worktrees/menubar-app` on branch `menubar-app`. Run tests from the worktree root.
- The Python bridge `automation/appcli.py` is the testable core. Every subcommand prints ONE JSON object to stdout and exits 0; recoverable errors are `{"ok": false, "error": "..."}` (still exit 0) so the Swift side always gets parseable JSON.
- Separate pure helpers (`_status_dict`, `_needs_review_items`, `_write_inbox_config`, `_process_path`) from `main(argv)` so tests exercise logic without argparse/stdout. Inject seams (`now_fn`, `which_fn`, a process fn) so tests never call `claude`, `launchctl`, or the network.
- Reuse ONLY (do not reimplement): `automation.config` (`load_config`, `done_dir`, `needs_review_dir`, `state_file`, `error_file`, `lock_file`), `automation.ingest` (`process_inbox`), `automation.install` (`main`, `plist_paths`), `automation.state`.
- The standard config path is `~/.config/scribetex/automation.toml` (same as `install.main` / `ingest.main` use).
- Config helpers take the loaded `cfg` dict and return `Path`s. `plist_paths(cfg)` returns `{"watch": Path, "sweep": Path}`.
- Do NOT modify `src/scribetex/`, existing `automation/*.py`, or existing skills. Only ADD `automation/appcli.py`, its tests, the `macapp/` Swift sources, and docs.
- Swift/Shortcut deliverables are AUTHORED, not compiled/tested here. Their verification is the user's Xcode build / Shortcut import, documented in their READMEs.
- Distribution is free/unsigned: build docs must include the Gatekeeper right-click→Open step and must NOT require an Apple Developer account.

---

### Task 1: `appcli` status + JSON contract

**Files:**
- Create: `automation/appcli.py`
- Test: `tests/test_appcli_status.py`

**Interfaces:**
- Consumes: `config.load_config/done_dir/needs_review_dir`, `install.plist_paths`.
- Produces:
  - `_status_dict(cfg, *, plist_paths_fn, which_fn, now_fn) -> dict` with EXACT keys: `ok`(True), `watcher_running`(bool: both plists exist), `inbox_dir`(str), `filed_today`(int), `filed_total`(int), `needs_review_count`(int), `claude_ok`(bool: which_fn(cfg["claude_bin"]) truthy), `settle_seconds`(int), `sweep_seconds`(int).
    - `filed_today` = count of files under `done_dir(cfg)/<now_fn().strftime("%Y-%m-%d")>/` (0 if absent).
    - `filed_total` = count of files under all `done_dir(cfg)/*/` subdirs.
    - `needs_review_count` = count of files under `needs_review_dir(cfg)` whose suffix is NOT `.txt` (exclude `.review.txt`/`.error.txt` sidecars).
  - `main(argv=None) -> int` — argparse with subcommands; `status` prints `json.dumps(_status_dict(...))`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_appcli_status.py
import datetime
import json
from pathlib import Path
from automation import appcli, config


def _cfg(tmp_path):
    return config.load_config(env={"SCRIBETEX_INBOX": str(tmp_path)}, toml_path=None)


def _touch(p):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x")


def test_status_keys_and_types(tmp_path):
    cfg = _cfg(tmp_path)
    st = appcli._status_dict(
        cfg,
        plist_paths_fn=lambda c: {"watch": tmp_path / "w.plist", "sweep": tmp_path / "s.plist"},
        which_fn=lambda b: "/usr/local/bin/claude",
        now_fn=lambda: datetime.datetime(2026, 8, 6),
    )
    for k in ("ok", "watcher_running", "inbox_dir", "filed_today", "filed_total",
              "needs_review_count", "claude_ok", "settle_seconds", "sweep_seconds"):
        assert k in st, f"missing key {k}"
    assert st["ok"] is True
    assert st["claude_ok"] is True
    assert st["watcher_running"] is False  # plists don't exist


def test_status_counts(tmp_path):
    cfg = _cfg(tmp_path)
    # 2 filed today, 1 filed on another day -> total 3
    _touch(tmp_path / "Done" / "2026-08-06" / "a.pdf")
    _touch(tmp_path / "Done" / "2026-08-06" / "b.pdf")
    _touch(tmp_path / "Done" / "2026-08-01" / "c.pdf")
    # 1 needs-review note + its sidecar (sidecar must NOT be counted)
    _touch(tmp_path / "NeedsReview" / "d.pdf")
    _touch(tmp_path / "NeedsReview" / "d.pdf.review.txt")
    st = appcli._status_dict(
        cfg,
        plist_paths_fn=lambda c: {"watch": tmp_path / "w", "sweep": tmp_path / "s"},
        which_fn=lambda b: None,
        now_fn=lambda: datetime.datetime(2026, 8, 6),
    )
    assert st["filed_today"] == 2
    assert st["filed_total"] == 3
    assert st["needs_review_count"] == 1
    assert st["claude_ok"] is False


def test_status_watcher_running_when_both_plists_exist(tmp_path):
    cfg = _cfg(tmp_path)
    w = tmp_path / "w.plist"; s = tmp_path / "s.plist"
    w.write_text("x"); s.write_text("x")
    st = appcli._status_dict(
        cfg, plist_paths_fn=lambda c: {"watch": w, "sweep": s},
        which_fn=lambda b: "claude", now_fn=lambda: datetime.datetime(2026, 8, 6),
    )
    assert st["watcher_running"] is True


def test_status_subcommand_emits_json(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SCRIBETEX_INBOX", str(tmp_path))
    monkeypatch.setattr(appcli, "_config_toml_path", lambda: tmp_path / "none.toml")
    rc = appcli.main(["status"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True
    assert "watcher_running" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/evane/Desktop/Projects/ScribeTeX/.worktrees/menubar-app && python -m pytest tests/test_appcli_status.py -v`
Expected: FAIL (`automation.appcli` missing).

- [ ] **Step 3: Write minimal implementation**

Create `automation/appcli.py`:
```python
"""JSON bridge CLI for the ScribeTeX menu-bar app.

Each subcommand prints ONE JSON object to stdout and exits 0. Recoverable
errors are reported as {"ok": false, "error": ...} (still exit 0) so the Swift
caller always receives parseable JSON.
"""
from __future__ import annotations
import argparse
import datetime as _dt
import json
import shutil
import sys
from pathlib import Path

from . import config as _config
from . import ingest as _ingest
from . import install as _install


def _config_toml_path() -> Path:
    return Path.home() / ".config" / "scribetex" / "automation.toml"


def _load(argv_inbox=None):
    return _config.load_config(toml_path=_config_toml_path())


def _count_files(d: Path) -> int:
    if not d.exists():
        return 0
    return sum(1 for p in d.iterdir() if p.is_file())


def _status_dict(cfg, *, plist_paths_fn=None, which_fn=None, now_fn=None) -> dict:
    plist_paths_fn = plist_paths_fn or _install.plist_paths
    which_fn = which_fn or shutil.which
    now_fn = now_fn or _dt.datetime.now

    paths = plist_paths_fn(cfg)
    watcher_running = paths["watch"].exists() and paths["sweep"].exists()

    done = _config.done_dir(cfg)
    today = now_fn().strftime("%Y-%m-%d")
    filed_today = _count_files(done / today)
    filed_total = 0
    if done.exists():
        for sub in done.iterdir():
            if sub.is_dir():
                filed_total += _count_files(sub)

    nr = _config.needs_review_dir(cfg)
    needs_review_count = 0
    if nr.exists():
        needs_review_count = sum(
            1 for p in nr.iterdir() if p.is_file() and p.suffix != ".txt"
        )

    return {
        "ok": True,
        "watcher_running": bool(watcher_running),
        "inbox_dir": str(cfg["inbox_dir"]),
        "filed_today": filed_today,
        "filed_total": filed_total,
        "needs_review_count": needs_review_count,
        "claude_ok": bool(which_fn(cfg["claude_bin"])),
        "settle_seconds": int(cfg["settle_seconds"]),
        "sweep_seconds": int(cfg["sweep_seconds"]),
    }


def _emit(obj) -> int:
    print(json.dumps(obj))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="ScribeTeX app JSON bridge.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    args = ap.parse_args(argv)

    cfg = _load()
    if args.cmd == "status":
        return _emit(_status_dict(cfg))
    return _emit({"ok": False, "error": f"unknown command: {args.cmd}"})


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/evane/Desktop/Projects/ScribeTeX/.worktrees/menubar-app && python -m pytest tests/test_appcli_status.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add automation/appcli.py tests/test_appcli_status.py
git commit -m "feat: appcli status subcommand + JSON contract"
```

---

### Task 2: `appcli needs-review`

**Files:**
- Modify: `automation/appcli.py`
- Test: `tests/test_appcli_needs_review.py`

**Interfaces:**
- Produces:
  - `_needs_review_items(cfg) -> list[dict]` — one entry per note file (suffix != `.txt`) in `needs_review_dir(cfg)`: `{"name": str, "path": str, "reason": str|None, "kind": "ambiguous"|"error"|"unknown"}`.
    - kind/reason: if a sibling `<name>.review.txt` exists → kind "ambiguous", reason = its text stripped; elif `<name>.error.txt` → kind "error", reason = its text; else kind "unknown", reason None.
  - `needs-review` subcommand → `_emit({"ok": True, "items": _needs_review_items(cfg)})`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_appcli_needs_review.py
from pathlib import Path
from automation import appcli, config


def _cfg(tmp_path):
    return config.load_config(env={"SCRIBETEX_INBOX": str(tmp_path)}, toml_path=None)


def _mk(p, text=None):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x")


def test_needs_review_parses_sidecars(tmp_path):
    cfg = _cfg(tmp_path)
    nr = tmp_path / "NeedsReview"
    nr.mkdir(parents=True)
    (nr / "amb.pdf").write_bytes(b"x")
    (nr / "amb.pdf.review.txt").write_text("Needs review: course unclear\n")
    (nr / "err.pdf").write_bytes(b"x")
    (nr / "err.pdf.error.txt").write_text("failed: boom\n")
    (nr / "bare.pdf").write_bytes(b"x")  # no sidecar

    items = {i["name"]: i for i in appcli._needs_review_items(cfg)}
    assert set(items) == {"amb.pdf", "err.pdf", "bare.pdf"}
    assert items["amb.pdf"]["kind"] == "ambiguous"
    assert "course unclear" in items["amb.pdf"]["reason"]
    assert items["err.pdf"]["kind"] == "error"
    assert "boom" in items["err.pdf"]["reason"]
    assert items["bare.pdf"]["kind"] == "unknown"
    assert items["bare.pdf"]["reason"] is None


def test_needs_review_empty_when_no_dir(tmp_path):
    cfg = _cfg(tmp_path)
    assert appcli._needs_review_items(cfg) == []


def test_needs_review_subcommand_json(tmp_path, monkeypatch, capsys):
    import json
    monkeypatch.setenv("SCRIBETEX_INBOX", str(tmp_path))
    monkeypatch.setattr(appcli, "_config_toml_path", lambda: tmp_path / "none.toml")
    (tmp_path / "NeedsReview").mkdir(parents=True)
    (tmp_path / "NeedsReview" / "x.pdf").write_bytes(b"x")
    rc = appcli.main(["needs-review"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True
    assert out["items"][0]["name"] == "x.pdf"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/evane/Desktop/Projects/ScribeTeX/.worktrees/menubar-app && python -m pytest tests/test_appcli_needs_review.py -v`
Expected: FAIL (`_needs_review_items` missing / subcommand not registered).

- [ ] **Step 3: Write minimal implementation**

In `automation/appcli.py`, add:
```python
def _needs_review_items(cfg) -> list:
    nr = _config.needs_review_dir(cfg)
    if not nr.exists():
        return []
    items = []
    for p in sorted(nr.iterdir()):
        if not p.is_file() or p.suffix == ".txt":
            continue
        review = nr / f"{p.name}.review.txt"
        error = nr / f"{p.name}.error.txt"
        if review.exists():
            kind, reason = "ambiguous", review.read_text().strip()
        elif error.exists():
            kind, reason = "error", error.read_text().strip()
        else:
            kind, reason = "unknown", None
        items.append({"name": p.name, "path": str(p), "reason": reason, "kind": kind})
    return items
```
Register the subcommand in `main`: `sub.add_parser("needs-review")` and handle
`if args.cmd == "needs-review": return _emit({"ok": True, "items": _needs_review_items(cfg)})`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/evane/Desktop/Projects/ScribeTeX/.worktrees/menubar-app && python -m pytest tests/test_appcli_needs_review.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add automation/appcli.py tests/test_appcli_needs_review.py
git commit -m "feat: appcli needs-review subcommand"
```

---

### Task 3: `appcli set-inbox`

**Files:**
- Modify: `automation/appcli.py`
- Test: `tests/test_appcli_set_inbox.py`

**Interfaces:**
- Produces:
  - `_write_inbox_config(inbox_path, toml_path) -> dict` — ensure `toml_path`'s parent exists; read existing TOML (tomllib) if present; set `inbox_dir` to the expanduser'd absolute path; write it back as TOML (hand-render simple `key = "value"` lines — stdlib has no TOML writer; only string/int keys are used). Create the inbox dir + `Done/`, `NeedsReview/`, `.scribetex/`. Return `{"ok": True, "inbox_dir": str}`.
  - `set-inbox --path P` subcommand → calls `_write_inbox_config(P, _config_toml_path())` and emits it.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_appcli_set_inbox.py
import json
import tomllib
from pathlib import Path
from automation import appcli


def test_write_inbox_creates_config_and_dirs(tmp_path):
    toml = tmp_path / "cfg" / "automation.toml"
    inbox = tmp_path / "MyInbox"
    res = appcli._write_inbox_config(str(inbox), toml)
    assert res["ok"] is True
    assert res["inbox_dir"] == str(inbox)
    # config written + parseable
    data = tomllib.loads(toml.read_text())
    assert data["inbox_dir"] == str(inbox)
    # dirs created
    assert (inbox / "Done").is_dir()
    assert (inbox / "NeedsReview").is_dir()
    assert (inbox / ".scribetex").is_dir()


def test_write_inbox_preserves_other_keys(tmp_path):
    toml = tmp_path / "automation.toml"
    toml.write_text('sweep_seconds = 300\ninbox_dir = "/old"\n')
    appcli._write_inbox_config(str(tmp_path / "new"), toml)
    data = tomllib.loads(toml.read_text())
    assert data["inbox_dir"] == str(tmp_path / "new")
    assert data["sweep_seconds"] == 300  # preserved


def test_set_inbox_subcommand_json(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(appcli, "_config_toml_path", lambda: tmp_path / "automation.toml")
    rc = appcli.main(["set-inbox", "--path", str(tmp_path / "Inbox")])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True
    assert out["inbox_dir"] == str(tmp_path / "Inbox")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/evane/Desktop/Projects/ScribeTeX/.worktrees/menubar-app && python -m pytest tests/test_appcli_set_inbox.py -v`
Expected: FAIL.

- [ ] **Step 3: Write minimal implementation**

In `automation/appcli.py`, add:
```python
def _render_toml(data: dict) -> str:
    lines = []
    for k, v in data.items():
        if isinstance(v, str):
            lines.append(f'{k} = "{v}"')
        elif isinstance(v, bool):
            lines.append(f"{k} = {'true' if v else 'false'}")
        else:
            lines.append(f"{k} = {v}")
    return "\n".join(lines) + "\n"


def _write_inbox_config(inbox_path, toml_path) -> dict:
    import tomllib
    toml_path = Path(toml_path)
    toml_path.parent.mkdir(parents=True, exist_ok=True)
    data = {}
    if toml_path.exists():
        try:
            data = tomllib.loads(toml_path.read_text())
        except Exception:
            data = {}
    inbox = str(Path(inbox_path).expanduser())
    data["inbox_dir"] = inbox
    toml_path.write_text(_render_toml(data))
    for sub in ("Done", "NeedsReview", ".scribetex"):
        (Path(inbox) / sub).mkdir(parents=True, exist_ok=True)
    return {"ok": True, "inbox_dir": inbox}
```
Register: `sp = sub.add_parser("set-inbox"); sp.add_argument("--path", required=True)` and in the dispatch `if args.cmd == "set-inbox": return _emit(_write_inbox_config(args.path, _config_toml_path()))`.

Note: `set-inbox` must write config BEFORE `_load()` is used, so move the `cfg = _load()` call to only the subcommands that need it (status/needs-review), OR load lazily. Simplest: load cfg lazily inside each branch that needs it, not once at the top.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/evane/Desktop/Projects/ScribeTeX/.worktrees/menubar-app && python -m pytest tests/test_appcli_set_inbox.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add automation/appcli.py tests/test_appcli_set_inbox.py
git commit -m "feat: appcli set-inbox writes config + creates dirs"
```

---

### Task 4: `appcli process / sweep / install / uninstall`

**Files:**
- Modify: `automation/appcli.py`
- Test: `tests/test_appcli_actions.py`

**Interfaces:**
- Produces:
  - `_process_path(cfg, src_path, *, process_fn=None) -> dict` — copy `src_path` into `inbox_dir` (if not already there), then run `process_fn(cfg)` (default `ingest.process_inbox`); return `{"ok": True, "processed": [...]}` (the list process_inbox returns). If `src_path` missing → `{"ok": False, "error": "file not found: ..."}`.
  - subcommands: `process --path P` → `_process_path`; `sweep` → `{"ok": True, "processed": ingest.process_inbox(cfg)}`; `install` → run `install.main([])`, then emit `{"ok": rc==0, "watcher_running": <both plists exist>}`; `uninstall` → `install.main(["--uninstall"])`, emit `{"ok": True, "watcher_running": False}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_appcli_actions.py
import json
from pathlib import Path
from automation import appcli, config


def _cfg(tmp_path):
    return config.load_config(env={"SCRIBETEX_INBOX": str(tmp_path)}, toml_path=None)


def test_process_copies_into_inbox_and_runs(tmp_path):
    cfg = _cfg(tmp_path)
    (tmp_path).mkdir(parents=True, exist_ok=True)
    src = tmp_path / "outside" / "note.pdf"
    src.parent.mkdir(parents=True)
    src.write_bytes(b"%PDF-1.4")
    captured = {}
    def fake_process(c):
        captured["ran"] = True
        return [{"file": "note.pdf", "outcome": "filed", "result": {"status": "filed"}}]
    res = appcli._process_path(cfg, str(src), process_fn=fake_process)
    assert res["ok"] is True
    assert captured.get("ran") is True
    assert (tmp_path / "note.pdf").exists()   # copied into inbox
    assert res["processed"][0]["outcome"] == "filed"


def test_process_missing_file(tmp_path):
    cfg = _cfg(tmp_path)
    res = appcli._process_path(cfg, str(tmp_path / "nope.pdf"), process_fn=lambda c: [])
    assert res["ok"] is False
    assert "file not found" in res["error"]


def test_sweep_subcommand(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SCRIBETEX_INBOX", str(tmp_path))
    monkeypatch.setattr(appcli, "_config_toml_path", lambda: tmp_path / "none.toml")
    monkeypatch.setattr(appcli._ingest, "process_inbox", lambda c: [])
    rc = appcli.main(["sweep"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True


def test_install_subcommand_wraps_install_main(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SCRIBETEX_INBOX", str(tmp_path))
    monkeypatch.setattr(appcli, "_config_toml_path", lambda: tmp_path / "none.toml")
    monkeypatch.setattr(appcli._install, "main", lambda argv: 0)
    monkeypatch.setattr(appcli._install, "plist_paths",
                        lambda c: {"watch": tmp_path / "w", "sweep": tmp_path / "s"})
    rc = appcli.main(["install"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert "watcher_running" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/evane/Desktop/Projects/ScribeTeX/.worktrees/menubar-app && python -m pytest tests/test_appcli_actions.py -v`
Expected: FAIL.

- [ ] **Step 3: Write minimal implementation**

In `automation/appcli.py`, add:
```python
import shutil as _shutil  # (top of file already imports shutil; reuse it)


def _process_path(cfg, src_path, *, process_fn=None) -> dict:
    process_fn = process_fn or _ingest.process_inbox
    src = Path(src_path).expanduser()
    if not src.exists():
        return {"ok": False, "error": f"file not found: {src}"}
    inbox = Path(cfg["inbox_dir"])
    inbox.mkdir(parents=True, exist_ok=True)
    dest = inbox / src.name
    if src.resolve() != dest.resolve():
        shutil.copy2(src, dest)
    return {"ok": True, "processed": process_fn(cfg)}
```
Register subcommands and dispatch:
- `process` (`--path` required) → `_emit(_process_path(cfg, args.path))`
- `sweep` → `_emit({"ok": True, "processed": _ingest.process_inbox(cfg)})`
- `install` → `rc = _install.main([]); paths = _install.plist_paths(cfg); _emit({"ok": rc == 0, "watcher_running": paths["watch"].exists() and paths["sweep"].exists()})`
- `uninstall` → `_install.main(["--uninstall"]); _emit({"ok": True, "watcher_running": False})`

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/evane/Desktop/Projects/ScribeTeX/.worktrees/menubar-app && python -m pytest tests/test_appcli_actions.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add automation/appcli.py tests/test_appcli_actions.py
git commit -m "feat: appcli process/sweep/install/uninstall subcommands"
```

---

### Task 5: JSON-contract guard test

**Files:**
- Create: `tests/test_appcli_contract.py`

**Interfaces:** none (guard test). Locks the exact `status` key set so the Swift Codable structs can't silently drift.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_appcli_contract.py
import datetime
from automation import appcli, config

STATUS_KEYS = {
    "ok", "watcher_running", "inbox_dir", "filed_today", "filed_total",
    "needs_review_count", "claude_ok", "settle_seconds", "sweep_seconds",
}
NEEDS_REVIEW_ITEM_KEYS = {"name", "path", "reason", "kind"}


def test_status_contract(tmp_path):
    cfg = config.load_config(env={"SCRIBETEX_INBOX": str(tmp_path)}, toml_path=None)
    st = appcli._status_dict(
        cfg, plist_paths_fn=lambda c: {"watch": tmp_path / "w", "sweep": tmp_path / "s"},
        which_fn=lambda b: None, now_fn=lambda: datetime.datetime(2026, 8, 6),
    )
    assert set(st.keys()) == STATUS_KEYS


def test_needs_review_item_contract(tmp_path):
    cfg = config.load_config(env={"SCRIBETEX_INBOX": str(tmp_path)}, toml_path=None)
    nr = tmp_path / "NeedsReview"; nr.mkdir(parents=True)
    (nr / "x.pdf").write_bytes(b"x")
    (nr / "x.pdf.review.txt").write_text("r")
    items = appcli._needs_review_items(cfg)
    assert items and set(items[0].keys()) == NEEDS_REVIEW_ITEM_KEYS
```

- [ ] **Step 2: Run test to verify it fails, then passes**

Run: `cd /Users/evane/Desktop/Projects/ScribeTeX/.worktrees/menubar-app && python -m pytest tests/test_appcli_contract.py -v`
Expected: PASS if Tasks 1–2 landed (this guards their shape). If it FAILS, a prior task's dict shape drifted — fix that task, do not weaken this test.

- [ ] **Step 3: Commit**

```bash
git add tests/test_appcli_contract.py
git commit -m "test: freeze appcli status + needs-review JSON contract"
```

---

### Task 6: Swift menu-bar app source (authored, user builds)

**Files:**
- Create: `macapp/README.md`
- Create: `macapp/ScribeTeX/ScribeTeXApp.swift`
- Create: `macapp/ScribeTeX/Bridge.swift`
- Create: `macapp/ScribeTeX/Models.swift`
- Create: `macapp/ScribeTeX/MenuContent.swift`
- Create: `macapp/project.yml` (XcodeGen spec) OR `macapp/Package.swift`
- Test: `tests/test_macapp_sources_present.py`

**Interfaces:** No Python interface. This task AUTHORS Swift; verification is the user's Xcode build. The Python test only asserts the files exist and reference the frozen appcli commands (a cheap guard that the deliverable is present and wired to the real bridge command names).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_macapp_sources_present.py
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "macapp"


def test_swift_sources_exist():
    for f in ("ScribeTeX/ScribeTeXApp.swift", "ScribeTeX/Bridge.swift",
              "ScribeTeX/Models.swift", "ScribeTeX/MenuContent.swift", "README.md"):
        assert (APP / f).exists(), f"missing {f}"


def test_bridge_references_appcli_commands():
    bridge = (APP / "ScribeTeX" / "Bridge.swift").read_text()
    # The bridge must invoke the real appcli module + the frozen command names.
    assert "automation.appcli" in bridge
    for cmd in ("status", "needs-review", "set-inbox", "process", "install", "uninstall"):
        assert cmd in bridge, f"bridge missing command {cmd}"


def test_readme_covers_unsigned_gatekeeper():
    readme = (APP / "README.md").read_text().lower()
    assert "right-click" in readme or "right click" in readme
    assert "open" in readme
    assert "claude code" in readme  # prerequisite documented
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/evane/Desktop/Projects/ScribeTeX/.worktrees/menubar-app && python -m pytest tests/test_macapp_sources_present.py -v`
Expected: FAIL (files missing).

- [ ] **Step 3: Write the Swift sources + README**

Author these files. They must be complete, idiomatic SwiftUI. Key requirements:

`macapp/ScribeTeX/Models.swift` — Codable structs matching the FROZEN contract:
```swift
import Foundation

struct Status: Codable {
    let ok: Bool
    let watcher_running: Bool
    let inbox_dir: String
    let filed_today: Int
    let filed_total: Int
    let needs_review_count: Int
    let claude_ok: Bool
    let settle_seconds: Int
    let sweep_seconds: Int
}

struct ReviewItem: Codable, Identifiable {
    var id: String { path }
    let name: String
    let path: String
    let reason: String?
    let kind: String
}

struct ReviewList: Codable { let ok: Bool; let items: [ReviewItem] }
struct ActionResult: Codable { let ok: Bool; let watcher_running: Bool? ; let error: String? }
```

`macapp/ScribeTeX/Bridge.swift` — runs the bridge via `Process`:
```swift
import Foundation

enum Bridge {
    // The repo root is chosen by the user on first run and stored in UserDefaults.
    static var repoRoot: String? {
        get { UserDefaults.standard.string(forKey: "ScribeTeXRepoRoot") }
        set { UserDefaults.standard.set(newValue, forKey: "ScribeTeXRepoRoot") }
    }
    static var pythonBin: String {
        UserDefaults.standard.string(forKey: "ScribeTeXPython") ?? "/usr/bin/python3"
    }

    static func run(_ args: [String]) throws -> Data {
        guard let root = repoRoot else { throw BridgeError.noRepo }
        let p = Process()
        p.executableURL = URL(fileURLWithPath: pythonBin)
        p.arguments = ["-m", "automation.appcli"] + args
        var env = ProcessInfo.processInfo.environment
        env["PYTHONPATH"] = "\(root):\(root)/src"
        p.environment = env
        p.currentDirectoryURL = URL(fileURLWithPath: root)
        let pipe = Pipe(); p.standardOutput = pipe
        try p.run(); p.waitUntilExit()
        return pipe.fileHandleForReading.readDataToEndOfFile()
    }

    // Convenience wrappers naming each appcli command:
    static func status() throws -> Status { try JSONDecoder().decode(Status.self, from: run(["status"])) }
    static func needsReview() throws -> ReviewList { try JSONDecoder().decode(ReviewList.self, from: run(["needs-review"])) }
    static func setInbox(_ path: String) throws -> Data { try run(["set-inbox", "--path", path]) }
    static func process(_ path: String) throws -> Data { try run(["process", "--path", path]) }
    static func install() throws -> Data { try run(["install"]) }
    static func uninstall() throws -> Data { try run(["uninstall"]) }
}

enum BridgeError: Error { case noRepo }
```

`macapp/ScribeTeX/ScribeTeXApp.swift` — `@main` `MenuBarExtra` app rendering
`MenuContent`, polling `Bridge.status()` on appear + a timer.

`macapp/ScribeTeX/MenuContent.swift` — the menu: status header (filed today/total,
watcher on/off), a Start/Stop toggle (install/uninstall), "Pick Inbox…"
(NSOpenPanel → setInbox), a NeedsReview submenu (needsReview items with reason),
"Process a File…" (NSOpenPanel → process), and — when `status.claude_ok` is false
or `Bridge.repoRoot` is nil — a setup row prompting to locate the repo / install
Claude Code. Include drag-drop via `.onDrop` on the app's window if present.

`macapp/README.md` — MUST include:
- Prerequisite: **Claude Code CLI + ScribeTeX plugin installed**.
- Build: open in Xcode (via XcodeGen `xcodegen generate` if `project.yml` is used, or open the Swift package), select the ScribeTeX scheme, Build/Run.
- First run: "Locate ScribeTeX…" to point at the repo root; pick your inbox.
- **Free/unsigned distribution**: zip the built `.app`; on another Mac, **right-click → Open** the first time to bypass Gatekeeper ("unidentified developer"). No Apple Developer account required.
- Note signing/notarization as an optional future step (not needed).

`macapp/project.yml` — a minimal XcodeGen spec (a macOS app target, deployment
target, `MenuBarExtra` needs macOS 13+) so `xcodegen generate` produces the
`.xcodeproj`. Document the `brew install xcodegen` step in the README. (Hand-
authoring a raw `.xcodeproj` is error-prone; XcodeGen from a small YAML is the
robust choice.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/evane/Desktop/Projects/ScribeTeX/.worktrees/menubar-app && python -m pytest tests/test_macapp_sources_present.py -v`
Expected: PASS. (Swift is NOT compiled here — that's the user's Xcode step, per the README.)

- [ ] **Step 5: Commit**

```bash
git add macapp tests/test_macapp_sources_present.py
git commit -m "feat: SwiftUI menu-bar app source + XcodeGen spec + build docs (user builds)"
```

---

### Task 7: iPad Shortcut recipe + README section

**Files:**
- Create: `docs/shortcut-setup.md`
- Modify: `README.md`
- Test: `tests/test_shortcut_doc.py`

**Interfaces:** none. Documentation deliverable.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_shortcut_doc.py
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_shortcut_doc_exists_and_covers_steps():
    doc = (ROOT / "docs" / "shortcut-setup.md").read_text().lower()
    assert "share sheet" in doc
    assert "save file" in doc
    assert "inbox" in doc
    assert "goodnotes" in doc


def test_readme_links_shortcut_and_app():
    readme = (ROOT / "README.md").read_text().lower()
    assert "shortcut" in readme
    assert "menu-bar" in readme or "menu bar" in readme
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/evane/Desktop/Projects/ScribeTeX/.worktrees/menubar-app && python -m pytest tests/test_shortcut_doc.py -v`
Expected: FAIL.

- [ ] **Step 3: Write the docs**

Create `docs/shortcut-setup.md` — a precise, numbered recipe:
1. Open the **Shortcuts** app (iPad). New Shortcut.
2. Shortcut settings → enable **"Show in Share Sheet"**; accept types: Images, PDFs, Files.
3. Add action **"Save File"**. Set the destination folder to the SAME cloud
   folder configured as your Mac inbox (iCloud Drive / Google Drive / Box /
   Dropbox / your `ScribeTeX-Inbox`). Turn OFF "Ask Where to Save".
4. Name it **"ScribeTeX"**. Done.
5. Usage: in **GoodNotes**, export/share the note as PDF → tap **Share** →
   **ScribeTeX**. The Mac watcher picks it up within seconds and files it.
Note: the destination MUST be the cloud-synced folder your Mac app watches; if
you change the inbox in the menu-bar app, update the Shortcut's Save File
destination to match.

In `README.md`, add an "Easy setup (menu-bar app + iPad Shortcut)" section that
links to `macapp/README.md` and `docs/shortcut-setup.md`, briefly stating: the
menu-bar app is a friendly front-end (build in Xcode, free/unsigned), and the
Shortcut sends notes from the iPad with one tap. Keep concise, match README tone.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/evane/Desktop/Projects/ScribeTeX/.worktrees/menubar-app && python -m pytest tests/test_shortcut_doc.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add docs/shortcut-setup.md README.md tests/test_shortcut_doc.py
git commit -m "docs: iPad Shortcut recipe + README easy-setup section"
```

---

### Task 8: Full-suite + plugin validation gate

**Files:** none (verification only).

- [ ] **Step 1: Full suite**

Run: `cd /Users/evane/Desktop/Projects/ScribeTeX/.worktrees/menubar-app && python -m pytest -q`
Expected: all green (existing 164 + new appcli/macapp/shortcut tests). Fix any regression (the appcli lazy-cfg-load change in Task 3 must not break Task 1/2 subcommands).

- [ ] **Step 2: Plugin validation**

Run: `cd /Users/evane/Desktop/Projects/ScribeTeX/.worktrees/menubar-app && claude plugin validate . 2>&1 | tail -20`
Expected: clean (no new skill added; manifests unchanged). If `claude` unavailable, JSON-lint the two manifests instead.

- [ ] **Step 3: appcli smoke over a temp config**

Run:
```bash
cd /Users/evane/Desktop/Projects/ScribeTeX/.worktrees/menubar-app
SCRIBETEX_INBOX=/tmp/scribetex_smoke python -c "
import json, sys
from automation import appcli
# status should emit valid JSON even with a nonexistent inbox
sys.argv = ['appcli','status']
appcli.main(['status'])
"
```
Expected: prints one valid JSON object with `ok` and `watcher_running`.

- [ ] **Step 4: Commit any fixups**

```bash
git add -A && git commit -m "test: menu-bar app suite green" || echo "nothing to fix up"
```

---

## Self-Review

- **Spec coverage:** appcli status→T1, needs-review→T2, set-inbox→T3, process/sweep/install/uninstall→T4, JSON-contract freeze→T5, Swift app source+build docs→T6, iPad Shortcut recipe+README→T7, gate→T8. Every spec component mapped. (Bridge Swift structs in T6 mirror the T1/T2/T5 frozen contract.)
- **Placeholder scan:** every Python step has real code; the Swift task gives complete source for the non-trivial files (Models/Bridge) and precise requirements for the UI files + README + XcodeGen spec (Swift is authored-not-compiled by design, per the spec's accepted constraint).
- **Type consistency:** `_status_dict` keys (T1) == STATUS_KEYS (T5) == Swift `Status` Codable (T6). `_needs_review_items` keys (T2) == NEEDS_REVIEW_ITEM_KEYS (T5) == Swift `ReviewItem` (T6). appcli command names (status/needs-review/set-inbox/process/sweep/install/uninstall) are asserted present in Bridge.swift (T6 test) and match the argparse subcommands (T1–T4). `_config_toml_path` is monkeypatched consistently across tests. Note the T3 lazy-cfg-load requirement is called out so set-inbox works before a config exists.
