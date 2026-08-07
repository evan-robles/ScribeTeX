"""JSON bridge CLI for the ScribeTeX menu-bar app.

Each subcommand prints ONE JSON object to stdout and exits 0. Recoverable
errors are reported as {"ok": false, "error": ...} (still exit 0) so the Swift
caller always receives parseable JSON.
"""
from __future__ import annotations
import argparse
import contextlib
import datetime as _dt
import io
import json
import shutil
import sys
from pathlib import Path

from . import config as _config
from . import ingest as _ingest
from . import install as _install
from .envpath import augmented_path as _augmented_path


def _config_toml_path() -> Path:
    return Path.home() / ".config" / "scribetex" / "automation.toml"


def _load():
    return _config.load_config(toml_path=_config_toml_path())


def _count_files(d: Path) -> int:
    if not d.exists():
        return 0
    return sum(1 for p in d.iterdir() if p.is_file())


def _status_dict(cfg, *, plist_paths_fn=None, which_fn=None, now_fn=None) -> dict:
    plist_paths_fn = plist_paths_fn or _install.plist_paths
    # Default detection augments PATH with ~/.local/bin, Homebrew, etc., so a
    # GUI-launched app (minimal PATH) still finds a user-installed `claude`.
    which_fn = which_fn or (lambda name: shutil.which(name, path=_augmented_path()))
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
            1 for p in nr.iterdir()
            if p.is_file() and p.suffix not in (".json", ".txt")
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


@contextlib.contextmanager
def _suppress_stdout():
    """Swallow stdout from a wrapped call so only our JSON reaches the caller.

    install.main prints human-readable status lines; if those hit stdout they
    corrupt the single-JSON-object contract the Swift app decodes.
    """
    with contextlib.redirect_stdout(io.StringIO()):
        yield


def _known_courses() -> list:
    from scribetex.discovery import known_courses
    from scribetex.config import notes_root
    return known_courses(notes_root())


def _resolve_parked_note(cfg, path):
    """Resolve a NeedsReview note path safely, or return (None, error_dict).

    Guards against path traversal / symlink escape: a legitimately-parked note
    (written by route_file/give_up_file via shutil.move of a real PDF) is never a
    symlink, and its real path always sits directly inside NeedsReview/. Reject a
    symlink outright, and require the RESOLVED path's parent to be NeedsReview so
    a crafted symlink inside NeedsReview can't make refile/discard act on a file
    elsewhere.
    """
    src = Path(path).expanduser()
    nr = _config.needs_review_dir(cfg)
    if not src.exists() or src.is_symlink():
        return None, {"ok": False, "error": f"not a parked note: {src}"}
    real = src.resolve()
    if real.parent != nr.resolve():
        return None, {"ok": False, "error": f"not a parked note: {src}"}
    return real, None


