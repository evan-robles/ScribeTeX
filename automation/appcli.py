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
    return _emit({"ok": False, "error": f"unknown command: {args.cmd}"})


if __name__ == "__main__":
    sys.exit(main())
