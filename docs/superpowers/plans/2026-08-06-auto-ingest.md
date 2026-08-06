# ScribeTeX Auto-Ingest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A note PDF/image dropped into a watched inbox triggers a headless Claude run that transcribes it and files the LaTeX into the right course, with two macOS launchd triggers (instant folder-watch + 10-minute safety-net sweep) and desktop notifications.

**Architecture:** A new root-level `automation/` Python package. Pure/injectable modules (readiness, state, prompt) + an orchestrator (`ingest.py`) that invokes `claude -p` headless and routes the file by the agent's machine-readable result line. A macOS installer writes two launchd plists. A `watch-inbox` skill documents setup. No change to the existing MCP server, skills, or `src/scribetex/`.

**Tech Stack:** Python 3.11+ (stdlib: `tomllib`, `os`, `json`, `subprocess`, `pathlib`, `fcntl`/`os.O_EXCL`), PyMuPDF (`fitz`) + Pillow (already deps) for validity checks, macOS `launchd` + `osascript`, the `claude` CLI (`-p/--print`).

## Global Constraints

- Work in the worktree `/Users/evane/Desktop/Projects/ScribeTeX/.worktrees/auto-ingest` on branch `auto-ingest`. Run tests from the worktree root.
- The new package is `automation/` at the REPO ROOT (not under `src/`). To make it importable in tests, `pyproject.toml`'s `[tool.pytest.ini_options] pythonpath` becomes `["src", "."]` (Task 1). Verified: adding `.` to pythonpath makes a root-level package importable.
- All automation modules are **pure/injectable where possible**: readiness/state/prompt take injected clock/size/subprocess fns so tests never sleep, never call `claude`, never touch launchd or the network.
- The headless engine is `claude -p` (a.k.a. `--print`) — reuse the shipped ScribeTeX plugin/MCP + skills; do NOT reimplement transcription or duplicate the process-note workflow.
- **Machine-readable contract:** the agent prints a line `SCRIBETEX_RESULT: <json>` and the worker parses the LAST such line. Statuses: `filed`, `ambiguous`, `error`. On `ambiguous` the agent must NOT write — it explains and stops.
- **File lifecycle:** originals are never deleted. `filed` → move to `<inbox>/Done/YYYY-MM-DD/`; `ambiguous` → move to `<inbox>/NeedsReview/` + a `<name>.review.txt` sidecar; `error`/unparseable → leave in place (sweep retries).
- **Inbox is configurable** (env var + optional `~/.config/scribetex/automation.toml`); defaults exist; no provider is hardcoded (Box/Drive/iCloud/local all work).
- **Ready check:** process a file only when size is stable across two reads `settle_seconds` apart AND it is a valid note (PDF opens via `fitz` with ≥1 page, or image opens via PIL). Supported exts mirror `scribetex.sources.file_source`: pdf, png, jpg, jpeg, heic.
- **Idempotency + locking:** a JSON seen-set keyed by `name:size:mtime_ns`; an atomic `O_CREAT|O_EXCL` lockfile (with stale-PID reclaim) so watch and sweep never double-process.
- Notifications via `osascript`; failures swallowed (never block ingest).
- Do NOT modify `src/scribetex/` or existing skills. Do NOT load launchd or run `claude` in tests.
- Reuse: `scribetex.config.notes_root`.

---

### Task 1: Package skeleton + pytest pythonpath

**Files:**
- Create: `automation/__init__.py`
- Modify: `pyproject.toml` (pytest `pythonpath`)
- Test: `tests/test_automation_import.py`

**Interfaces:**
- Produces: importable `automation` package; `automation.__version__ = "0.1.0"`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_automation_import.py
def test_automation_package_imports():
    import automation
    assert hasattr(automation, "__version__")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/evane/Desktop/Projects/ScribeTeX/.worktrees/auto-ingest && python -m pytest tests/test_automation_import.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'automation'`).

- [ ] **Step 3: Write minimal implementation**

Create `automation/__init__.py`:
```python
"""ScribeTeX auto-ingest: watch an inbox and file notes via headless Claude."""
__version__ = "0.1.0"
```

In `pyproject.toml`, change the pytest section's pythonpath line from `pythonpath = ["src"]` to:
```toml
pythonpath = ["src", "."]
```
(Leave `testpaths = ["tests"]` unchanged.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/evane/Desktop/Projects/ScribeTeX/.worktrees/auto-ingest && python -m pytest tests/test_automation_import.py -v`
Expected: PASS. Also confirm the existing suite still collects: `python -m pytest -q` (expect prior 103 + this 1).

- [ ] **Step 5: Commit**

```bash
git add automation/__init__.py pyproject.toml tests/test_automation_import.py
git commit -m "feat: automation package skeleton + pytest pythonpath"
```

---

### Task 2: `automation/config.py` — configuration

**Files:**
- Create: `automation/config.py`
- Test: `tests/test_automation_config.py`

**Interfaces:**
- Consumes: `scribetex.config.notes_root`, env vars, optional TOML.
- Produces:
  - `load_config(env=None, toml_path=None) -> dict` — merge defaults ← TOML ← env (env wins). Keys: `inbox_dir` (Path), `sweep_seconds` (int, default 600), `settle_seconds` (int, default 4), `claude_bin` (str, default "claude"), `log_file` (Path). Never raises if the TOML file is absent; if present but malformed, raise `ValueError` naming the file.
  - Derived path helpers taking the config dict: `done_dir(cfg)`, `needs_review_dir(cfg)`, `state_file(cfg)`, `lock_file(cfg)` — all under `inbox_dir` except state/lock which live under `inbox_dir/.scribetex/`.
  - Env vars: `SCRIBETEX_INBOX` (inbox dir), `SCRIBETEX_SWEEP_SECONDS`, `SCRIBETEX_SETTLE_SECONDS`, `SCRIBETEX_CLAUDE_BIN`, `SCRIBETEX_AUTOMATION_LOG`.
  - Default `inbox_dir` = `~/ScribeTeX-Inbox` (expanded). `expanduser()` applied to all paths.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_automation_config.py
from pathlib import Path
import pytest
from automation import config


def test_defaults_when_no_env_no_toml():
    cfg = config.load_config(env={}, toml_path=None)
    assert cfg["inbox_dir"] == (Path.home() / "ScribeTeX-Inbox")
    assert cfg["sweep_seconds"] == 600
    assert cfg["settle_seconds"] == 4
    assert cfg["claude_bin"] == "claude"


def test_env_overrides(tmp_path):
    env = {
        "SCRIBETEX_INBOX": str(tmp_path / "in"),
        "SCRIBETEX_SWEEP_SECONDS": "120",
        "SCRIBETEX_SETTLE_SECONDS": "2",
        "SCRIBETEX_CLAUDE_BIN": "/usr/local/bin/claude",
    }
    cfg = config.load_config(env=env, toml_path=None)
    assert cfg["inbox_dir"] == (tmp_path / "in")
    assert cfg["sweep_seconds"] == 120
    assert cfg["settle_seconds"] == 2
    assert cfg["claude_bin"] == "/usr/local/bin/claude"