def _refile(cfg, path, course, date, *, invoke_fn=None) -> dict:
    from scribetex.classify import parse_date
    from .prompt import (build_refile_prompt, parse_result, allowed_tools_args,
                         mcp_config_args, new_nonce)
    from .envpath import augmented_env
    src, err = _resolve_parked_note(cfg, path)
    if err:
        return err
    nr = _config.needs_review_dir(cfg)
    date_iso = parse_date(date)
    if not date_iso:
        return {"ok": False, "error": f"unusable date: {date!r}"}
    nonce = new_nonce()
    if invoke_fn is None:
        import subprocess
        def invoke_fn(prompt_text, claude_bin):
            # Give the worker the ScribeTeX MCP server explicitly (--mcp-config)
            # so prepare_note/write_section exist and it gets the server context,
            # and pre-authorize the tools (headless `claude -p` can't prompt).
            proc = subprocess.run(
                [claude_bin, "-p", prompt_text,
                 *mcp_config_args(), *allowed_tools_args()],
                capture_output=True, text=True, timeout=1800,
                env=augmented_env())
            return proc.stdout or ""
    try:
        prompt_text = build_refile_prompt(str(src), course, date_iso, nonce)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    stdout = invoke_fn(prompt_text, cfg["claude_bin"])
    result = parse_result(stdout, nonce)
    if result.get("status") != "filed":
        return {"ok": False, "error": result.get("reason", "re-file did not complete")}
    # Trust "filed" only if the worker actually wrote the course document: an
    # existing main.tex inside the notes root. An authenticated result whose
    # target is missing or points elsewhere means nothing was legitimately
    # written, so keep the note in NeedsReview rather than moving it (data loss).
    target = result.get("target")
    if not _ingest._valid_written_target(target):
        return {"ok": False,
                "error": f"worker reported filed but target is not a valid "
                         f"course main.tex under the notes root: {target!r}"}
    # Reject a lossy transcription that dropped a figure; the note stays parked
    # so the user can re-file (which replaces the block via date+filename dedup).
    from .prompt import figures_complete
    ok, reason = figures_complete(result)
    if not ok:
        return {"ok": False, "error": reason}
    dest_dir = _config.done_dir(cfg) / date_iso
    dest_dir.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dest_dir / src.name))
    for sfx in (".review.json", ".review.txt", ".error.txt"):
        sc = nr / f"{src.name}{sfx}"
        if sc.exists():
            sc.unlink()
    return {"ok": True, "filed": result}


def _discard(cfg, path) -> dict:
    src, err = _resolve_parked_note(cfg, path)
    if err:
        return err
    nr = _config.needs_review_dir(cfg)
    src.unlink()
    for sfx in (".review.json", ".review.txt", ".error.txt"):
        sc = nr / f"{src.name}{sfx}"
        if sc.exists():
            sc.unlink()
    return {"ok": True, "discarded": src.name}


def _course_main_tex(course):
    from scribetex.config import notes_root
    from scribetex.classify import course_slug
    slug = course_slug(course)
    if not slug:
        return None
    return notes_root() / slug / "main.tex"


def _deliver_pdf(cfg, pdf_path) -> str | None:
    """Copy a compiled PDF into the configured output_dir (e.g. an iCloud folder
    for the iPad). No-op if output_dir is unset or the PDF is missing. Returns
    the delivered path, or None."""
    out = (cfg.get("output_dir") or "").strip()
    if not out or not pdf_path:
        return None
    src = Path(pdf_path)
    if not src.exists():
        return None
    dest_dir = Path(out).expanduser()
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / src.name
        shutil.copy2(src, dest)
        return str(dest)
    except OSError:
        return None


def _compile(cfg, course) -> dict:
    """Plain compile (no LLM): run the toolchain, return structured result."""
    from scribetex.compile import compile_course
    target = _course_main_tex(course)
    if target is None:
        return {"ok": False, "error": f"course {course!r} has no usable slug"}
    res = compile_course(target)
    if res.get("compiled"):
        delivered = _deliver_pdf(cfg, res.get("pdf"))
        if delivered:
            res["delivered_to"] = delivered
    return {"ok": bool(res.get("compiled")), **res}


def _open_pdf(cfg, course) -> dict:
    """Return the course PDF path (and open it) if it exists."""
    import subprocess
    target = _course_main_tex(course)
    if target is None:
        return {"ok": False, "error": f"course {course!r} has no usable slug"}
    pdf = target.with_suffix(".pdf")
    if not pdf.exists():
        return {"ok": False, "error": f"no compiled PDF yet for {course}"}
    try:
        subprocess.run(["open", str(pdf)], check=False,
                       env=_ingest.augmented_env() if hasattr(_ingest, "augmented_env") else None)
    except Exception:
        pass
    return {"ok": True, "pdf": str(pdf)}


