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


def _refile(cfg, path, course, section, subsection, date, *, invoke_fn=None) -> dict:
    from scribetex.classify import parse_date
    from .prompt import build_refile_prompt, parse_result, allowed_tools_args, new_nonce
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
            # Pre-authorize the ScribeTeX MCP tools; headless `claude -p` cannot
            # prompt for permission, so without this the tool calls are blocked.
            proc = subprocess.run(
                [claude_bin, "-p", prompt_text, *allowed_tools_args()],
                capture_output=True, text=True, timeout=1800,
                env=augmented_env())
            return proc.stdout or ""
    try:
        prompt_text = build_refile_prompt(str(src), course, section, subsection,
                                          date_iso, nonce)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    stdout = invoke_fn(prompt_text, cfg["claude_bin"])
    result = parse_result(stdout, nonce)
    if result.get("status") != "filed":
        return {"ok": False, "error": result.get("reason", "re-file did not complete")}
    # Trust "filed" only if the worker actually wrote a target file — an
    # authenticated result whose target doesn't exist means nothing was written,
    # so keep the note in NeedsReview rather than moving it to Done (data loss).
    target = result.get("target")
    if not target or not Path(target).expanduser().exists():
        return {"ok": False,
                "error": f"worker reported filed but target is missing: {target!r}"}
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
    for a in ("--path", "--course", "--date"):
        rp.add_argument(a, required=True)
    # Section/subsection are optional: blank means the agent decides them from
    # the note content (course + date are the only user-required placement).
    rp.add_argument("--section", default="")
    rp.add_argument("--subsection", default="")
    dp = sub.add_parser("discard"); dp.add_argument("--path", required=True)
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
        return _emit(_refile(cfg, args.path, args.course, args.section,
                             args.subsection, args.date))
    if args.cmd == "discard":
        cfg = _load()
        return _emit(_discard(cfg, args.path))
    return _emit({"ok": False, "error": f"unknown command: {args.cmd}"})


if __name__ == "__main__":
    sys.exit(main())