def test_toml_used_and_env_wins(tmp_path):
    toml = tmp_path / "automation.toml"
    toml.write_text('inbox_dir = "%s"\nsweep_seconds = 300\n' % (tmp_path / "t"))
    cfg = config.load_config(env={"SCRIBETEX_SWEEP_SECONDS": "45"}, toml_path=toml)
    assert cfg["inbox_dir"] == (tmp_path / "t")   # from toml
    assert cfg["sweep_seconds"] == 45             # env overrides toml


def test_missing_toml_is_ok(tmp_path):
    cfg = config.load_config(env={}, toml_path=tmp_path / "nope.toml")
    assert cfg["sweep_seconds"] == 600


def test_malformed_toml_raises(tmp_path):
    bad = tmp_path / "bad.toml"
    bad.write_text("this is = = not toml")
    with pytest.raises(ValueError, match="bad.toml"):
        config.load_config(env={}, toml_path=bad)


def test_derived_paths(tmp_path):
    cfg = config.load_config(env={"SCRIBETEX_INBOX": str(tmp_path)}, toml_path=None)
    assert config.done_dir(cfg) == tmp_path / "Done"
    assert config.needs_review_dir(cfg) == tmp_path / "NeedsReview"
    assert config.state_file(cfg) == tmp_path / ".scribetex" / "seen.json"
    assert config.lock_file(cfg) == tmp_path / ".scribetex" / "ingest.lock"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/evane/Desktop/Projects/ScribeTeX/.worktrees/auto-ingest && python -m pytest tests/test_automation_config.py -v`
Expected: FAIL (`automation.config` does not exist).

- [ ] **Step 3: Write minimal implementation**

Create `automation/config.py`:
```python
"""Auto-ingest configuration: defaults <- optional TOML <- env (env wins)."""
from __future__ import annotations
import os
import tomllib
from pathlib import Path

DEFAULTS = {
    "inbox_dir": Path.home() / "ScribeTeX-Inbox",
    "sweep_seconds": 600,
    "settle_seconds": 4,
    "claude_bin": "claude",
    "log_file": Path.home() / "ScribeTeX-Inbox" / ".scribetex" / "ingest.log",
}

_ENV = {
    "inbox_dir": "SCRIBETEX_INBOX",
    "sweep_seconds": "SCRIBETEX_SWEEP_SECONDS",
    "settle_seconds": "SCRIBETEX_SETTLE_SECONDS",
    "claude_bin": "SCRIBETEX_CLAUDE_BIN",
    "log_file": "SCRIBETEX_AUTOMATION_LOG",
}
_INT_KEYS = {"sweep_seconds", "settle_seconds"}
_PATH_KEYS = {"inbox_dir", "log_file"}


def load_config(env=None, toml_path=None) -> dict:
    env = os.environ if env is None else env
    cfg = dict(DEFAULTS)

    if toml_path is not None and Path(toml_path).exists():
        try:
            with open(toml_path, "rb") as fh:
                data = tomllib.load(fh)
        except tomllib.TOMLDecodeError as e:
            raise ValueError(f"malformed automation config {toml_path}: {e}")
        cfg.update({k: v for k, v in data.items() if k in DEFAULTS})

    for key, var in _ENV.items():
        if var in env and env[var] != "":
            cfg[key] = env[var]

    for k in _INT_KEYS:
        cfg[k] = int(cfg[k])
    for k in _PATH_KEYS:
        cfg[k] = Path(cfg[k]).expanduser()
    return cfg


def _sub(cfg) -> Path:
    return Path(cfg["inbox_dir"]) / ".scribetex"


def done_dir(cfg) -> Path:
    return Path(cfg["inbox_dir"]) / "Done"


def needs_review_dir(cfg) -> Path:
    return Path(cfg["inbox_dir"]) / "NeedsReview"


def state_file(cfg) -> Path:
    return _sub(cfg) / "seen.json"


def lock_file(cfg) -> Path:
    return _sub(cfg) / "ingest.lock"
```

Note: when `inbox_dir` comes from TOML/env the default `log_file` still points at the default inbox; that's acceptable (log_file is independently overridable). Tests don't assert log_file coupling.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/evane/Desktop/Projects/ScribeTeX/.worktrees/auto-ingest && python -m pytest tests/test_automation_config.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add automation/config.py tests/test_automation_config.py
git commit -m "feat: auto-ingest configuration (defaults <- toml <- env)"
```

---

### Task 3: `automation/readiness.py` — ready + validity checks

**Files:**
- Create: `automation/readiness.py`
- Test: `tests/test_automation_readiness.py`

**Interfaces:**
- Produces:
  - `SUPPORTED_EXTS = {".pdf", ".png", ".jpg", ".jpeg", ".heic"}`.
  - `is_stable(path, settle_seconds, size_fn=None, sleep_fn=None) -> bool` — reads size, waits `settle_seconds` (via injectable `sleep_fn`), reads again; True iff equal and > 0. `size_fn(path)->int` and `sleep_fn(secs)->None` injectable for tests.
  - `is_valid_note(path) -> bool` — ext in SUPPORTED_EXTS; for `.pdf` open with `fitz` and require `page_count >= 1`; for images open with `PIL.Image` and `.verify()`. Any exception → False. Zero-byte → False.
  - `is_ready(path, settle_seconds, **inj) -> bool` — `is_valid_note(path) and is_stable(...)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_automation_readiness.py
import fitz
from PIL import Image
from automation import readiness


def _pdf(path, pages=1):
    doc = fitz.open()
    for _ in range(pages):
        doc.new_page()
    doc.save(str(path))
    doc.close()
    return path


def test_stable_when_size_unchanged():
    sizes = iter([100, 100])
    ok = readiness.is_stable(
        "x", 1, size_fn=lambda p: next(sizes), sleep_fn=lambda s: None
    )
    assert ok is True


def test_not_stable_when_growing():
    sizes = iter([100, 250])
    ok = readiness.is_stable(
        "x", 1, size_fn=lambda p: next(sizes), sleep_fn=lambda s: None
    )
    assert ok is False


def test_not_stable_when_zero():
    ok = readiness.is_stable(
        "x", 1, size_fn=lambda p: 0, sleep_fn=lambda s: None
    )
    assert ok is False


def test_valid_pdf(tmp_path):
    p = _pdf(tmp_path / "n.pdf")
    assert readiness.is_valid_note(p) is True


def test_valid_png(tmp_path):
    p = tmp_path / "n.png"
    Image.new("RGB", (10, 10), "white").save(p)
    assert readiness.is_valid_note(p) is True


def test_invalid_zero_byte_pdf(tmp_path):
    p = tmp_path / "empty.pdf"
    p.write_bytes(b"")
    assert readiness.is_valid_note(p) is False


def test_invalid_truncated_pdf(tmp_path):
    p = tmp_path / "trunc.pdf"
    p.write_bytes(b"%PDF-1.4 broken not really a pdf")
    assert readiness.is_valid_note(p) is False


def test_unsupported_ext(tmp_path):
    p = tmp_path / "note.txt"
    p.write_text("hi")
    assert readiness.is_valid_note(p) is False


def test_is_ready_combines(tmp_path):
    p = _pdf(tmp_path / "n.pdf")
    ok = readiness.is_ready(
        p, 1, size_fn=lambda x: p.stat().st_size, sleep_fn=lambda s: None
    )
    assert ok is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/evane/Desktop/Projects/ScribeTeX/.worktrees/auto-ingest && python -m pytest tests/test_automation_readiness.py -v`