def _build(cfg, course, *, invoke_fn=None) -> dict:
    """Compile with surgical LLM error-recovery: compile, and if it fails let the
    worker patch only the offending note blocks and recompile (bounded)."""
    from .prompt import (build_compile_prompt, parse_result, allowed_tools_args,
                         mcp_config_args, new_nonce)
    from .envpath import augmented_env
    from scribetex.compile import compile_course, toolchain_missing
    target = _course_main_tex(course)
    if target is None or not target.exists():
        return {"ok": False, "error": f"course document not found for {course!r}"}
    missing = toolchain_missing()
    if missing:
        return {"ok": False, "error": f"'{missing}' not on PATH; install MacTeX/TeX Live"}
    # Fast path: if it already compiles, skip the (expensive) LLM worker.
    first = compile_course(target)
    if first.get("compiled"):
        out = {"ok": True, "compiled": True, "pdf": first.get("pdf"), "rounds": 0}
        d = _deliver_pdf(cfg, first.get("pdf"))
        if d:
            out["delivered_to"] = d
        return out
    nonce = new_nonce()
    if invoke_fn is None:
        import subprocess
        def invoke_fn(prompt_text, claude_bin):
            proc = subprocess.run(
                [claude_bin, "-p", prompt_text,
                 *mcp_config_args(), *allowed_tools_args()],
                capture_output=True, text=True, timeout=1800, env=augmented_env())
            return proc.stdout or ""
    stdout = invoke_fn(build_compile_prompt(course, nonce), cfg["claude_bin"])
    result = parse_result(stdout, nonce)
    if result.get("status") == "compiled":
        out = {"ok": True, "compiled": True, "pdf": result.get("pdf"),
               "rounds": result.get("rounds"), "patched": result.get("patched", [])}
        # The recovered PDF path from the worker may be relative; recompute from
        # the known target so delivery uses an absolute path.
        d = _deliver_pdf(cfg, str(target.with_suffix(".pdf")))
        if d:
            out["delivered_to"] = d
        return out
    return {"ok": False, "compiled": False,
            "error": "could not auto-fix compile errors",
            "errors": result.get("errors", []), "rounds": result.get("rounds")}


def _list_notes(cfg, course) -> dict:
    """List a course's filed notes (key/date/section titles) for a picker."""
    from scribetex.placement import list_notes
    target = _course_main_tex(course)
    if target is None or not target.exists():
        return {"ok": False, "error": f"course document not found for {course!r}"}
    return {"ok": True, "notes": list_notes(target.read_text(encoding="utf-8"))}


def _correct(cfg, course, note_key, instruction, reread=False, *, invoke_fn=None) -> dict:
    """Apply a plain-language fix to ONE filed note via the correction worker."""
    from .prompt import (build_correct_prompt, parse_result, allowed_tools_args,
                         mcp_config_args, new_nonce)
    from .envpath import augmented_env
    target = _course_main_tex(course)
    if target is None or not target.exists():
        return {"ok": False, "error": f"course document not found for {course!r}"}
    # For re-read mode, locate the note's original file under Done/ (best effort).
    note_path = ""
    if reread:
        date = note_key.split(":", 1)[0]
        done_day = _config.done_dir(cfg) / date
        if done_day.exists():
            for f in done_day.iterdir():
                if f.is_file():
                    note_path = str(f)
                    break
    nonce = new_nonce()
    if invoke_fn is None:
        import subprocess
        def invoke_fn(prompt_text, claude_bin):
            proc = subprocess.run(
                [claude_bin, "-p", prompt_text,
                 *mcp_config_args(), *allowed_tools_args()],
                capture_output=True, text=True, timeout=1800, env=augmented_env())
            return proc.stdout or ""
    try:
        prompt_text = build_correct_prompt(course, note_key, instruction, nonce,
                                           note_path=note_path)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    stdout = invoke_fn(prompt_text, cfg["claude_bin"])
    result = parse_result(stdout, nonce)
    if result.get("status") != "corrected":
        return {"ok": False, "error": result.get("reason", "correction did not complete")}
    return {"ok": True, "corrected": result}


