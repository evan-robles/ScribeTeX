"""PATH augmentation so GUI-launched processes can find user-installed tools.

A macOS app launched from Finder/Xcode inherits a minimal PATH (typically
``/usr/bin:/bin:/usr/sbin:/sbin``) that excludes the locations where CLIs like
``claude`` are commonly installed (``~/.local/bin``, Homebrew). Both the
``claude`` detection (shutil.which) and the actual ``claude`` invocation must
see those directories, or the app reports "Claude Code not detected" and filing
fails even though it works fine from a terminal.
"""
from __future__ import annotations

import os
from pathlib import Path

# Common user/tool bin locations to add if missing, in priority order.
_EXTRA_BINS = [
    str(Path.home() / ".local" / "bin"),
    str(Path.home() / "bin"),
    "/opt/homebrew/bin",
    "/usr/local/bin",
]


def augmented_path(base: str | None = None) -> str:
    """Return a PATH string with the common user/tool bin dirs prepended.

    Existing entries are preserved and not duplicated. ``base`` defaults to the
    current process ``PATH`` (or the minimal system PATH if unset).
    """
    if base is None:
        base = os.environ.get("PATH", "/usr/bin:/bin:/usr/sbin:/sbin")
    existing = [p for p in base.split(os.pathsep) if p]
    seen = set(existing)
    prefix = [p for p in _EXTRA_BINS if p not in seen]
    return os.pathsep.join(prefix + existing)


def augmented_env(env: dict | None = None) -> dict:
    """Return a copy of ``env`` (default os.environ) with an augmented PATH."""
    env = dict(os.environ if env is None else env)
    env["PATH"] = augmented_path(env.get("PATH"))
    return env
