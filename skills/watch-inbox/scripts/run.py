#!/usr/bin/env python3
"""Manage ScribeTeX auto-ingest: install/uninstall launchd agents, status, sweep.

Self-locating: adds the repo root (for `automation`) and repo/src (for
`scribetex`) to sys.path, so no external PYTHONPATH is needed.
"""
from __future__ import annotations
import argparse
import pathlib
import sys

_ROOT = pathlib.Path(__file__).resolve().parents[3]
for _p in (_ROOT, _ROOT / "src"):
    if _p.is_dir() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from automation import config as _config       # noqa: E402
from automation import install as _install     # noqa: E402
from automation import ingest as _ingest       # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="ScribeTeX auto-ingest manager.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("install")
    sub.add_parser("uninstall")
    sub.add_parser("status")
    sub.add_parser("sweep")
    args = ap.parse_args()

    if args.cmd == "install":
        return _install.main([])
    if args.cmd == "uninstall":
        return _install.main(["--uninstall"])
    if args.cmd == "sweep":
        cfg = _config.load_config(
            toml_path=pathlib.Path.home() / ".config" / "scribetex" / "automation.toml")
        res = _ingest.process_inbox(cfg)
        print(f"processed {len(res)} file(s): "
              + ", ".join(f"{r['file']}={r['outcome']}" for r in res))
        return 0
    # status
    cfg = _config.load_config(
        toml_path=pathlib.Path.home() / ".config" / "scribetex" / "automation.toml")
    paths = _install.plist_paths(cfg)
    print(f"inbox_dir       : {cfg['inbox_dir']}")
    print(f"sweep_seconds   : {cfg['sweep_seconds']}")
    print(f"settle_seconds  : {cfg['settle_seconds']}")
    print(f"claude_bin      : {cfg['claude_bin']}")
    print(f"watch agent     : {'installed' if paths['watch'].exists() else 'not installed'}")
    print(f"sweep agent     : {'installed' if paths['sweep'].exists() else 'not installed'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