def _run_course_worker(cfg, course, prompt_builder, ok_status, *, invoke_fn=None) -> dict:
    """Shared driver for whole-course worker passes (study aid / verify / caption).
    Launches the headless worker with the ScribeTeX MCP server and returns the
    parsed result on the expected ok_status."""
    from .prompt import (parse_result, allowed_tools_args, mcp_config_args, new_nonce)
    from .envpath import augmented_env
    target = _course_main_tex(course)
    if target is None or not target.exists():
        return {"ok": False, "error": f"course document not found for {course!r}"}
    nonce = new_nonce()
    if invoke_fn is None:
        import subprocess
        def invoke_fn(prompt_text, claude_bin):
            proc = subprocess.run(
                [claude_bin, "-p", prompt_text,
                 *mcp_config_args(), *allowed_tools_args()],
                capture_output=True, text=True, timeout=1800, env=augmented_env())
            return proc.stdout or ""
    try:
        prompt_text = prompt_builder(nonce)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    result = parse_result(invoke_fn(prompt_text, cfg["claude_bin"]), nonce)
    if result.get("status") != ok_status:
        return {"ok": False, "error": result.get("reason", f"{ok_status} did not complete")}
    return {"ok": True, "result": result}


def _reveal(path) -> None:
    """Reveal a file in Finder (selects it), best-effort."""
    if not path:
        return
    p = Path(path)
    if not p.exists():
        return
    try:
        import subprocess
        subprocess.run(["open", "-R", str(p)], check=False)
    except Exception:
        pass


def _study_guide(cfg, course, kind="guide", *, invoke_fn=None, reveal=True) -> dict:
    from .prompt import build_studyguide_prompt
    res = _run_course_worker(
        cfg, course, lambda n: build_studyguide_prompt(course, kind, n),
        "study_aid", invoke_fn=invoke_fn)
    # Surface the output so the user can find it: flashcards.tsv (to import into
    # Anki) is revealed in Finder; the study guide lives inside main.tex, so we
    # reveal that. The written path is echoed in the result either way.
    if res.get("ok"):
        path = (res.get("result") or {}).get("path")
        res["path"] = path
        if reveal:
            _reveal(path)
    return res


def _verify(cfg, course, note_key="", *, invoke_fn=None) -> dict:
    from .prompt import build_verify_prompt
    return _run_course_worker(
        cfg, course, lambda n: build_verify_prompt(course, note_key, n),
        "verified", invoke_fn=invoke_fn)


def _caption(cfg, course, *, invoke_fn=None) -> dict:
    from .prompt import build_caption_prompt
    return _run_course_worker(
        cfg, course, lambda n: build_caption_prompt(course, n),
        "captioned", invoke_fn=invoke_fn)


def _emit(obj) -> int:
    print(json.dumps(obj))
    return 0


def _render_toml(data: dict) -> str:
    lines = []
    for k, v in data.items():
        if isinstance(v, str):
            lines.append(f"{k} = {json.dumps(v)}")
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


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="ScribeTeX app JSON bridge.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    sub.add_parser("needs-review")
    sub.add_parser("known-courses")
    sp = sub.add_parser("set-inbox")
    sp.add_argument("--path", required=True)
    pp = sub.add_parser("process")
    pp.add_argument("--path", required=True)
    sub.add_parser("sweep")
    sub.add_parser("install")
    sub.add_parser("uninstall")
    rp = sub.add_parser("refile")
    # Only course + date are user-supplied placement; the note's section
    # structure is authored by the LLM from the note's content.
    for a in ("--path", "--course", "--date"):
        rp.add_argument(a, required=True)
    dp = sub.add_parser("discard"); dp.add_argument("--path", required=True)
    cp = sub.add_parser("compile"); cp.add_argument("--course", required=True)
    bp = sub.add_parser("build"); bp.add_argument("--course", required=True)
    op = sub.add_parser("open-pdf"); op.add_argument("--course", required=True)
    lp = sub.add_parser("list-notes"); lp.add_argument("--course", required=True)
    kp = sub.add_parser("correct")
    for a in ("--course", "--note-key", "--instruction"):
        kp.add_argument(a, required=True)
    kp.add_argument("--reread", action="store_true")
    gp = sub.add_parser("study-guide"); gp.add_argument("--course", required=True)
    fp = sub.add_parser("flashcards"); fp.add_argument("--course", required=True)
    vp = sub.add_parser("verify")
    vp.add_argument("--course", required=True)
    vp.add_argument("--note-key", default="")
    xp = sub.add_parser("caption-figures"); xp.add_argument("--course", required=True)
    args = ap.parse_args(argv)

    try:
        return _dispatch(args)
    except Exception as e:  # config load / engine errors -> clean JSON, exit 0
        return _emit({"ok": False, "error": str(e)})