Expected: FAIL (`automation.readiness` missing).

- [ ] **Step 3: Write minimal implementation**

Create `automation/readiness.py`:
```python
"""Decide whether an inbox file is fully arrived and a valid note."""
from __future__ import annotations
import time
from pathlib import Path

SUPPORTED_EXTS = {".pdf", ".png", ".jpg", ".jpeg", ".heic"}


def is_stable(path, settle_seconds, size_fn=None, sleep_fn=None) -> bool:
    size_fn = size_fn or (lambda p: Path(p).stat().st_size)
    sleep_fn = sleep_fn or time.sleep
    first = size_fn(path)
    if first <= 0:
        return False
    sleep_fn(settle_seconds)
    return size_fn(path) == first


def is_valid_note(path) -> bool:
    p = Path(path)
    ext = p.suffix.lower()
    if ext not in SUPPORTED_EXTS:
        return False
    try:
        if p.stat().st_size == 0:
            return False
    except OSError:
        return False
    try:
        if ext == ".pdf":
            import fitz
            doc = fitz.open(str(p))
            try:
                return doc.page_count >= 1
            finally:
                doc.close()
        from PIL import Image
        with Image.open(p) as img:
            img.verify()
        return True
    except Exception:
        return False


def is_ready(path, settle_seconds, size_fn=None, sleep_fn=None) -> bool:
    return is_valid_note(path) and is_stable(
        path, settle_seconds, size_fn=size_fn, sleep_fn=sleep_fn
    )
```

Note: `.heic` may fail `PIL.verify()` without a HEIF plugin; that's acceptable — an unopenable file is treated not-ready and retried/needs-review, never crashes. Do not add a hard HEIC dependency.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/evane/Desktop/Projects/ScribeTeX/.worktrees/auto-ingest && python -m pytest tests/test_automation_readiness.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add automation/readiness.py tests/test_automation_readiness.py
git commit -m "feat: auto-ingest readiness + note validity checks"
```

---

### Task 4: `automation/state.py` — seen-set + lockfile

**Files:**
- Create: `automation/state.py`
- Test: `tests/test_automation_state.py`

**Interfaces:**
- Produces:
  - `identity(path) -> str` — `f"{name}:{size}:{mtime_ns}"` from `path.stat()`.
  - `load_seen(state_file) -> set[str]` — JSON list → set; missing file → empty set; malformed → empty set (never raise).
  - `mark_seen(state_file, key) -> None` — add key, write JSON (creates parent dir).
  - `acquire_lock(lock_file, pid=None, pid_alive=None) -> bool` — atomic `O_CREAT|O_EXCL` write of the PID; if the lock exists, read its PID and, if not alive (via injectable `pid_alive(pid)->bool`), reclaim it (True); else False. `pid` defaults to `os.getpid()`.
  - `release_lock(lock_file) -> None` — unlink if present (ignore missing).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_automation_state.py
from pathlib import Path
from automation import state


def test_identity_changes_with_size(tmp_path):
    p = tmp_path / "a.pdf"
    p.write_bytes(b"12345")
    id1 = state.identity(p)
    p.write_bytes(b"1234567890")
    id2 = state.identity(p)
    assert id1 != id2
    assert p.name in id1


def test_seen_roundtrip(tmp_path):
    sf = tmp_path / ".scribetex" / "seen.json"
    assert state.load_seen(sf) == set()
    state.mark_seen(sf, "k1")
    state.mark_seen(sf, "k2")
    assert state.load_seen(sf) == {"k1", "k2"}


def test_seen_malformed_is_empty(tmp_path):
    sf = tmp_path / "seen.json"
    sf.write_text("{not json")
    assert state.load_seen(sf) == set()


def test_lock_acquire_then_blocked(tmp_path):
    lf = tmp_path / "ingest.lock"
    assert state.acquire_lock(lf, pid=111, pid_alive=lambda pid: True) is True
    # a second acquirer sees a live holder -> blocked
    assert state.acquire_lock(lf, pid=222, pid_alive=lambda pid: True) is False


def test_lock_reclaims_stale(tmp_path):
    lf = tmp_path / "ingest.lock"
    assert state.acquire_lock(lf, pid=111, pid_alive=lambda pid: True) is True
    # holder 111 is dead -> 222 reclaims
    assert state.acquire_lock(lf, pid=222, pid_alive=lambda pid: False) is True


def test_release_lock(tmp_path):
    lf = tmp_path / "ingest.lock"
    state.acquire_lock(lf, pid=111, pid_alive=lambda pid: True)
    state.release_lock(lf)
    assert not lf.exists()
    state.release_lock(lf)  # idempotent, no raise
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/evane/Desktop/Projects/ScribeTeX/.worktrees/auto-ingest && python -m pytest tests/test_automation_state.py -v`
Expected: FAIL (`automation.state` missing).

- [ ] **Step 3: Write minimal implementation**

Create `automation/state.py`:
```python
"""Idempotency seen-set + an atomic single-holder lockfile."""
from __future__ import annotations
import json
import os
from pathlib import Path


def identity(path) -> str:
    st = Path(path).stat()
    return f"{Path(path).name}:{st.st_size}:{st.st_mtime_ns}"


def load_seen(state_file) -> set:
    p = Path(state_file)
    if not p.exists():
        return set()
    try:
        return set(json.loads(p.read_text()))
    except Exception:
        return set()


def mark_seen(state_file, key) -> None:
    p = Path(state_file)
    p.parent.mkdir(parents=True, exist_ok=True)
    seen = load_seen(p)
    seen.add(key)
    p.write_text(json.dumps(sorted(seen)))


def _default_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists but not ours


def acquire_lock(lock_file, pid=None, pid_alive=None) -> bool:
    p = Path(lock_file)
    p.parent.mkdir(parents=True, exist_ok=True)
    pid = os.getpid() if pid is None else pid
    pid_alive = pid_alive or _default_alive
    try:
        fd = os.open(str(p), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(pid).encode())
        os.close(fd)
        return True
    except FileExistsError:
        try:
            holder = int(p.read_text().strip() or "-1")
        except Exception:
            holder = -1
        if holder == pid or not pid_alive(holder):
            # stale (or ours): reclaim
            p.write_text(str(pid))
            return True
        return False


def release_lock(lock_file) -> None:
    try:
        Path(lock_file).unlink()
    except FileNotFoundError:
        pass
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/evane/Desktop/Projects/ScribeTeX/.worktrees/auto-ingest && python -m pytest tests/test_automation_state.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add automation/state.py tests/test_automation_state.py
git commit -m "feat: auto-ingest seen-set + atomic lockfile with stale reclaim"
```

