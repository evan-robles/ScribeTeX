# ScribeTeX Review Window + Inline Re-file Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a parked (NeedsReview) note resolvable in-app: a native notification opens a dedicated Review window where the user sets course/section/date and re-files, and the fix roots out the Script-Editor notification bug.

**Architecture:** Parking writes a structured `<name>.review.json` sidecar (reason + Claude's best-guess course/section/date). New `appcli` commands (`needs-review` enriched, `known-courses`, `refile`, `discard`) wrap the existing engine and are fully tested in Python. The Swift app posts native `UNUserNotificationCenter` notifications (fixing Script Editor) and shows a Review window over those commands — authored here, built by the user in Xcode. Re-file re-transcribes with the confirmed date so figures land correctly.

**Tech Stack:** Python 3.11+ (stdlib json/argparse/shutil/pathlib), the existing `automation` + `scribetex` packages, SwiftUI (`Window`, `UNUserNotificationCenter`; authored only).

## Global Constraints

- Work in the worktree `/Users/evane/Desktop/Projects/ScribeTeX/.worktrees/review-window` on branch `review-window`. Run tests from the worktree root.
- Every appcli subcommand prints ONE JSON object to stdout and exits 0; recoverable errors are `{"ok": false, "error": ...}` (still exit 0). The top-level dispatch is already wrapped in try/except → JSON.
- The parking sidecar is `<name>.review.json` with keys: `reason` (str), `kind` ("ambiguous"|"error"), `guess` (object with `course`/`section`/`subsection`/`date`, each str-or-null). The human `.review.txt`/`.error.txt` are REPLACED by the `.json` (the needs-review reader falls back to legacy `.txt`/`.error.txt` = reason-only, guess nulls, for pre-existing parked notes).
- `needs-review` item shape (frozen contract, extended): `{name, path, reason, kind, course, section, subsection, date}` — course/section/subsection/date from the sidecar `guess`, null when unknown.
- Re-file RE-TRANSCRIBES: it runs a refile-specific prompt that hard-codes the user's course/section/subsection/date so Claude only transcribes+files and never re-parks.
- Reuse ONLY (do not reimplement): `scribetex.discovery.known_courses(root: Path) -> list[str]`, `scribetex.classify.parse_date(raw) -> str|None`, `scribetex.config.notes_root`/dir helpers, `automation.ingest.invoke_claude`, `automation.config`.
- Notifications: the APP owns them (native). The launchd watcher stays quiet. `ingest`/`appcli` must NOT be the user-facing osascript notifier anymore (the existing `ingest.notify` may remain in the tree but is no longer wired into the app-facing flow).
- Swift files are AUTHORED, not compiled here; verified by the user in Xcode. Keep the JSON contract frozen so the Codable structs are stable.
- Do NOT modify `src/scribetex/` behavior. Only ADD to `automation/` + `macapp/` + tests + docs.

---

### Task 1: Structured parking sidecar (`.review.json`)

**Files:**
- Modify: `automation/prompt.py`
- Modify: `automation/ingest.py`
- Test: `tests/test_review_sidecar.py`

**Interfaces:**
- Consumes: an ambiguous/error result dict.
- Produces:
  - `prompt.build_prompt` ambiguous contract now instructs Claude to include best-guess fields: the ambiguous line becomes `{"status":"ambiguous","reason":"...","course":<str|null>,"section":<str|null>,"subsection":<str|null>,"date":<str|null>}` (still "do NOT write anything" — just report guesses).
  - `ingest._write_review_sidecar(note_name_dir, note_name, reason, kind, result) -> Path` — writes `<name>.review.json` = `{"reason","kind","guess":{"course","section","subsection","date"}}` (guess values from result, defaulting to None). Returns the json path.
  - `route_file` (ambiguous) and `give_up_file` (error) call it (kind "ambiguous"/"error") and no longer write the `.txt`/`.error.txt`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_review_sidecar.py
import json
from pathlib import Path
from automation import ingest, config


def _cfg(tmp_path):
    return config.load_config(env={"SCRIBETEX_INBOX": str(tmp_path)}, toml_path=None)


def _pdf(p):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"%PDF-1.4")
    return p