def _dispatch(args) -> int:
    if args.cmd == "known-courses":
        return _emit({"ok": True, "courses": _known_courses()})
    if args.cmd == "status":
        cfg = _load()
        return _emit(_status_dict(cfg))
    if args.cmd == "needs-review":
        cfg = _load()
        return _emit({"ok": True, "items": _needs_review_items(cfg)})
    if args.cmd == "set-inbox":
        return _emit(_write_inbox_config(args.path, _config_toml_path()))
    if args.cmd == "process":
        cfg = _load()
        return _emit(_process_path(cfg, args.path))
    if args.cmd == "sweep":
        cfg = _load()
        return _emit({"ok": True, "processed": _ingest.process_inbox(cfg)})
    if args.cmd == "install":
        cfg = _load()
        # Report preflight problems as JSON (never as loose stdout text that
        # would corrupt the caller's JSON parse).
        repo_root = str(Path(__file__).resolve().parents[1])
        problems = _install.preflight(cfg, cfg["claude_bin"], repo_root)
        if problems:
            return _emit({"ok": False, "watcher_running": False,
                          "error": "; ".join(problems)})
        # Suppress install.main's human-readable stdout so only our JSON is emitted.
        with _suppress_stdout():
            rc = _install.main([])
        paths = _install.plist_paths(cfg)
        running = paths["watch"].exists() and paths["sweep"].exists()
        return _emit({"ok": rc == 0 and running, "watcher_running": running})
    if args.cmd == "uninstall":
        with _suppress_stdout():
            _install.main(["--uninstall"])
        return _emit({"ok": True, "watcher_running": False})
    if args.cmd == "refile":
        cfg = _load()
        return _emit(_refile(cfg, args.path, args.course, args.date))
    if args.cmd == "discard":
        cfg = _load()
        return _emit(_discard(cfg, args.path))
    if args.cmd == "compile":
        cfg = _load()
        return _emit(_compile(cfg, args.course))
    if args.cmd == "build":
        cfg = _load()
        return _emit(_build(cfg, args.course))
    if args.cmd == "open-pdf":
        cfg = _load()
        return _emit(_open_pdf(cfg, args.course))
    if args.cmd == "list-notes":
        cfg = _load()
        return _emit(_list_notes(cfg, args.course))
    if args.cmd == "correct":
        cfg = _load()
        return _emit(_correct(cfg, args.course, args.note_key, args.instruction,
                              reread=args.reread))
    if args.cmd == "study-guide":
        cfg = _load()
        return _emit(_study_guide(cfg, args.course, kind="guide"))
    if args.cmd == "flashcards":
        cfg = _load()
        return _emit(_study_guide(cfg, args.course, kind="flashcards"))
    if args.cmd == "verify":
        cfg = _load()
        return _emit(_verify(cfg, args.course, args.note_key))
    if args.cmd == "caption-figures":
        cfg = _load()
        return _emit(_caption(cfg, args.course))
    return _emit({"ok": False, "error": f"unknown command: {args.cmd}"})


if __name__ == "__main__":
    sys.exit(main())