---

### Task 5: `automation/prompt.py` — headless prompt + result parsing

**Files:**
- Create: `automation/prompt.py`
- Test: `tests/test_automation_prompt.py`

**Interfaces:**
- Produces:
  - `RESULT_PREFIX = "SCRIBETEX_RESULT:"`.
  - `build_prompt(note_path) -> str` — the instruction for `claude -p`. Must contain: the absolute note path; instruction to use the ScribeTeX tools (prepare_note → transcribe every page → resolve_placement → write_section, embedding drawings via save_figure per the figure priority); the "if ambiguous, do NOT guess/write — emit ambiguous result and stop" rule; and the exact output contract describing the three `SCRIBETEX_RESULT:` JSON shapes.
  - `parse_result(stdout) -> dict` — return the JSON from the LAST line starting with `RESULT_PREFIX`; if none or malformed, return `{"status": "error", "reason": "<why>"}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_automation_prompt.py
from automation import prompt


def test_build_prompt_mentions_path_and_contract():
    p = prompt.build_prompt("/notes/inbox/Bio 5.pdf")
    assert "/notes/inbox/Bio 5.pdf" in p
    assert "prepare_note" in p and "resolve_placement" in p and "write_section" in p
    assert "save_figure" in p
    assert prompt.RESULT_PREFIX in p
    # must instruct not to guess when ambiguous
    low = p.lower()
    assert "ambiguous" in low and ("do not" in low or "don't" in low)


def test_parse_filed():
    out = 'blah\nSCRIBETEX_RESULT: {"status":"filed","course":"Bio","target":"/x/main.tex"}\ndone'
    r = prompt.parse_result(out)
    assert r["status"] == "filed"
    assert r["course"] == "Bio"


def test_parse_ambiguous():
    out = 'SCRIBETEX_RESULT: {"status":"ambiguous","reason":"course unclear"}'
    assert prompt.parse_result(out)["status"] == "ambiguous"


def test_parse_last_line_wins():
    out = ('SCRIBETEX_RESULT: {"status":"error","reason":"x"}\n'
           'SCRIBETEX_RESULT: {"status":"filed","course":"C"}')
    assert prompt.parse_result(out)["status"] == "filed"


def test_parse_missing_line_is_error():
    assert prompt.parse_result("no marker here")["status"] == "error"


def test_parse_malformed_json_is_error():
    out = "SCRIBETEX_RESULT: {not json}"
    r = prompt.parse_result(out)
    assert r["status"] == "error"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/evane/Desktop/Projects/ScribeTeX/.worktrees/auto-ingest && python -m pytest tests/test_automation_prompt.py -v`
Expected: FAIL (`automation.prompt` missing).

- [ ] **Step 3: Write minimal implementation**

Create `automation/prompt.py`:
```python
"""The headless-Claude instruction + parsing of its machine-readable result."""
from __future__ import annotations
import json

RESULT_PREFIX = "SCRIBETEX_RESULT:"


def build_prompt(note_path) -> str:
    return f"""You are ScribeTeX's unattended ingest worker. Process EXACTLY ONE \
handwritten note file into typeset LaTeX using the ScribeTeX MCP tools. Do not \
ask the user anything; there is no human available.

Note file: {note_path}

Steps:
1. Call prepare_note(source="file", ref="{note_path}").
2. Read EVERY returned page image and transcribe it to LaTeX per the returned \
brief (body only). Reproduce charts/tables/graphs as TikZ/pgfplots/tabular; embed \
freehand drawings by calling save_figure with a fractional bbox; prose only as a \
last resort.
3. Decide the course, the top-level section, a concise subsection title, and the \
date from the note's content.
4. Call resolve_placement(course_hint, section_hint, subsection_hint, date).
5. Call write_section(...) to file the transcription.

If you CANNOT confidently determine the course, section, or date (ambiguous or \
missing), DO NOT guess and DO NOT write anything. Instead stop and report an \
ambiguous result.

When done, print EXACTLY ONE final line, machine-readable, one of:
{RESULT_PREFIX} {{"status":"filed","course":"...","section":"...","subsection":"...","date":"YYYY-MM-DD","target":"<path to main.tex>","figures":<int>}}
{RESULT_PREFIX} {{"status":"ambiguous","reason":"<what was unclear>"}}
{RESULT_PREFIX} {{"status":"error","reason":"<what failed>"}}
The {RESULT_PREFIX} line MUST be valid JSON after the prefix. Print nothing after it."""


def parse_result(stdout: str) -> dict:
    last = None
    for line in stdout.splitlines():
        s = line.strip()
        if s.startswith(RESULT_PREFIX):
            last = s[len(RESULT_PREFIX):].strip()
    if last is None:
        return {"status": "error", "reason": "no SCRIBETEX_RESULT line in output"}
    try:
        data = json.loads(last)
    except Exception as e:
        return {"status": "error", "reason": f"malformed result json: {e}"}
    if "status" not in data:
        return {"status": "error", "reason": "result missing status"}
    return data
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/evane/Desktop/Projects/ScribeTeX/.worktrees/auto-ingest && python -m pytest tests/test_automation_prompt.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add automation/prompt.py tests/test_automation_prompt.py
git commit -m "feat: auto-ingest headless prompt + SCRIBETEX_RESULT parsing"
```

---

### Task 6: `automation/ingest.py` — the orchestrator

**Files:**
- Create: `automation/ingest.py`
- Test: `tests/test_automation_ingest.py`