def test_route_ambiguous_writes_json_sidecar(tmp_path):
    cfg = _cfg(tmp_path)
    note = _pdf(tmp_path / "note.pdf")
    result = {"status": "ambiguous", "reason": "no date",
              "course": "BIOS 20200", "section": "Receptors",
              "subsection": "Receptors", "date": None}
    outcome = ingest.route_file(str(note), result, cfg)
    assert outcome == "ambiguous"
    nr = tmp_path / "NeedsReview"
    assert (nr / "note.pdf").exists()
    sidecar = nr / "note.pdf.review.json"
    assert sidecar.exists()
    data = json.loads(sidecar.read_text())
    assert data["reason"] == "no date"
    assert data["kind"] == "ambiguous"
    assert data["guess"]["course"] == "BIOS 20200"
    assert data["guess"]["date"] is None
    # legacy .txt no longer written
    assert not (nr / "note.pdf.review.txt").exists()


def test_give_up_writes_error_json_sidecar(tmp_path):
    cfg = _cfg(tmp_path)
    note = _pdf(tmp_path / "bad.pdf")
    result = {"status": "error", "reason": "boom"}
    ingest.give_up_file(str(note), result, cfg)
    nr = tmp_path / "NeedsReview"
    sidecar = nr / "bad.pdf.review.json"
    assert sidecar.exists()
    data = json.loads(sidecar.read_text())
    assert data["kind"] == "error"
    assert data["reason"] == "boom"
    assert data["guess"]["course"] is None


def test_build_prompt_ambiguous_contract_documents_guesses():
    from automation.prompt import build_prompt
    p = build_prompt("/x/note.pdf")
    # ambiguous result now carries best-guess fields for prefill
    assert '"status":"ambiguous"' in p
    assert "course" in p and "section" in p and "subsection" in p and "date" in p
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/evane/Desktop/Projects/ScribeTeX/.worktrees/review-window && python -m pytest tests/test_review_sidecar.py -v`
Expected: FAIL (`_write_review_sidecar` missing; route_file still writes `.txt`; prompt ambiguous line lacks guess fields).

- [ ] **Step 3: Write minimal implementation**

In `automation/prompt.py`, change the ambiguous template line so build_prompt's output contains the guess fields. Replace the ambiguous `SCRIBETEX_RESULT` example line with:
```
{RESULT_PREFIX} {{"status":"ambiguous","reason":"<what was unclear>","course":<string-or-null>,"section":<string-or-null>,"subsection":<string-or-null>,"date":<string-or-null>}}
```
and add one instruction sentence before the result contract: "If you must report ambiguous, still include your BEST GUESS for course/section/subsection/date (use null for any you truly cannot infer) so the user can confirm quickly."

In `automation/ingest.py`, add the helper and rewire both branches:
```python
import json as _json  # if not already imported at top; else use existing json import

def _write_review_sidecar(nr_dir, note_name, reason, kind, result) -> "Path":
    from pathlib import Path
    sidecar = Path(nr_dir) / f"{note_name}.review.json"
    payload = {
        "reason": reason,
        "kind": kind,
        "guess": {
            "course": result.get("course"),
            "section": result.get("section"),
            "subsection": result.get("subsection"),
            "date": result.get("date"),
        },
    }
    sidecar.write_text(_json.dumps(payload, indent=2))
    return sidecar
```
(Reuse the module's existing `json` import if present — check the top of ingest.py; if `json` isn't imported, add `import json`.)

In `route_file` ambiguous branch, replace the `.review.txt` write with:
```python
        nr.mkdir(parents=True, exist_ok=True)
        shutil.move(str(note), str(nr / note.name))
        _write_review_sidecar(nr, note.name,
                              result.get("reason", "unspecified"), "ambiguous", result)
        return "ambiguous"
