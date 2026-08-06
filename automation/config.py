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