**Interfaces:**
- Consumes: `automation.config`, `readiness`, `state`, `prompt`.
- Produces:
  - `invoke_claude(note_path, claude_bin, run_fn=None, timeout=1800) -> str` — runs `[claude_bin, "-p", build_prompt(path)]` via injectable `run_fn` (default `subprocess.run`), returns stdout; on nonzero exit/timeout/exception returns a stdout string containing an `error` SCRIBETEX_RESULT line.
  - `notify(title, message, run_fn=None) -> None` — `osascript -e 'display notification ...'`; swallow all errors.
  - `route_file(note_path, result, cfg, now_fn=None) -> str` — perform the move + sidecar per status; return one of `"filed"`, `"ambiguous"`, `"error"` (the effective outcome). `filed`→Done/<date-from-now>; `ambiguous`→NeedsReview/ + `<name>.review.txt`; `error`→leave in place. `now_fn` injectable for the Done date.
  - `process_inbox(cfg, invoke_fn=None, notify_fn=None, ready_fn=None, now_fn=None) -> list[dict]` — the top-level loop with locking, returning a per-file summary list (for tests/logging). `invoke_fn`, `notify_fn`, `ready_fn` injectable.
  - `main(argv=None) -> int` — arg parse `--once` / `--sweep` (behaviourally identical; both call `process_inbox`), load config, run, return 0.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_automation_ingest.py
import json
from pathlib import Path
import fitz
from automation import ingest, config, prompt


def _pdf(path):
    doc = fitz.open(); doc.new_page(); doc.save(str(path)); doc.close()
    return path


def _cfg(tmp_path):
    return config.load_config(
        env={"SCRIBETEX_INBOX": str(tmp_path), "SCRIBETEX_SETTLE_SECONDS": "0"},
        toml_path=None,
    )


def _result_line(d):
    return f'{prompt.RESULT_PREFIX} {json.dumps(d)}'


def test_filed_moves_to_done(tmp_path):
    cfg = _cfg(tmp_path)
    note = _pdf(tmp_path / "note.pdf")
    invoke = lambda p, b: _result_line(
        {"status": "filed", "course": "Bio", "section": "R", "subsection": "S",
         "date": "2026-08-06", "target": "/x/main.tex", "figures": 0})
    out = ingest.process_inbox(
        cfg, invoke_fn=invoke, notify_fn=lambda *a: None,
        ready_fn=lambda p, s: True, now_fn=lambda: __import__("datetime").datetime(2026, 8, 6),
    )
    assert any(r["outcome"] == "filed" for r in out)
    assert not note.exists()
    moved = list((tmp_path / "Done" / "2026-08-06").glob("note.pdf"))
    assert len(moved) == 1


def test_ambiguous_moves_to_needsreview_with_sidecar(tmp_path):
    cfg = _cfg(tmp_path)
    note = _pdf(tmp_path / "amb.pdf")
    invoke = lambda p, b: _result_line({"status": "ambiguous", "reason": "course unclear"})
    ingest.process_inbox(cfg, invoke_fn=invoke, notify_fn=lambda *a: None,
                         ready_fn=lambda p, s: True)
    assert not note.exists()
    nr = tmp_path / "NeedsReview"
    assert (nr / "amb.pdf").exists()
    sidecar = nr / "amb.pdf.review.txt"
    assert sidecar.exists() and "course unclear" in sidecar.read_text()


def test_error_leaves_in_place(tmp_path):
    cfg = _cfg(tmp_path)
    note = _pdf(tmp_path / "err.pdf")
    invoke = lambda p, b: _result_line({"status": "error", "reason": "boom"})
    ingest.process_inbox(cfg, invoke_fn=invoke, notify_fn=lambda *a: None,
                         ready_fn=lambda p, s: True)
    assert note.exists()  # stays for retry


def test_seen_prevents_reprocessing(tmp_path):
    cfg = _cfg(tmp_path)
    _pdf(tmp_path / "once.pdf")
    calls = []
    invoke = lambda p, b: calls.append(p) or _result_line(
        {"status": "filed", "course": "C", "date": "2026-08-06", "target": "/x"})
    ingest.process_inbox(cfg, invoke_fn=invoke, notify_fn=lambda *a: None,
                         ready_fn=lambda p, s: True,
                         now_fn=lambda: __import__("datetime").datetime(2026, 8, 6))
    # second pass: file already moved to Done AND marked seen -> no new invoke
    ingest.process_inbox(cfg, invoke_fn=invoke, notify_fn=lambda *a: None,
                         ready_fn=lambda p, s: True,
                         now_fn=lambda: __import__("datetime").datetime(2026, 8, 6))
    assert len(calls) == 1


def test_not_ready_skipped(tmp_path):
    cfg = _cfg(tmp_path)
    _pdf(tmp_path / "slow.pdf")
    calls = []
    invoke = lambda p, b: calls.append(p) or _result_line({"status": "filed"})
    ingest.process_inbox(cfg, invoke_fn=invoke, notify_fn=lambda *a: None,
                         ready_fn=lambda p, s: False)
    assert calls == []
    assert (tmp_path / "slow.pdf").exists()


def test_subdirs_ignored(tmp_path):
    cfg = _cfg(tmp_path)
    (tmp_path / "Done").mkdir()
    _pdf(tmp_path / "Done" / "already.pdf")
    calls = []
    invoke = lambda p, b: calls.append(p) or _result_line({"status": "filed"})
    ingest.process_inbox(cfg, invoke_fn=invoke, notify_fn=lambda *a: None,
                         ready_fn=lambda p, s: True)
    assert calls == []  # files under Done/ are not candidates
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/evane/Desktop/Projects/ScribeTeX/.worktrees/auto-ingest && python -m pytest tests/test_automation_ingest.py -v`
Expected: FAIL (`automation.ingest` missing).

- [ ] **Step 3: Write minimal implementation**

Create `automation/ingest.py`:
```python
"""Orchestrate: find ready inbox notes, run headless Claude, route + notify."""
from __future__ import annotations
import argparse
import datetime as _dt
import shutil
import subprocess
import sys
from pathlib import Path

from . import config as _config
from . import readiness, state
from .prompt import build_prompt, parse_result

_IGNORE_DIRS = {"Done", "NeedsReview", ".scribetex"}


def invoke_claude(note_path, claude_bin, run_fn=None, timeout=1800) -> str:
    run_fn = run_fn or subprocess.run
    try:
        proc = run_fn(
            [claude_bin, "-p", build_prompt(note_path)],
            capture_output=True, text=True, timeout=timeout,
        )
        out = proc.stdout or ""
        if proc.returncode != 0 and "SCRIBETEX_RESULT:" not in out:
            return (out + f"\nSCRIBETEX_RESULT: "
                    f'{{"status":"error","reason":"claude exit {proc.returncode}"}}')
        return out
    except Exception as e:  # timeout / not found / etc.
        return f'SCRIBETEX_RESULT: {{"status":"error","reason":"invoke failed: {e}"}}'


def notify(title, message, run_fn=None) -> None:
    run_fn = run_fn or subprocess.run
    try:
        script = f'display notification {message!r} with title {title!r}'
        run_fn(["osascript", "-e", script], capture_output=True, text=True, timeout=10)
    except Exception:
        pass