```
In `give_up_file`, replace the `.error.txt` write with:
```python
    nr.mkdir(parents=True, exist_ok=True)
    shutil.move(str(note), str(nr / note.name))
    _write_review_sidecar(nr, note.name,
                          result.get("reason", "unspecified"), "error", result)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/evane/Desktop/Projects/ScribeTeX/.worktrees/review-window && python -m pytest tests/test_review_sidecar.py -v`
Expected: PASS. Then `python -m pytest -q` — NOTE some existing ingest/appcli tests assert the old `.review.txt`/`.error.txt`; those are updated in Task 2 (needs-review reader) and Task 6 (gate). If an EXISTING test in test_automation_ingest.py asserts `.review.txt`, update it here to assert `.review.json` (it's the same behavior change) so this task leaves the suite green for the files it touches.

- [ ] **Step 5: Commit**

```bash
git add automation/prompt.py automation/ingest.py tests/test_review_sidecar.py
git commit -m "feat: structured .review.json parking sidecar with best-guess fields"
```

---

### Task 2: `needs-review` reads sidecar guesses (+ legacy fallback)

**Files:**
- Modify: `automation/appcli.py`
- Modify: `tests/test_appcli_contract.py`
- Test: `tests/test_appcli_needs_review_guesses.py`

**Interfaces:**
- Produces: `_needs_review_items(cfg)` returns items with keys `{name, path, reason, kind, course, section, subsection, date}`. Reads `<name>.review.json` (`guess` → the four fields). Legacy fallback: if only `<name>.review.txt` or `<name>.error.txt` exists, reason = its text, kind accordingly, all four guesses null.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_appcli_needs_review_guesses.py
import json
from pathlib import Path
from automation import appcli, config


def _cfg(tmp_path):
    return config.load_config(env={"SCRIBETEX_INBOX": str(tmp_path)}, toml_path=None)


def test_reads_json_sidecar_guesses(tmp_path):
    cfg = _cfg(tmp_path)
    nr = tmp_path / "NeedsReview"; nr.mkdir(parents=True)
    (nr / "a.pdf").write_bytes(b"x")
    (nr / "a.pdf.review.json").write_text(json.dumps({
        "reason": "no date", "kind": "ambiguous",
        "guess": {"course": "BIOS 20200", "section": "Receptors",
                  "subsection": "Receptors", "date": None}}))
    items = {i["name"]: i for i in appcli._needs_review_items(cfg)}
    it = items["a.pdf"]
    assert it["kind"] == "ambiguous"
    assert it["reason"] == "no date"
    assert it["course"] == "BIOS 20200"
    assert it["section"] == "Receptors"
    assert it["date"] is None


def test_legacy_txt_sidecar_fallback(tmp_path):
    cfg = _cfg(tmp_path)
    nr = tmp_path / "NeedsReview"; nr.mkdir(parents=True)
    (nr / "old.pdf").write_bytes(b"x")
    (nr / "old.pdf.review.txt").write_text("Needs review: course unclear")
    it = {i["name"]: i for i in appcli._needs_review_items(cfg)}["old.pdf"]
    assert it["kind"] == "ambiguous"
    assert "course unclear" in it["reason"]
    assert it["course"] is None and it["date"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/evane/Desktop/Projects/ScribeTeX/.worktrees/review-window && python -m pytest tests/test_appcli_needs_review_guesses.py -v`
Expected: FAIL (items lack course/section/subsection/date; no json reading).

- [ ] **Step 3: Write minimal implementation**

