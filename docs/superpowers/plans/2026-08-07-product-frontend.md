# ScribeTeX Product Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the menu-bar-popover utility into a product-grade macOS app with a two-pane main window (sidebar · detail) where the compiled PDF, study guide, and flashcards are viewed in-app and review/correction happen inline.

**Architecture:** Add a SwiftUI `WindowGroup` main window alongside the existing `MenuBarExtra`. The Python bridge is unchanged except three additive read-only appcli commands that feed the viewers. The bolt-on AppKit review/correction windows are retired; their flows become inline detail panels. All actions keep routing through `AppModel.perform(label){…}`.

**Tech Stack:** SwiftUI + PDFKit (macOS 13+), Python 3.11 backend, `automation.appcli` JSON bridge, XcodeGen (`project.yml` → `.xcodeproj`).

## Global Constraints

- Every appcli subcommand prints ONE JSON object to stdout and exits 0; recoverable errors are `{"ok": false, "error": ...}`. New commands follow this exactly.
- New Swift files require `cd macapp && xcodegen generate` before building.
- Backend changes must keep `python -m pytest -q` green; Swift is authored (built in Xcode), validated by source-presence tests + the exact-equality tool-schema test.
- Reuse existing helpers; do not duplicate. `AppModel.perform` already provides named status + elapsed timer + completion notification — every action uses it.
- The Python bridge JSON contract is the Swift/Python boundary: any new command gets a source-presence test in `tests/test_macapp_review_sources.py` so drift is caught.

---

### Task 1: Extend `list_notes` with figure & uncertain counts

**Files:**
- Modify: `src/scribetex/placement.py` (the `list_notes` function, ~line 76)
- Test: `tests/test_placement.py`

**Interfaces:**
- Produces: `list_notes(main_tex) -> [{key, date, sections, figures, uncertain}]` — adds `figures` (count of `\includegraphics` in the note block) and `uncertain` (count of `\uncertain` in the block) to each existing dict.

- [ ] **Step 1: Write the failing test**

```python
def test_list_notes_counts_figures_and_uncertain():
    from scribetex.placement import list_notes, note_block, ENTRIES_START, ENTRIES_END
    body = ("\\section{A}\n\\includegraphics{x}\ntext \\uncertain{42} "
            "\\includegraphics{y}\n")
    doc = (f"H\n{ENTRIES_START}\n{note_block(body, '2026-08-06', 'bio.pdf')}"
           f"{ENTRIES_END}\nT\n")
    n = list_notes(doc)[0]
    assert n["figures"] == 2
    assert n["uncertain"] == 1
```

- [ ] **Step 2: Run it — expect KeyError/failure**

Run: `PYTHONPATH="$PWD:$PWD/src" python -m pytest tests/test_placement.py::test_list_notes_counts_figures_and_uncertain -v`
Expected: FAIL (`figures`/`uncertain` keys absent).

- [ ] **Step 3: Implement**

In `list_notes`, after computing the block substring, count occurrences:

```python
block = main_tex[block_start:block_end]
sections = _SECTION_RE.findall(block)
out.append({
    "key": key, "date": key.split(":", 1)[0], "sections": sections,
    "figures": block.count("\\includegraphics"),
    "uncertain": block.count("\\uncertain"),
})
```