def route_file(note_path, result, cfg, now_fn=None) -> str:
    now_fn = now_fn or _dt.datetime.now
    note = Path(note_path)
    status = result.get("status", "error")
    if status == "filed":
        day = now_fn().strftime("%Y-%m-%d")
        dest_dir = _config.done_dir(cfg) / day
        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(str(note), str(dest_dir / note.name))
        return "filed"
    if status == "ambiguous":
        nr = _config.needs_review_dir(cfg)
        nr.mkdir(parents=True, exist_ok=True)
        shutil.move(str(note), str(nr / note.name))
        (nr / f"{note.name}.review.txt").write_text(
            f"Needs review: {result.get('reason', 'unspecified')}\n"
        )
        return "ambiguous"
    return "error"  # leave in place


def _candidates(cfg):
    inbox = Path(cfg["inbox_dir"])
    if not inbox.exists():
        return []
    out = []
    for entry in sorted(inbox.iterdir()):
        if entry.is_dir() or entry.name.startswith("."):
            continue
        if entry.suffix.lower() not in readiness.SUPPORTED_EXTS:
            continue
        out.append(entry)
    return out


def process_inbox(cfg, invoke_fn=None, notify_fn=None, ready_fn=None,
                  now_fn=None) -> list:
    invoke_fn = invoke_fn or (lambda p, b: invoke_claude(p, b))
    notify_fn = notify_fn or notify
    ready_fn = ready_fn or (lambda p, s: readiness.is_ready(p, s))

    lock = _config.lock_file(cfg)
    if not state.acquire_lock(lock):
        return []
    results = []
    try:
        sf = _config.state_file(cfg)
        seen = state.load_seen(sf)
        settle = cfg["settle_seconds"]
        for note in _candidates(cfg):
            key = state.identity(note)
            if key in seen:
                continue
            if not ready_fn(note, settle):
                continue
            stdout = invoke_fn(str(note), cfg["claude_bin"])
            result = parse_result(stdout)
            outcome = route_file(note, result, cfg, now_fn=now_fn)
            if outcome in ("filed", "ambiguous"):
                state.mark_seen(sf, key)
            _notify_outcome(notify_fn, note, result, outcome)
            results.append({"file": note.name, "outcome": outcome,
                            "result": result})
    finally:
        state.release_lock(lock)
    return results