Rewrite `_needs_review_items` in `automation/appcli.py`:
```python
def _needs_review_items(cfg) -> list:
    nr = _config.needs_review_dir(cfg)
    if not nr.exists():
        return []
    items = []
    for p in sorted(nr.iterdir()):
        if not p.is_file() or p.suffix in (".json", ".txt"):
            continue
        jpath = nr / f"{p.name}.review.json"
        review = nr / f"{p.name}.review.txt"
        error = nr / f"{p.name}.error.txt"
        reason, kind = None, "unknown"
        guess = {"course": None, "section": None, "subsection": None, "date": None}
        if jpath.exists():
            try:
                data = json.loads(jpath.read_text())
                reason = data.get("reason")
                kind = data.get("kind", "unknown")
                g = data.get("guess") or {}
                for k in guess:
                    guess[k] = g.get(k)
            except Exception:
                reason, kind = "unreadable review sidecar", "unknown"
        elif review.exists():
            reason, kind = review.read_text().strip(), "ambiguous"
        elif error.exists():
            reason, kind = error.read_text().strip(), "error"
        items.append({"name": p.name, "path": str(p), "reason": reason,
                      "kind": kind, **guess})
    return items
```
Note the exclusion now skips `.json` AND `.txt` sidecar files (so they aren't listed as notes).

In `tests/test_appcli_contract.py`, update:
```python
NEEDS_REVIEW_ITEM_KEYS = {"name", "path", "reason", "kind",
                          "course", "section", "subsection", "date"}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/evane/Desktop/Projects/ScribeTeX/.worktrees/review-window && python -m pytest tests/test_appcli_needs_review_guesses.py tests/test_appcli_contract.py tests/test_appcli_needs_review.py -v`
Expected: PASS. If `tests/test_appcli_needs_review.py` (older) asserts the old 4-key shape or `.review.txt` items, update those assertions to the new shape (same behavior, richer keys) — do not weaken them.

- [ ] **Step 5: Commit**

```bash
git add automation/appcli.py tests/test_appcli_contract.py tests/test_appcli_needs_review_guesses.py tests/test_appcli_needs_review.py
git commit -m "feat: needs-review returns sidecar guesses; legacy .txt fallback"
```

---

### Task 3: `appcli known-courses`

**Files:**
- Modify: `automation/appcli.py`
- Test: `tests/test_appcli_known_courses.py`

**Interfaces:**
- Consumes: `scribetex.discovery.known_courses`, `scribetex.config.notes_root` (via the loaded cfg's inbox? NO — courses live under the NOTES root, which is `scribetex.config.notes_root()`, distinct from the automation inbox). Use `scribetex.config.notes_root()`.
- Produces: `_known_courses() -> list[str]`; `known-courses` subcommand → `{"ok": true, "courses": [...]}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_appcli_known_courses.py
import json
from automation import appcli


def test_known_courses_lists_folders(tmp_path, monkeypatch):
    # Point the scribetex NOTES root at a temp dir with two course folders.
    monkeypatch.setenv("SCRIBETEX_NOTES_ROOT", str(tmp_path))
    (tmp_path / "Organic Chemistry").mkdir()
    (tmp_path / "BIOS 20200").mkdir()
    (tmp_path / "not-a-course.txt").write_text("x")
    courses = set(appcli._known_courses())
    assert "Organic Chemistry" in courses
    assert "BIOS 20200" in courses


def test_known_courses_subcommand_json(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SCRIBETEX_NOTES_ROOT", str(tmp_path))
    (tmp_path / "Physics 101").mkdir()
    rc = appcli.main(["known-courses"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True
    assert "Physics 101" in out["courses"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/evane/Desktop/Projects/ScribeTeX/.worktrees/review-window && python -m pytest tests/test_appcli_known_courses.py -v`
Expected: FAIL.

- [ ] **Step 3: Write minimal implementation**

In `automation/appcli.py`:
```python
def _known_courses() -> list:
    from scribetex.discovery import known_courses
    from scribetex.config import notes_root
    return known_courses(notes_root())
```
Register `sub.add_parser("known-courses")` and dispatch:
`if args.cmd == "known-courses": return _emit({"ok": True, "courses": _known_courses()})`.
(Note: `known-courses` needs NO automation config load; place its dispatch branch so it does not call `_load()`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/evane/Desktop/Projects/ScribeTeX/.worktrees/review-window && python -m pytest tests/test_appcli_known_courses.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add automation/appcli.py tests/test_appcli_known_courses.py
git commit -m "feat: appcli known-courses subcommand for the review course dropdown"
```

---

### Task 4: refile prompt + `appcli refile` / `discard`

**Files:**
- Modify: `automation/prompt.py`
- Modify: `automation/appcli.py`
- Test: `tests/test_appcli_refile.py`

**Interfaces:**
- Produces:
  - `prompt.build_refile_prompt(note_path, course, section, subsection, date) -> str` — hard-codes placement: "The course is C, the section is S, the subsection is Sub, the class date is D. Transcribe this note and FILE it with exactly these values. Do NOT report ambiguous." Same `SCRIBETEX_RESULT` filed/error contract (no ambiguous).
  - `_refile(cfg, path, course, section, subsection, date, *, invoke_fn=None, write_fn=None) -> dict` — validate path is under NeedsReview + exists; `parse_date(date)` (error if unusable); re-transcribe via `invoke_fn` (default a thin wrapper running `ingest.invoke_claude` with the refile prompt) → parse result; on filed, move PDF to `Done/<date>/`, remove the `.review.json`/legacy sidecars, return `{"ok": true, "filed": {...}}`; on error, leave in place, `{"ok": false, "error": ...}`.
  - `_discard(cfg, path) -> dict` — remove the parked PDF + its sidecars; `{"ok": true, "discarded": name}`.
  - subcommands `refile --path --course --section --subsection --date` and `discard --path`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_appcli_refile.py
import json
from pathlib import Path
from automation import appcli, config, prompt


def _cfg(tmp_path):
    return config.load_config(env={"SCRIBETEX_INBOX": str(tmp_path)}, toml_path=None)


def _parked(tmp_path, name="n.pdf"):
    nr = tmp_path / "NeedsReview"; nr.mkdir(parents=True, exist_ok=True)
    pdf = nr / name; pdf.write_bytes(b"%PDF-1.4")
    (nr / f"{name}.review.json").write_text(json.dumps(
        {"reason": "no date", "kind": "ambiguous",
         "guess": {"course": None, "section": None, "subsection": None, "date": None}}))
    return pdf


def test_refile_prompt_hardcodes_placement():
    p = prompt.build_refile_prompt("/x/n.pdf", "Bio", "Receptors", "Rods", "2026-08-06")
    assert "Bio" in p and "Receptors" in p and "Rods" in p and "2026-08-06" in p
    assert "do not" in p.lower() and "ambiguous" in p.lower()


def test_refile_files_and_moves(tmp_path):
    cfg = _cfg(tmp_path)
    pdf = _parked(tmp_path)
    filed_line = (prompt.RESULT_PREFIX +
                  ' {"status":"filed","course":"Bio","section":"Receptors",'
                  '"subsection":"Rods","date":"2026-08-06","target":"/x/main.tex","figures":0}')
    res = appcli._refile(cfg, str(pdf), "Bio", "Receptors", "Rods", "2026-08-06",
                         invoke_fn=lambda *a, **k: filed_line)
    assert res["ok"] is True
    assert not pdf.exists()                                   # moved out of NeedsReview
    assert list((tmp_path / "Done" / "2026-08-06").glob("n.pdf"))
    assert not (tmp_path / "NeedsReview" / "n.pdf.review.json").exists()  # sidecar gone


def test_refile_bad_date_errors_and_keeps(tmp_path):
    cfg = _cfg(tmp_path)
    pdf = _parked(tmp_path, "b.pdf")
    res = appcli._refile(cfg, str(pdf), "Bio", "S", "Sub", "notadate",
                         invoke_fn=lambda *a, **k: "")
    assert res["ok"] is False
    assert pdf.exists()   # untouched


def test_discard_removes_note_and_sidecar(tmp_path):
    cfg = _cfg(tmp_path)
    pdf = _parked(tmp_path, "d.pdf")
    res = appcli._discard(cfg, str(pdf))
    assert res["ok"] is True
    assert not pdf.exists()
    assert not (tmp_path / "NeedsReview" / "d.pdf.review.json").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/evane/Desktop/Projects/ScribeTeX/.worktrees/review-window && python -m pytest tests/test_appcli_refile.py -v`
Expected: FAIL.

- [ ] **Step 3: Write minimal implementation**

In `automation/prompt.py`, add:
```python
def build_refile_prompt(note_path, course, section, subsection, date) -> str:
    return f"""You are ScribeTeX's re-file worker. The placement is ALREADY \
decided by the user — do not second-guess it.

Note file: {note_path}
Course: {course}
Section: {section}
Subsection: {subsection}
Class date: {date}

Call prepare_note(source="file", ref="{note_path}"), transcribe every page to \
LaTeX per the brief (reproduce charts/tables as TikZ/pgfplots/tabular; embed \
freehand drawings via save_figure), then call write_section with course \
"{course}", section "{section}", subsection "{subsection}", date "{date}". \
Do NOT report ambiguous — the user has supplied all placement values.

Print EXACTLY ONE final line:
{RESULT_PREFIX} {{"status":"filed","course":"{course}","section":"{section}","subsection":"{subsection}","date":"{date}","target":"<path>","figures":<int>}}
or on failure:
{RESULT_PREFIX} {{"status":"error","reason":"<what failed>"}}"""
```

In `automation/appcli.py`, add `_refile` and `_discard`:
```python
def _refile(cfg, path, course, section, subsection, date, *, invoke_fn=None) -> dict:
    from scribetex.classify import parse_date
    from .prompt import build_refile_prompt, parse_result
    from .envpath import augmented_env
    src = Path(path).expanduser()
    nr = _config.needs_review_dir(cfg)
    if not src.exists() or src.parent.resolve() != nr.resolve():
        return {"ok": False, "error": f"not a parked note: {src}"}
    date_iso = parse_date(date)
    if not date_iso:
        return {"ok": False, "error": f"unusable date: {date!r}"}
    if invoke_fn is None:
        import subprocess
        def invoke_fn(prompt_text, claude_bin):
            proc = subprocess.run([claude_bin, "-p", prompt_text],
                                  capture_output=True, text=True, timeout=1800,
                                  env=augmented_env())
            return proc.stdout or ""
    stdout = invoke_fn(build_refile_prompt(str(src), course, section, subsection, date_iso),
                       cfg["claude_bin"])
    result = parse_result(stdout)
    if result.get("status") != "filed":
        return {"ok": False, "error": result.get("reason", "re-file did not complete")}
    dest_dir = _config.done_dir(cfg) / date_iso
    dest_dir.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dest_dir / src.name))
    for sfx in (".review.json", ".review.txt", ".error.txt"):
        sc = nr / f"{src.name}{sfx}"
        if sc.exists():
            sc.unlink()
    return {"ok": True, "filed": result}


def _discard(cfg, path) -> dict:
    src = Path(path).expanduser()
    nr = _config.needs_review_dir(cfg)
    if not src.exists() or src.parent.resolve() != nr.resolve():
        return {"ok": False, "error": f"not a parked note: {src}"}
    src.unlink()
    for sfx in (".review.json", ".review.txt", ".error.txt"):
        sc = nr / f"{src.name}{sfx}"
        if sc.exists():
            sc.unlink()
    return {"ok": True, "discarded": src.name}
```
Register subcommands:
```python
rp = sub.add_parser("refile")
for a in ("--path", "--course", "--section", "--subsection", "--date"):
    rp.add_argument(a, required=True)
dp = sub.add_parser("discard"); dp.add_argument("--path", required=True)
```
Dispatch (both load cfg):
```python
if args.cmd == "refile":
    cfg = _load()
    return _emit(_refile(cfg, args.path, args.course, args.section,
                         args.subsection, args.date))
if args.cmd == "discard":
    cfg = _load()
    return _emit(_discard(cfg, args.path))
```
Note: the invoke_fn signature is `(prompt_text, claude_bin)`; the test passes `lambda *a, **k: filed_line`, compatible.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/evane/Desktop/Projects/ScribeTeX/.worktrees/review-window && python -m pytest tests/test_appcli_refile.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add automation/prompt.py automation/appcli.py tests/test_appcli_refile.py
git commit -m "feat: refile prompt + appcli refile/discard (re-transcribe with confirmed placement)"
```

---

### Task 5: Swift — native notifications + Review window (authored)

**Files:**
- Modify: `macapp/ScribeTeX/Bridge.swift`
- Modify: `macapp/ScribeTeX/Models.swift`
- Modify: `macapp/ScribeTeX/ScribeTeXApp.swift`
- Create: `macapp/ScribeTeX/ReviewWindow.swift`
- Modify: `macapp/README.md`
- Test: `tests/test_macapp_review_sources.py`

**Interfaces:** No Python interface. Presence/wiring test only; the user compiles in Xcode.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_macapp_review_sources.py
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "macapp" / "ScribeTeX"


def test_review_window_source_exists():
    assert (APP / "ReviewWindow.swift").exists()


def test_bridge_has_refile_knowncourses_discard():
    b = (APP / "Bridge.swift").read_text()
    for cmd in ("refile", "known-courses", "discard"):
        assert cmd in b, f"Bridge missing {cmd}"


def test_app_uses_usernotifications_and_window():
    app = (APP / "ScribeTeXApp.swift").read_text()
    assert "UserNotifications" in app or "UNUserNotificationCenter" in app
    review = (APP / "ReviewWindow.swift").read_text()
    # window pulls parked notes + files them
    assert "needsReview" in review or "ReviewItem" in review
    assert "refile" in review.lower()


def test_models_review_item_has_guess_fields():
    m = (APP / "Models.swift").read_text()
    for f in ("course", "section", "subsection", "date"):
        assert f in m
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/evane/Desktop/Projects/ScribeTeX/.worktrees/review-window && python -m pytest tests/test_macapp_review_sources.py -v`
Expected: FAIL (ReviewWindow.swift missing; Bridge lacks refile/known-courses/discard; Models lacks guess fields).

- [ ] **Step 3: Author the Swift**

`Models.swift`: extend `ReviewItem` to match the frozen needs-review contract:
```swift
struct ReviewItem: Codable, Identifiable {
    var id: String { path }
    let name: String
    let path: String
    let reason: String?
    let kind: String
    let course: String?
    let section: String?
    let subsection: String?
    let date: String?
}
struct CoursesList: Codable { let ok: Bool; let courses: [String] }
```

`Bridge.swift`: add wrappers (use the existing `run`/`action` infra):
```swift
static func knownCourses() throws -> [String] {
    try JSONDecoder().decode(CoursesList.self, from: run(["known-courses"])).courses
}
@discardableResult
static func refile(path: String, course: String, section: String,
                   subsection: String, date: String) throws -> ActionResult {
    try action(["refile", "--path", path, "--course", course,
                "--section", section, "--subsection", subsection, "--date", date])
}
@discardableResult
static func discard(path: String) throws -> ActionResult {
    try action(["discard", "--path", path])
}
```
(Note: `ActionResult` currently has `ok`/`watcher_running?`/`error?`; refile returns `{ok, filed}`/`{ok, error}` and discard `{ok, discarded}` — decoding into ActionResult works as long as `ok` is present and the extra keys are ignored by the decoder. Confirm ActionResult tolerates unknown keys, which JSONDecoder does by default.)

`ScribeTeXApp.swift`: add `import UserNotifications`; request authorization on launch; when `AppModel.refresh()` observes `needs_review_count` rise, post a `UNMutableNotificationContent` ("N ScribeTeX note(s) need review"); add a `UNUserNotificationCenterDelegate` whose `didReceive` opens the review window (via a shared open-window mechanism / `NSApp.activate` + `openWindow(id:"review")`). Add a `Window(id: "review")` scene rendering `ReviewWindow(model:)`, and a "Review Notes…" `MenuContent` row that opens it.

`ReviewWindow.swift`: a `View` that lists `model.reviewItems`; each item shows name + reason and an editable form:
- Course `Picker` from a `@State courses: [String]` loaded via `Bridge.knownCourses()`, plus a "New course…" text field.
- Section/Subsection `TextField`s (prefilled from item.section/subsection).
- Date `DatePicker` (prefilled from item.date if parseable, else today; formatted yyyy-MM-dd on submit).
- "Re-file" button → `Bridge.refile(...)` inside `model.perform`, disabled while busy; on success refresh + the row drops out.
- "Discard" button → `Bridge.discard(path:)`.

`README.md`: add a "Review window" subsection — notifications now open an in-app Review window where you set course/date and re-file; note re-file re-transcribes (spends tokens, ~2 min); macOS will prompt for notification permission on first launch.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/evane/Desktop/Projects/ScribeTeX/.worktrees/review-window && python -m pytest tests/test_macapp_review_sources.py -v`
Expected: PASS. (Swift not compiled here — user Builds/Runs in Xcode.)

- [ ] **Step 5: Commit**

```bash
git add macapp tests/test_macapp_review_sources.py
git commit -m "feat: native notifications + Review window (authored; user builds in Xcode)"
```

---

### Task 6: Full-suite + plugin validation gate

**Files:** none (verification only).

- [ ] **Step 1: Full suite**

Run: `cd /Users/evane/Desktop/Projects/ScribeTeX/.worktrees/review-window && python -m pytest -q`
Expected: all green. If any EXISTING test still asserts the old `.review.txt` sidecar or the old 4-key needs-review shape, update it to the new `.review.json` / 8-key shape (same behavior, richer data) — do not weaken. Common spots: test_automation_ingest.py (ambiguous → sidecar), test_appcli_needs_review.py.

- [ ] **Step 2: Plugin validation**

Run: `cd /Users/evane/Desktop/Projects/ScribeTeX/.worktrees/review-window && claude plugin validate . 2>&1 | tail -20`
Expected: clean (no manifest change). If `claude` unavailable, JSON-lint the two manifests.

- [ ] **Step 3: appcli smoke (temp fixtures)**

Run:
```bash
cd /Users/evane/Desktop/Projects/ScribeTeX/.worktrees/review-window
D=$(mktemp -d); mkdir -p "$D/NeedsReview"
printf '%%PDF-1.4' > "$D/NeedsReview/x.pdf"
echo '{"reason":"no date","kind":"ambiguous","guess":{"course":"Bio","section":"R","subsection":"S","date":null}}' > "$D/NeedsReview/x.pdf.review.json"
SCRIBETEX_INBOX="$D" PYTHONPATH=.:src python3 -m automation.appcli needs-review
SCRIBETEX_NOTES_ROOT="$D" PYTHONPATH=.:src python3 -m automation.appcli known-courses
```
Expected: needs-review emits one item with course "Bio"/date null; known-courses emits a JSON list.

- [ ] **Step 4: Commit any fixups**

```bash
git add -A && git commit -m "test: review-window suite green" || echo "nothing to fix up"
```

---

## Self-Review

- **Spec coverage:** sidecar (.review.json + prompt guesses)→T1; needs-review guesses + legacy fallback→T2; known-courses→T3; refile prompt + refile/discard→T4; Swift notifications + Review window→T5; gate→T6. Every spec component mapped.
- **Placeholder scan:** all Python steps have real code; the Swift task gives complete Models/Bridge additions + precise requirements for the window/app/README (authored-not-compiled by design).
- **Type consistency:** needs-review keys `{name,path,reason,kind,course,section,subsection,date}` are defined in T2, frozen in T2's contract edit, and mirrored by Swift `ReviewItem` (T5). `refile` args (path/course/section/subsection/date) match the argparse subcommand (T4) and `Bridge.refile` (T5). `build_refile_prompt` signature consistent T4↔its test. `_write_review_sidecar` (T1) writes the exact `guess` object T2 reads. `known-courses`/`refile`/`discard` command names asserted present in Bridge.swift (T5) and registered in argparse (T3/T4). `ActionResult` tolerating extra keys (filed/discarded) noted in T5.
- **Ordering note:** T1 changes the sidecar format; T2/T6 update any existing tests that asserted the old `.review.txt` — called out explicitly so the suite stays green.
