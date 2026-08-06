"""Configuration: resolve the notes root directory."""
import os
from pathlib import Path

DEFAULT_NOTES_ROOT = Path.home() / "Desktop" / "College" / "Notes"
ENV_VAR = "SCRIBETEX_NOTES_ROOT"


def notes_root() -> Path:
    """Return the parent folder that holds one repo per course.

    Reads env var SCRIBETEX_NOTES_ROOT (with ~ expansion) if set, else the
    default ~/Desktop/College/Notes. Never creates the directory.
    """
    override = os.environ.get(ENV_VAR)
    if override:
        return Path(override).expanduser()
    return DEFAULT_NOTES_ROOT