def _notify_outcome(notify_fn, note, result, outcome):
    if outcome == "filed":
        msg = (f"Filed {note.name} under "
               f"{result.get('section', '?')} / {result.get('subsection', '?')}"
               f" ({result.get('figures', 0)} figures)")
        notify_fn("ScribeTeX filed a note", msg)
    elif outcome == "ambiguous":
        notify_fn("ScribeTeX needs review",
                  f"{note.name}: {result.get('reason', 'ambiguous')}")
    else:
        notify_fn("ScribeTeX error",
                  f"{note.name}: {result.get('reason', 'error')}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="ScribeTeX inbox ingest.")
    ap.add_argument("--once", action="store_true", help="process inbox once (watch trigger)")
    ap.add_argument("--sweep", action="store_true", help="sweep the inbox (timer trigger)")
    ap.parse_args(argv)  # flags are behaviourally identical; both process once
    cfg = _config.load_config(
        toml_path=Path.home() / ".config" / "scribetex" / "automation.toml"
    )
    process_inbox(cfg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/evane/Desktop/Projects/ScribeTeX/.worktrees/auto-ingest && python -m pytest tests/test_automation_ingest.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add automation/ingest.py tests/test_automation_ingest.py
git commit -m "feat: auto-ingest orchestrator (invoke, route, notify, lock)"
```

---

### Task 7: `automation/install.py` — launchd plist installer

**Files:**
- Create: `automation/install.py`
- Test: `tests/test_automation_install.py`

**Interfaces:**
- Produces:
  - `render_plist(label, program_args, *, watch_paths=None, start_interval=None, log_file) -> str` — a valid launchd plist XML string. Includes `<key>Label</key>`, `ProgramArguments`, `StandardOutPath`/`StandardErrorPath` = log_file, and EITHER `WatchPaths` (list) OR `StartInterval` (int). Raise `ValueError` if neither/both given.
  - `plist_paths(cfg) -> dict` — `{"watch": Path(~/Library/LaunchAgents/com.scribetex.watch.plist), "sweep": ...}`.
  - `build_plists(cfg, python_bin, repo_root) -> dict[Path, str]` — returns the two target paths → rendered XML. Watch agent: `ProgramArguments=[python_bin, "-m", "automation.ingest", "--once"]`, `WatchPaths=[str(inbox_dir)]`, `WorkingDirectory`/`PYTHONPATH` = repo_root so `automation` + `scribetex` import. Sweep agent: same but `--sweep` and `StartInterval=sweep_seconds`.
  - `preflight(cfg, claude_bin, repo_root) -> list[str]` — returns a list of human-readable problems (empty = OK): claude not found (`shutil.which`), inbox_dir missing, repo_root/automation missing, repo_root/src/scribetex missing.
  - `main(argv)` — `install` (default) writes plists (creating Done/NeedsReview/.scribetex), prints preflight problems and ABORTS if any; `--uninstall` removes them. Does NOT call launchctl in tests (guard behind a `--load/--no-load`, default load on real install). Keep launchctl calls out of the unit-tested functions.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_automation_install.py
import plistlib
from pathlib import Path
import pytest
from automation import install, config


def _cfg(tmp_path):
    return config.load_config(env={"SCRIBETEX_INBOX": str(tmp_path)}, toml_path=None)


def test_render_watch_plist_valid():
    xml = install.render_plist(
        "com.scribetex.watch",
        ["/usr/bin/python3", "-m", "automation.ingest", "--once"],
        watch_paths=["/inbox"], log_file="/tmp/x.log",
    )
    data = plistlib.loads(xml.encode())
    assert data["Label"] == "com.scribetex.watch"
    assert data["WatchPaths"] == ["/inbox"]
    assert data["ProgramArguments"][-1] == "--once"
    assert "StartInterval" not in data


def test_render_sweep_plist_valid():
    xml = install.render_plist(
        "com.scribetex.sweep",
        ["/usr/bin/python3", "-m", "automation.ingest", "--sweep"],
        start_interval=600, log_file="/tmp/x.log",
    )
    data = plistlib.loads(xml.encode())
    assert data["StartInterval"] == 600
    assert "WatchPaths" not in data


def test_render_requires_exactly_one_trigger():
    with pytest.raises(ValueError):
        install.render_plist("l", ["x"], log_file="/t")  # neither
    with pytest.raises(ValueError):
        install.render_plist("l", ["x"], watch_paths=["/a"],
                             start_interval=1, log_file="/t")  # both


def test_build_plists_targets_and_content(tmp_path):
    cfg = _cfg(tmp_path)
    plists = install.build_plists(cfg, "/usr/bin/python3", "/repo")
    labels = {p.name for p in plists}
    assert "com.scribetex.watch.plist" in labels
    assert "com.scribetex.sweep.plist" in labels
    watch_xml = next(v for k, v in plists.items() if "watch" in k.name)
    assert str(tmp_path) in watch_xml  # inbox in WatchPaths
    assert "/repo" in watch_xml        # PYTHONPATH/WorkingDirectory


def test_preflight_flags_missing_claude(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    tmp_path.mkdir(exist_ok=True)
    monkeypatch.setattr(install.shutil, "which", lambda x: None)
    problems = install.preflight(cfg, "claude", str(tmp_path))
    assert any("claude" in p.lower() for p in problems)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/evane/Desktop/Projects/ScribeTeX/.worktrees/auto-ingest && python -m pytest tests/test_automation_install.py -v`
Expected: FAIL (`automation.install` missing).

- [ ] **Step 3: Write minimal implementation**

Create `automation/install.py`:
```python
"""Render + install the two launchd agents (watch + sweep)."""
from __future__ import annotations
import argparse
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

from . import config as _config

LAUNCH_AGENTS = Path.home() / "Library" / "LaunchAgents"
WATCH_LABEL = "com.scribetex.watch"
SWEEP_LABEL = "com.scribetex.sweep"


def render_plist(label, program_args, *, watch_paths=None,
                 start_interval=None, log_file) -> str:
    if (watch_paths is None) == (start_interval is None):
        raise ValueError("exactly one of watch_paths / start_interval required")
    d = {
        "Label": label,
        "ProgramArguments": list(program_args),
        "RunAtLoad": start_interval is not None,
        "StandardOutPath": str(log_file),
        "StandardErrorPath": str(log_file),
    }
    if watch_paths is not None:
        d["WatchPaths"] = list(watch_paths)
    else:
        d["StartInterval"] = int(start_interval)
    return plistlib.dumps(d).decode()


def plist_paths(cfg) -> dict:
    return {
        "watch": LAUNCH_AGENTS / f"{WATCH_LABEL}.plist",
        "sweep": LAUNCH_AGENTS / f"{SWEEP_LABEL}.plist",
    }


def build_plists(cfg, python_bin, repo_root) -> dict:
    inbox = str(cfg["inbox_dir"])
    log = str(cfg["log_file"])
    # Inject repo_root on PYTHONPATH via an env-setting wrapper is awkward in
    # launchd; instead run with `-c` bootstrapping sys.path, or rely on the
    # module being importable from WorkingDirectory. We set EnvironmentVariables.
    def args(flag):
        return [python_bin, "-m", "automation.ingest", flag]

    watch = render_plist(WATCH_LABEL, args("--once"),
                         watch_paths=[inbox], log_file=log)
    sweep = render_plist(SWEEP_LABEL, args("--sweep"),
                         start_interval=int(cfg["sweep_seconds"]), log_file=log)
    # Add WorkingDirectory + PYTHONPATH so automation + scribetex import.
    watch = _inject_env(watch, repo_root)
    sweep = _inject_env(sweep, repo_root)
    paths = plist_paths(cfg)
    return {paths["watch"]: watch, paths["sweep"]: sweep}


def _inject_env(xml, repo_root):
    data = plistlib.loads(xml.encode())
    data["WorkingDirectory"] = str(repo_root)
    data["EnvironmentVariables"] = {
        "PYTHONPATH": f"{repo_root}:{repo_root}/src",
    }
    return plistlib.dumps(data).decode()


def preflight(cfg, claude_bin, repo_root) -> list:
    problems = []
    if shutil.which(claude_bin) is None and not Path(claude_bin).exists():
        problems.append(f"claude CLI not found: {claude_bin}")
    if not Path(cfg["inbox_dir"]).exists():
        problems.append(f"inbox dir does not exist: {cfg['inbox_dir']}")
    if not (Path(repo_root) / "automation").is_dir():
        problems.append(f"automation package not found under {repo_root}")
    if not (Path(repo_root) / "src" / "scribetex").is_dir():
        problems.append(f"scribetex package not found under {repo_root}/src")
    return problems


def _ensure_dirs(cfg):
    for d in (_config.done_dir(cfg), _config.needs_review_dir(cfg),
              Path(cfg["inbox_dir"]) / ".scribetex"):
        d.mkdir(parents=True, exist_ok=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Install ScribeTeX launchd agents.")
    ap.add_argument("--uninstall", action="store_true")
    ap.add_argument("--no-load", action="store_true",
                    help="write/remove plists but don't call launchctl")
    ap.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    args = ap.parse_args(argv)

    cfg = _config.load_config(
        toml_path=Path.home() / ".config" / "scribetex" / "automation.toml"
    )
    paths = plist_paths(cfg)

    if args.uninstall:
        for label, p in ((WATCH_LABEL, paths["watch"]), (SWEEP_LABEL, paths["sweep"])):
            if not args.no_load and p.exists():
                subprocess.run(["launchctl", "unload", str(p)],
                               capture_output=True)
            p.unlink(missing_ok=True)
            print(f"removed {p}")
        return 0

    problems = preflight(cfg, cfg["claude_bin"], args.repo_root)
    if problems:
        print("Cannot install — fix these first:")
        for pr in problems:
            print(f"  - {pr}")
        return 1

    _ensure_dirs(cfg)
    LAUNCH_AGENTS.mkdir(parents=True, exist_ok=True)
    for target, xml in build_plists(cfg, sys.executable, args.repo_root).items():
        target.write_text(xml)
        print(f"wrote {target}")
        if not args.no_load:
            subprocess.run(["launchctl", "unload", str(target)],
                           capture_output=True)
            subprocess.run(["launchctl", "load", str(target)],
                           capture_output=True)
    print("Installed. Drop a PDF into", cfg["inbox_dir"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/evane/Desktop/Projects/ScribeTeX/.worktrees/auto-ingest && python -m pytest tests/test_automation_install.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add automation/install.py tests/test_automation_install.py
git commit -m "feat: auto-ingest launchd plist renderer + installer"
```

---

### Task 8: `watch-inbox` skill + README section

**Files:**
- Create: `skills/watch-inbox/SKILL.md`
- Create: `skills/watch-inbox/scripts/run.py`
- Create: `skills/watch-inbox/scripts/__init__.py`
- Modify: `README.md`
- Test: `tests/test_watch_inbox_skill.py`

**Interfaces:**
- `skills/watch-inbox/scripts/run.py` — self-locating CLI wrapping install/uninstall/status/sweep. Subcommands: `install`, `uninstall`, `status` (print config + whether plists exist), `sweep` (run one ingest pass now). Self-locates BOTH `automation` (repo root) and `scribetex` (src) onto sys.path.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_watch_inbox_skill.py
import os, subprocess, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RUN = REPO / "skills" / "watch-inbox" / "scripts" / "run.py"


def test_skill_md_exists_and_has_frontmatter():
    md = (REPO / "skills" / "watch-inbox" / "SKILL.md").read_text()
    assert md.startswith("---")
    assert "name: watch-inbox" in md
    assert "category:" in md


def test_run_status_imports_without_pythonpath():
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    r = subprocess.run([sys.executable, str(RUN), "status"],
                       capture_output=True, text=True, env=env,
                       cwd=str(Path.home()))
    assert "ModuleNotFoundError" not in r.stderr, r.stderr
    assert r.returncode == 0, r.stderr
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/evane/Desktop/Projects/ScribeTeX/.worktrees/auto-ingest && python -m pytest tests/test_watch_inbox_skill.py -v`
Expected: FAIL (files missing).

- [ ] **Step 3: Write minimal implementation**

Create `skills/watch-inbox/scripts/__init__.py` (empty).

Create `skills/watch-inbox/scripts/run.py`:
```python
#!/usr/bin/env python3
"""Manage ScribeTeX auto-ingest: install/uninstall launchd agents, status, sweep.

Self-locating: adds the repo root (for `automation`) and repo/src (for
`scribetex`) to sys.path, so no external PYTHONPATH is needed.
"""
from __future__ import annotations
import argparse
import pathlib
import sys

_ROOT = pathlib.Path(__file__).resolve().parents[3]
for _p in (_ROOT, _ROOT / "src"):
    if _p.is_dir() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from automation import config as _config       # noqa: E402
from automation import install as _install     # noqa: E402
from automation import ingest as _ingest       # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="ScribeTeX auto-ingest manager.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("install")
    sub.add_parser("uninstall")
    sub.add_parser("status")
    sub.add_parser("sweep")
    args = ap.parse_args()

    if args.cmd == "install":
        return _install.main([])
    if args.cmd == "uninstall":
        return _install.main(["--uninstall"])
    if args.cmd == "sweep":
        cfg = _config.load_config(
            toml_path=pathlib.Path.home() / ".config" / "scribetex" / "automation.toml")
        res = _ingest.process_inbox(cfg)
        print(f"processed {len(res)} file(s): "
              + ", ".join(f"{r['file']}={r['outcome']}" for r in res))
        return 0
    # status
    cfg = _config.load_config(
        toml_path=pathlib.Path.home() / ".config" / "scribetex" / "automation.toml")
    paths = _install.plist_paths(cfg)
    print(f"inbox_dir       : {cfg['inbox_dir']}")
    print(f"sweep_seconds   : {cfg['sweep_seconds']}")
    print(f"settle_seconds  : {cfg['settle_seconds']}")
    print(f"claude_bin      : {cfg['claude_bin']}")
    print(f"watch agent     : {'installed' if paths['watch'].exists() else 'not installed'}")
    print(f"sweep agent     : {'installed' if paths['sweep'].exists() else 'not installed'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Create `skills/watch-inbox/SKILL.md`:
```markdown
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
```

In `README.md`, add a short "Automatic ingest (watch a folder)" section pointing at the `watch-inbox` skill: the inbox config, `install`/`status`/`uninstall`, the Filed/NeedsReview/Error outcomes, and the cost/handwriting caveat. Keep it concise and consistent with the README's tone.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/evane/Desktop/Projects/ScribeTeX/.worktrees/auto-ingest && python -m pytest tests/test_watch_inbox_skill.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add skills/watch-inbox README.md tests/test_watch_inbox_skill.py
git commit -m "feat: watch-inbox skill + README auto-ingest section"
```

---

### Task 9: Full-suite + plugin validation gate

**Files:** none (verification only).

- [ ] **Step 1: Full suite**

Run: `cd /Users/evane/Desktop/Projects/ScribeTeX/.worktrees/auto-ingest && python -m pytest -q`
Expected: all green (prior 103 + new automation/skill tests). If a prior test broke due to the `pythonpath` change, investigate — adding `"."` should be additive; do not remove `"src"`.

- [ ] **Step 2: Plugin validation**

Run: `cd /Users/evane/Desktop/Projects/ScribeTeX/.worktrees/auto-ingest && claude plugin validate . 2>&1 | tail -20`
Expected: clean (the new `watch-inbox` skill validates). If `claude` unavailable, JSON-lint manifests instead.

- [ ] **Step 3: Manual smoke of the worker (stubbed claude)**

Run:
```bash
cd /Users/evane/Desktop/Projects/ScribeTeX/.worktrees/auto-ingest
python - <<'PY'
import tempfile, datetime, fitz
from pathlib import Path
from automation import config, ingest, prompt
d = Path(tempfile.mkdtemp())
doc = fitz.open(); doc.new_page(); doc.save(str(d / "smoke.pdf")); doc.close()
cfg = config.load_config(env={"SCRIBETEX_INBOX": str(d), "SCRIBETEX_SETTLE_SECONDS": "0"}, toml_path=None)
line = prompt.RESULT_PREFIX + ' {"status":"filed","course":"Bio","section":"R","subsection":"S","date":"2026-08-06","target":"/x","figures":1}'
res = ingest.process_inbox(cfg, invoke_fn=lambda p,b: line, notify_fn=lambda *a: None, ready_fn=lambda p,s: True, now_fn=lambda: datetime.datetime(2026,8,6))
print("RESULT:", res)
print("moved:", list((d/"Done"/"2026-08-06").glob("*.pdf")))
PY
```
Expected: prints one `filed` result and the moved PDF path.

- [ ] **Step 4: Commit any fixups**

```bash
git add -A && git commit -m "test: auto-ingest full-suite green" || echo "nothing to fix up"
```

---

## Self-Review

- **Spec coverage:** config→T2, readiness→T3, state→T4, prompt+parse→T5, ingest/route/notify/lock→T6, launchd installer+preflight→T7, skill+README→T8, gate→T9, package/pythonpath→T1. Every spec component mapped.
- **Placeholder scan:** every code step contains real code; no TBDs.
- **Type consistency:** `load_config` dict keys (`inbox_dir`, `sweep_seconds`, `settle_seconds`, `claude_bin`, `log_file`) are consumed identically in T6/T7/T8. `process_inbox`'s injectable params (`invoke_fn(p,b)`, `notify_fn`, `ready_fn(p,s)`, `now_fn`) match their call sites and the tests. `render_plist`'s exactly-one-trigger rule is asserted in T7. `RESULT_PREFIX`/`parse_result` defined in T5, used in T6. `plist_paths`/`build_plists`/`preflight` names consistent T7↔T8. Self-locating `run.py` uses `parents[3]` (skills/watch-inbox/scripts/run.py → repo root), matching existing skills.
- **Note:** T1 changes pytest `pythonpath` to `["src","."]`; verified a root package imports under that. All later tasks depend on it (first task, correctly ordered).
