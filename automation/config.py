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
    # Opt-in: after a note is filed, compile its course (plain compile, no LLM
    # auto-fix) so a broken transcription surfaces immediately. Off by default —
    # compilation needs a TeX toolchain and adds time to each note.
    "auto_compile": False,
}

_ENV = {
    "inbox_dir": "SCRIBETEX_INBOX",
    "sweep_seconds": "SCRIBETEX_SWEEP_SECONDS",
    "settle_seconds": "SCRIBETEX_SETTLE_SECONDS",
    "claude_bin": "SCRIBETEX_CLAUDE_BIN",
    "log_file": "SCRIBETEX_AUTOMATION_LOG",
    "auto_compile": "SCRIBETEX_AUTO_COMPILE",
}
_INT_KEYS = {"sweep_seconds", "settle_seconds"}
_BOOL_KEYS = {"auto_compile"}
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
        try:
            cfg[k] = int(cfg[k])
        except (TypeError, ValueError):
            raise ValueError(
                f"{_ENV[k]} must be an integer number of seconds; "
                f"got {cfg[k]!r} which is not a valid integer"
            )
    for k in _BOOL_KEYS:
        v = cfg[k]
        if isinstance(v, str):
            cfg[k] = v.strip().lower() in ("1", "true", "yes", "on")
        else:
            cfg[k] = bool(v)
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


def error_file(cfg) -> Path:
    return _sub(cfg) / "errors.json"


def lock_file(cfg) -> Path:
    return _sub(cfg) / "ingest.lock"