- [ ] **Step 4: Run — expect PASS.** Also run the whole `test_placement.py` and `test_course_tools.py` to confirm nothing else broke (they don't assert exact dict equality).

- [ ] **Step 5: Commit** `feat: list_notes reports per-note figure & uncertain counts`

---

### Task 2: `courses-info` appcli command

**Files:**
- Modify: `automation/appcli.py` (add `_courses_info`, argparse `courses-info`, dispatch)
- Test: `tests/test_appcli_courses_info.py` (create)

**Interfaces:**
- Consumes: `scribetex.discovery.known_courses`, `scribetex.placement.list_notes`, `_course_main_tex`, `_config.needs_review_dir`.
- Produces: `courses-info` → `{"ok": true, "courses": [{name, note_count, needs_review, has_pdf, pdf_path, has_guide, guide_pdf, flashcard_count}]}`. `needs_review` is the global count (from the inbox), attached identically to each course for the sidebar badge (there is no per-course parked-note attribution — parked notes have no course yet).

- [ ] **Step 1: Write the failing test**

```python
import json
from automation import appcli, config

def _cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("SCRIBETEX_NOTES_ROOT", str(tmp_path / "notes"))
    return config.load_config(env={"SCRIBETEX_INBOX": str(tmp_path)}, toml_path=None)

def test_courses_info_reports_metadata(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    from scribetex import server
    server._write_section("Bio", "\\section{A}\nx", "2026-08-06", source_name="n.pdf")
    (tmp_path / "notes" / "Bio" / "flashcards.tsv").write_text("q\ta\nq2\ta2\n")
    r = appcli._courses_info(cfg)
    assert r["ok"] is True
    bio = next(c for c in r["courses"] if c["name"] == "Bio")
    assert bio["note_count"] == 1
    assert bio["flashcard_count"] == 2
    assert bio["has_pdf"] is False        # not compiled
    assert bio["has_guide"] is False
```

- [ ] **Step 2: Run — expect AttributeError** (`_courses_info` missing).

Run: `PYTHONPATH="$PWD:$PWD/src" python -m pytest tests/test_appcli_courses_info.py -v`

- [ ] **Step 3: Implement `_courses_info`**

```python
def _courses_info(cfg) -> dict:
    from scribetex.discovery import known_courses
    from scribetex.placement import list_notes
    from scribetex.config import notes_root
    nr = _config.needs_review_dir(cfg)
    needs = 0
    if nr.exists():
        needs = sum(1 for p in nr.iterdir()
                    if p.is_file() and p.suffix not in (".json", ".txt"))
    out = []
    for name in known_courses(notes_root()):
        main = _course_main_tex(name)
        note_count = 0
        if main and main.exists():
            note_count = len(list_notes(main.read_text(encoding="utf-8")))
        pdf = main.with_suffix(".pdf") if main else None
        guide = main.parent / "study-guide.pdf" if main else None
        tsv = main.parent / "flashcards.tsv" if main else None
        fc = 0
        if tsv and tsv.exists():
            fc = sum(1 for line in tsv.read_text().splitlines() if line.strip())
        out.append({
            "name": name, "note_count": note_count, "needs_review": needs,
            "has_pdf": bool(pdf and pdf.exists()), "pdf_path": str(pdf) if pdf else "",
            "has_guide": bool(guide and guide.exists()),
            "guide_pdf": str(guide) if guide else "",
            "flashcard_count": fc,
        })
    return {"ok": True, "courses": out}
```

Add argparse: `sub.add_parser("courses-info")`. Dispatch: `if args.cmd == "courses-info": cfg = _load(); return _emit(_courses_info(cfg))`.

- [ ] **Step 4: Run — expect PASS.**

- [ ] **Step 5: Commit** `feat: courses-info appcli command for the sidebar`

---

### Task 3: `read-flashcards` appcli command

**Files:**
- Modify: `automation/appcli.py`
- Test: `tests/test_appcli_courses_info.py` (append)

**Interfaces:**
- Produces: `read-flashcards --course` → `{"ok": true, "cards": [{"q": str, "a": str}]}` parsed from `flashcards.tsv` (tab-split, skip blank lines, ignore lines without a tab). `{"ok": false, "error"}` if no tsv.

- [ ] **Step 1: Write the failing test**

```python
def test_read_flashcards_parses_tsv(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    from scribetex import server
    server._write_section("Bio", "\\section{A}\nx", "2026-08-06", source_name="n.pdf")
    (tmp_path / "notes" / "Bio" / "flashcards.tsv").write_text(
        "What detects light?\tPhotoreceptors.\n\nBad line no tab\n")
    r = appcli._read_flashcards(cfg, "Bio")
    assert r["ok"] is True
    assert r["cards"] == [{"q": "What detects light?", "a": "Photoreceptors."}]

def test_read_flashcards_missing(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    from scribetex import server
    server._write_section("Bio", "\\section{A}\nx", "2026-08-06", source_name="n.pdf")
    assert appcli._read_flashcards(cfg, "Bio")["ok"] is False
```

- [ ] **Step 2: Run — expect AttributeError.**

- [ ] **Step 3: Implement**

```python
def _read_flashcards(cfg, course) -> dict:
    main = _course_main_tex(course)
    if main is None:
        return {"ok": False, "error": f"course {course!r} has no usable slug"}
    tsv = main.parent / "flashcards.tsv"
    if not tsv.exists():
        return {"ok": False, "error": f"no flashcards yet for {course}"}
    cards = []
    for line in tsv.read_text(encoding="utf-8").splitlines():
        if "\t" not in line:
            continue
        q, a = line.split("\t", 1)
        cards.append({"q": q, "a": a})
    return {"ok": True, "cards": cards}
```

Add argparse `read-flashcards --course` + dispatch.

- [ ] **Step 4: Run — expect PASS.**

- [ ] **Step 5: Commit** `feat: read-flashcards appcli command`

---

### Task 4: `compile-guide` appcli command

**Files:**
- Modify: `automation/appcli.py`
- Test: `tests/test_appcli_compile.py` (append)

**Interfaces:**
- Consumes: `scribetex.compile.compile_course` (takes a `Path`), `_deliver_pdf`.
- Produces: `compile-guide --course` → compiles `<course>/study-guide.tex`; same result shape as `_compile` (`{ok, compiled, pdf, errors, ...}`); delivers to `output_dir` if set.

- [ ] **Step 1: Write the failing test** (toolchain-independent path)

```python
def test_compile_guide_missing_file(tmp_path, monkeypatch):
    monkeypatch.setenv("SCRIBETEX_NOTES_ROOT", str(tmp_path / "notes"))
    cfg = config.load_config(env={"SCRIBETEX_INBOX": str(tmp_path)}, toml_path=None)
    # course exists but no study-guide.tex yet
    from scribetex import server
    server._write_section("Bio", "\\section{A}\nx", "2026-08-06", source_name="n.pdf")
    r = appcli._compile_guide(cfg, "Bio")
    assert r["ok"] is False  # study-guide.tex not generated yet
```

- [ ] **Step 2: Run — expect AttributeError.**

- [ ] **Step 3: Implement**

```python
def _compile_guide(cfg, course) -> dict:
    from scribetex.compile import compile_course
    main = _course_main_tex(course)
    if main is None:
        return {"ok": False, "error": f"course {course!r} has no usable slug"}
    guide = main.parent / "study-guide.tex"
    if not guide.exists():
        return {"ok": False, "error": f"no study guide yet for {course}; generate it first"}
    res = compile_course(guide)
    if res.get("compiled"):
        d = _deliver_pdf(cfg, res.get("pdf"))
        if d:
            res["delivered_to"] = d
    return {"ok": bool(res.get("compiled")), **res}
```

Add argparse `compile-guide --course` + dispatch.

- [ ] **Step 4: Run — expect PASS.**

- [ ] **Step 5: Commit** `feat: compile-guide appcli command`

---

### Task 5: Models + Bridge wrappers for the new commands

**Files:**
- Modify: `macapp/ScribeTeX/Models.swift`
- Modify: `macapp/ScribeTeX/Bridge.swift`
- Test: `tests/test_macapp_review_sources.py`

**Interfaces:**
- Produces (Swift): `CourseInfo` Codable (name, note_count, needs_review, has_pdf, pdf_path, has_guide, guide_pdf, flashcard_count); `CoursesInfoList{ok, courses}`; `Flashcard{q,a}`; `FlashcardList{ok, cards}`. Bridge: `coursesInfo() -> [CourseInfo]`, `readFlashcards(course:) -> [Flashcard]`, `compileGuide(course:) -> ActionResult`. Extend `NoteRef` with `figures:Int` and `uncertain:Int` (defaulted via custom decoding or made non-optional to match Task 1).

- [ ] **Step 1: Write the failing test**

```python
def test_bridge_has_frontend_commands():
    b = (APP / "Bridge.swift").read_text()
    for cmd in ("courses-info", "read-flashcards", "compile-guide"):
        assert cmd in b, f"Bridge missing {cmd}"

def test_models_has_courseinfo_and_flashcard():
    m = (APP / "Models.swift").read_text()
    assert "struct CourseInfo" in m and "struct Flashcard" in m
```

- [ ] **Step 2: Run — expect FAIL.**

Run: `python -m pytest tests/test_macapp_review_sources.py -k "frontend or courseinfo" -v`

- [ ] **Step 3: Add the Codable structs to Models.swift**

```swift
struct CourseInfo: Codable, Identifiable {
    var id: String { name }
    let name: String
    let note_count: Int
    let needs_review: Int
    let has_pdf: Bool
    let pdf_path: String
    let has_guide: Bool
    let guide_pdf: String
    let flashcard_count: Int
}
struct CoursesInfoList: Codable { let ok: Bool; let courses: [CourseInfo] }
struct Flashcard: Codable, Identifiable {
    var id: String { q }
    let q: String; let a: String
}
struct FlashcardList: Codable { let ok: Bool; let cards: [Flashcard] }
```

Update `NoteRef` to add `let figures: Int` and `let uncertain: Int`.

- [ ] **Step 4: Add Bridge wrappers**

```swift
static func coursesInfo() throws -> [CourseInfo] {
    try JSONDecoder().decode(CoursesInfoList.self, from: run(["courses-info"])).courses
}
static func readFlashcards(course: String) throws -> [Flashcard] {
    try JSONDecoder().decode(FlashcardList.self,
        from: run(["read-flashcards", "--course", course])).cards
}
@discardableResult
static func compileGuide(course: String) throws -> ActionResult {
    try action(["compile-guide", "--course", course], timeout: 300)
}
```

- [ ] **Step 5: Run the presence tests — expect PASS. Commit** `feat: Swift models + bridge for frontend commands`

---

### Task 6: Main window shell (WindowGroup + NavigationSplitView) & AppModel selection state

**Files:**
- Create: `macapp/ScribeTeX/MainWindow.swift`
- Modify: `macapp/ScribeTeX/ScribeTeXApp.swift` (add the `WindowGroup`, open-from-menu)
- Modify: `macapp/ScribeTeX/ScribeTeXApp.swift` (AppModel: add `@Published var courses: [CourseInfo]`, `selectedCourse: String?`, `selectedTab`, `loadCourses()`)
- Test: `tests/test_macapp_review_sources.py`

**Interfaces:**
- Consumes: `Bridge.coursesInfo()`, `AppModel`.
- Produces: a `WindowGroup(id: "main")` showing `MainWindow(model:)`; `MainWindow` is a `NavigationSplitView { Sidebar } detail: { DetailPane }`. A `MainWindowController`-free approach: open via SwiftUI `openWindow(id:"main")` from the menu is unreliable under LSUIElement, so reuse the proven AppKit-window pattern OR set activation policy `.regular` and use a `WindowGroup` — **decision: use a single AppKit `NSWindow` host (like the retired ReviewWindowController) to guarantee it shows under LSUIElement**, hosting `MainWindow`. Name it `MainWindowController`.

- [ ] **Step 1: Add selection state to AppModel** (in ScribeTeXApp.swift)

```swift
@Published var courses: [CourseInfo] = []
@Published var selectedCourse: String?
@Published var detailTab: DetailTab = .notes   // enum DetailTab { case notes, pdf, guide, flashcards, review, correct }

func loadCourses() {
    Task.detached(priority: .userInitiated) {
        let list = (try? Bridge.coursesInfo()) ?? []
        await MainActor.run { self.courses = list }
    }
}
```

- [ ] **Step 2: Create `MainWindowController` (AppKit host, reuse the ReviewWindowController pattern)** in MainWindow.swift — flips activation policy to `.regular` on show, hosts `NSHostingController(rootView: MainWindow(model:))`, single reused window, reverts to `.accessory` on close.

- [ ] **Step 3: Create `MainWindow` view**: `NavigationSplitView` with `Sidebar(model:)` and `DetailPane(model:)` (both stubbed to `Text("…")` for now so it compiles). `.frame(minWidth: 900, minHeight: 560)`. `.onAppear { model.loadCourses() }`.

- [ ] **Step 4: Add "Open ScribeTeX" to the menu** (MenuContent footer) calling `MainWindowController.shared.show(model: model)`.

- [ ] **Step 5: `xcodegen generate`; presence test** asserts `MainWindow.swift` exists and `NavigationSplitView` appears. Build in Xcode (⌘R): the window opens with two empty panes.

- [ ] **Step 6: Commit** `feat: main window shell (two-pane) + Open ScribeTeX`

---

### Task 7: Sidebar (courses + needs-review)

**Files:**
- Create: `macapp/ScribeTeX/Sidebar.swift`
- Modify: `macapp/ScribeTeX/MainWindow.swift` (wire in real Sidebar)
- Test: presence test

**Interfaces:**
- Consumes: `model.courses` (`[CourseInfo]`), `model.selectedCourse`, `model.status?.needs_review_count`.
- Produces: a `List` with a "Courses" section (each row: name + note_count badge) binding selection to `model.selectedCourse`, and a "Needs Review" section (from `model.reviewItems`) whose rows set `model.detailTab = .review` and a `model.reviewTarget`.

- [ ] **Step 1: Build the Sidebar `List`** — Courses section (selectable rows, note-count badge), Needs Review section (count badge, rows open the review panel). Selecting a course sets `selectedCourse` and resets `detailTab = .notes`.
- [ ] **Step 2: Wire into MainWindow**, remove the stub.
- [ ] **Step 3: `xcodegen generate`; presence test** (`Sidebar.swift` exists, references `model.courses`).
- [ ] **Step 4: Build (⌘R)** — sidebar lists real courses; clicking selects.
- [ ] **Step 5: Commit** `feat: sidebar with courses + needs-review`

---

### Task 8: Notes tab

**Files:**
- Create: `macapp/ScribeTeX/NotesTab.swift`
- Modify: `macapp/ScribeTeX/DetailPane.swift` (created here as the tab host)
- Create: `macapp/ScribeTeX/DetailPane.swift`
- Test: presence test

**Interfaces:**
- Consumes: `Bridge.listNotes(course:)` → `[NoteRef]` (now with figures/uncertain), `model.detailTab`.
- Produces: `DetailPane` = a top tab bar (Notes/PDF/Guide/Flashcards) switching on `model.detailTab`, plus routes to ReviewPanel/CorrectPanel when those tabs are active. `NotesTab` lists notes as cards (`date — sections.joined(", ")`, `"\(figures) figures · \(uncertain) uncertain"`, a "Correct…" button setting `detailTab = .correct` + `correctTarget`).

- [ ] **Step 1: Create `DetailPane`** with a segmented top tab bar bound to `model.detailTab`; body `switch`es to each tab view (PDF/Guide/Flashcards stubbed to `Text`).
- [ ] **Step 2: Create `NotesTab`** — loads notes for `model.selectedCourse` via `Bridge.listNotes` off-main; renders cards; empty state "No notes filed yet."; "Correct…" wires to the correct panel.
- [ ] **Step 3: `xcodegen generate`; presence test.**
- [ ] **Step 4: Build (⌘R)** — selecting a course shows its notes as cards.
- [ ] **Step 5: Commit** `feat: notes tab + detail tab bar`

---

### Task 9: PDF tab (PDFKit preview + compile controls)

**Files:**
- Create: `macapp/ScribeTeX/PDFTab.swift`
- Create: `macapp/ScribeTeX/PDFPreview.swift` (NSViewRepresentable wrapping PDFView)
- Modify: `macapp/ScribeTeX/DetailPane.swift`
- Test: presence test

**Interfaces:**
- Consumes: `model.courses` (to find `pdf_path`/`has_pdf` for the selected course), `Bridge.compile/build/openPDF`.
- Produces: `PDFPreview(url:)` NSViewRepresentable; `PDFTab` shows the PDF if present, else an empty state with a Compile button. Toolbar: Compile, Compile+auto-fix, Open in Preview. After a compile via `perform`, `model.loadCourses()` refreshes `has_pdf`/`pdf_path` and the view reloads.

- [ ] **Step 1: Create `PDFPreview`** — `NSViewRepresentable` that creates a `PDFView`, sets `.autoScales = true`, loads `PDFDocument(url:)`; `updateNSView` reloads if the URL changed.
- [ ] **Step 2: Create `PDFTab`** — resolves the selected course's `pdf_path`; if `has_pdf` shows `PDFPreview`, else empty state; toolbar buttons call `model.perform("Compiling \(course)"){…}` etc.; a compile-error banner when the last build reported errors (store last error text on the model or re-run compile to read it — v1: rely on the completion notification + red `lastError`).
- [ ] **Step 3: Wire into DetailPane; `xcodegen generate`; presence test** (`PDFTab.swift`, `PDFPreview.swift`, `import PDFKit`).
- [ ] **Step 4: Build (⌘R)** — PDF tab renders BIOS 12000's compiled PDF; Compile button works and reloads.
- [ ] **Step 5: Commit** `feat: PDF tab with embedded PDFKit preview`

---

### Task 10: Study Guide tab

**Files:**
- Create: `macapp/ScribeTeX/StudyGuideTab.swift`
- Modify: `macapp/ScribeTeX/DetailPane.swift`
- Test: presence test

**Interfaces:**
- Consumes: `model.courses` (`has_guide`/`guide_pdf`), `Bridge.studyGuide(course:)`, `Bridge.compileGuide(course:)`, reuses `PDFPreview`.
- Produces: `StudyGuideTab` — a **Generate study guide** button (runs `studyGuide`, then `compileGuide`), and a `PDFPreview` of `study-guide.pdf`. Empty state before first generation.

- [ ] **Step 1: Create `StudyGuideTab`** — if `has_guide` show `PDFPreview(url: guide_pdf)`; toolbar: Generate (chains `studyGuide` then `compileGuide` in one `perform` via a Bridge helper `generateAndCompileGuide`), Recompile. Empty state otherwise.
- [ ] **Step 2: Add `Bridge.generateAndCompileGuide(course:)`** that runs both commands sequentially (study-guide then compile-guide), returning the compile result.
- [ ] **Step 3: Wire into DetailPane; `xcodegen generate`; presence test.**
- [ ] **Step 4: Build (⌘R)** — Generate produces + previews the standalone guide PDF.
- [ ] **Step 5: Commit** `feat: study guide tab (generate + preview)`

---

### Task 11: Flashcards tab (flip-card study deck)

**Files:**
- Create: `macapp/ScribeTeX/FlashcardsTab.swift`
- Modify: `macapp/ScribeTeX/DetailPane.swift`
- Test: presence test

**Interfaces:**
- Consumes: `Bridge.readFlashcards(course:)` → `[Flashcard]`, `Bridge.flashcards(course:)` (generate).
- Produces: `FlashcardsTab` — loads cards; shows one card (Question, tap/Flip to reveal Answer), Prev/Next, "Card k of N" + progress; toolbar: Generate flashcards, Export to Anki (reveals the tsv via the existing appcli reveal on `flashcards` — or a new `open-flashcards` that reveals). Empty state before generation.

- [ ] **Step 1: Create `FlashcardsTab`** with `@State cards`, `@State index`, `@State showAnswer`. Card view flips on click; Prev/Next bounded; progress = `(index+1)/cards.count`. Loads via `Bridge.readFlashcards` off-main on appear + after generate.
- [ ] **Step 2: Export to Anki** — the existing `flashcards` command already reveals the tsv (`_study_guide(reveal)` path); add a lightweight `Bridge.flashcards` call for Generate, and for Export reuse `open-pdf`-style reveal via a new `reveal-flashcards` appcli command (or call `flashcards` which reveals). Keep it simple: Generate = `flashcards`; Export = reveal the existing tsv.
- [ ] **Step 3: Wire into DetailPane; `xcodegen generate`; presence test** (`FlashcardsTab.swift`, "Flip").
- [ ] **Step 4: Build (⌘R)** — deck of 78 BIOS cards flips and navigates.
- [ ] **Step 5: Commit** `feat: flashcards study tab (flip cards)`

---

### Task 12: Inline Review & Correct panels; retire AppKit windows

**Files:**
- Create: `macapp/ScribeTeX/ReviewPanel.swift` (from `ReviewWindow` body)
- Create: `macapp/ScribeTeX/CorrectPanel.swift` (from `CorrectionWindow` body)
- Modify: `macapp/ScribeTeX/DetailPane.swift` (route `.review`/`.correct`)
- Delete: `macapp/ScribeTeX/ReviewWindow.swift`, `macapp/ScribeTeX/CorrectionWindow.swift`
- Modify: `macapp/ScribeTeX/ScribeTeXApp.swift` (remove `ReviewWindowController`; keep notification-tap → open main window on the review tab)
- Modify: `macapp/ScribeTeX/MenuContent.swift` (remove the old "Review Notes…"/"Correct a note…" window triggers; the sidebar/notes now drive these)
- Test: `tests/test_macapp_review_sources.py` (update: assert ReviewPanel/CorrectPanel exist; drop the old window-source assertions)

**Interfaces:**
- Consumes: existing review/correct logic (`Bridge.refile/discard/correct/listNotes/knownCourses`).
- Produces: `ReviewPanel(model:)` and `CorrectPanel(model:, noteKey:)` rendered in the detail pane; `AppModel.reviewTarget`/`correctTarget` selection state.

- [ ] **Step 1: Extract `ReviewPanel`** from `ReviewWindow`'s SwiftUI body (course picker + date + Re-file/Discard), driven by `model.reviewTarget`; on success clear target + `loadCourses()`.
- [ ] **Step 2: Extract `CorrectPanel`** from `CorrectionWindow`'s body (course/note preselected from `correctTarget`, instruction field, re-read toggle, Apply); Back sets `detailTab = .notes`.
- [ ] **Step 3: Route in DetailPane** — `.review` → ReviewPanel, `.correct` → CorrectPanel.
- [ ] **Step 4: Delete the two window files + `ReviewWindowController`/`CorrectionWindowController`;** repoint the notification-tap handler to `MainWindowController.shared.show` + `model.detailTab = .review`.
- [ ] **Step 5: Update MenuContent** — the standalone window-opening rows go away; keep "Open ScribeTeX".
- [ ] **Step 6: `xcodegen generate`; update presence tests** (ReviewPanel/CorrectPanel exist; the retired files no longer referenced).
- [ ] **Step 7: Build (⌘R)** — review a parked note and correct a filed note entirely inside the main window.
- [ ] **Step 8: Commit** `refactor: inline review & correct panels; retire AppKit windows`

---

### Task 13: Full-suite green + docs + final xcodegen

**Files:**
- Modify: `README.md` (screenshot-free: describe the new main window + tabs)
- Verify: all tests

- [ ] **Step 1:** `PYTHONPATH="$PWD:$PWD/src" python -m pytest -q` — all green.
- [ ] **Step 2:** `cd macapp && xcodegen generate` — confirm every new Swift file appears in `project.pbxproj`.
- [ ] **Step 3:** Update README "Easy setup" section to describe the windowed app (sidebar · Notes/PDF/Study Guide/Flashcards tabs · inline review/correct).
- [ ] **Step 4:** Build (⌘R) end-to-end smoke: select course → compile → view PDF → generate guide → generate + flip flashcards → review a parked note → correct a filed note.
- [ ] **Step 5: Commit** `docs: describe the product frontend`

---

## Self-Review

**Spec coverage:** shell (Task 6), sidebar (7), Notes/PDF/Guide/Flashcards tabs (8–11), inline review/correct + window retirement (12), three backend commands (2–4), model/figure counts (1,5). All spec sections mapped.

**Placeholder scan:** none — each Swift task ends in a build+presence check; each Python task has concrete test code + implementation.

**Type consistency:** `CourseInfo` fields match `_courses_info` JSON keys exactly; `Flashcard{q,a}` matches `_read_flashcards`; `NoteRef` gains `figures`/`uncertain` in both Task 1 (Python) and Task 5 (Swift) — kept in lockstep. `DetailTab` enum is the single source for tab routing across Tasks 6/8/12.

**Risk:** Task 6's LSUIElement window-showing reuses the proven AppKit `NSWindow` host pattern (not SwiftUI `openWindow`, which we know is unreliable from the menu-bar context) — this is called out explicitly so the implementer doesn't repeat the earlier openWindow trap.
