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

# Cap on consecutive error outcomes for the same file identity before it is
# dead-lettered to NeedsReview/ instead of being retried forever.
MAX_ERROR_ATTEMPTS = 3


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


def _as_str(s):
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def notify(title, message, run_fn=None) -> None:
    run_fn = run_fn or subprocess.run
    try:
        script = f"display notification {_as_str(message)} with title {_as_str(title)}"
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


def give_up_file(note_path, result, cfg) -> None:
    """Dead-letter a persistently-erroring file to NeedsReview/ with a sidecar."""
    note = Path(note_path)
    nr = _config.needs_review_dir(cfg)
    nr.mkdir(parents=True, exist_ok=True)
    shutil.move(str(note), str(nr / note.name))
    (nr / f"{note.name}.error.txt").write_text(
        f"Gave up after repeated errors: {result.get('reason', 'unspecified')}\n"
    )


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
        ef = _config.error_file(cfg)
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
                state.clear_error_count(ef, key)
                _notify_outcome(notify_fn, note, result, outcome)
            else:  # error
                attempts = state.bump_error_count(ef, key)
                if attempts >= MAX_ERROR_ATTEMPTS:
                    give_up_file(note, result, cfg)
                    state.mark_seen(sf, key)
                    outcome = "gave_up"
                    _notify_outcome(notify_fn, note, result, outcome)
                elif attempts == 1:
                    # Only notify on the first error attempt; suppress the
                    # middle retries so a persistently-failing note doesn't
                    # spam a notification on every sweep/watch trigger.
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
    elif outcome == "gave_up":
        notify_fn("ScribeTeX gave up",
                  f"{note.name}: repeated errors, moved to NeedsReview "
                  f"({result.get('reason', 'error')})")
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
