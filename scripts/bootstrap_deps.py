#!/usr/bin/env python3
"""Ensure the scribe-tex MCP server's Python dependencies are importable.

Runs from the plugin's SessionStart hook. Idempotent: if fastmcp, PyMuPDF
(``fitz``), and python-dateutil already import, it does nothing but print a
one-line OK. If any are missing it pip-installs them quietly into the current
Python, so a marketplace install works turnkey without a manual pip step.

Stdlib only (no third-party imports at module load) so it can run before the
deps exist. Never raises: a bootstrap failure must not block the session.
"""
from __future__ import annotations

import importlib
import subprocess
import sys

# import name -> pip requirement
REQUIRED = {
    "fastmcp": "fastmcp>=2.0",
    "fitz": "pymupdf>=1.24",
    "dateutil": "python-dateutil>=2.9",
}


def _missing() -> list[str]:
    missing = []
    for mod, req in REQUIRED.items():
        try:
            importlib.import_module(mod)
        except Exception:
            missing.append(req)
    return missing


def main() -> int:
    missing = _missing()
    if not missing:
        print("[scribe-tex] dependencies present.")
        return 0
    print(f"[scribe-tex] installing missing dependencies: {', '.join(missing)}")
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet", *missing],
            check=True,
        )
    except Exception as e:  # never block the session
        print(f"[scribe-tex] could not auto-install ({e}). "
              f"Run: {sys.executable} -m pip install {' '.join(missing)}")
        return 0
    still = _missing()
    if still:
        print(f"[scribe-tex] still missing after install: {', '.join(still)} "
              f"(the MCP server may not start until these are installed).")
    else:
        print("[scribe-tex] dependencies installed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
