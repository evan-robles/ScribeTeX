"""Render + install the two launchd agents (watch + sweep)."""
from __future__ import annotations
import argparse
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

from . import config as _config

LAUNCH_AGENTS = Path.home() / "Library" / "LaunchAgents"
WATCH_LABEL = "com.scribetex.watch"
SWEEP_LABEL = "com.scribetex.sweep"


def render_plist(label, program_args, *, watch_paths=None,
                 start_interval=None, log_file) -> str:
    if (watch_paths is None) == (start_interval is None):
        raise ValueError("exactly one of watch_paths / start_interval required")
    d = {
        "Label": label,
        "ProgramArguments": list(program_args),
        "RunAtLoad": start_interval is not None,
        "StandardOutPath": str(log_file),
        "StandardErrorPath": str(log_file),
    }
    if watch_paths is not None:
        d["WatchPaths"] = list(watch_paths)
    else:
        d["StartInterval"] = int(start_interval)
    return plistlib.dumps(d).decode()


def plist_paths(cfg) -> dict:
    return {
        "watch": LAUNCH_AGENTS / f"{WATCH_LABEL}.plist",
        "sweep": LAUNCH_AGENTS / f"{SWEEP_LABEL}.plist",
    }


_DEFAULT_PATH = "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"


def build_plists(cfg, python_bin, repo_root) -> dict:
    inbox = str(cfg["inbox_dir"])
    log = str(cfg["log_file"])
    # Inject repo_root on PYTHONPATH via an env-setting wrapper is awkward in
    # launchd; instead run with `-c` bootstrapping sys.path, or rely on the
    # module being importable from WorkingDirectory. We set EnvironmentVariables.
    def args(flag):
        return [python_bin, "-m", "automation.ingest", flag]

    watch = render_plist(WATCH_LABEL, args("--once"),
                         watch_paths=[inbox], log_file=log)
    sweep = render_plist(SWEEP_LABEL, args("--sweep"),
                         start_interval=int(cfg["sweep_seconds"]), log_file=log)
    # Add WorkingDirectory + PYTHONPATH so automation + scribetex import.
    # Also resolve the claude binary's directory so launchd's minimal PATH
    # still finds a bare `claude` (launchd processes do not inherit the
    # user's shell PATH, so without this ingest silently fails to invoke it).
    claude_path = shutil.which(cfg["claude_bin"]) or cfg["claude_bin"]
    resolved_dir = Path(claude_path).parent
    claude_dir = str(resolved_dir) if str(resolved_dir) not in ("", ".") else None
    watch = _inject_env(watch, repo_root, extra_path=claude_dir)
    sweep = _inject_env(sweep, repo_root, extra_path=claude_dir)
    paths = plist_paths(cfg)
    return {paths["watch"]: watch, paths["sweep"]: sweep}


def _inject_env(xml, repo_root, extra_path=None):
    data = plistlib.loads(xml.encode())
    data["WorkingDirectory"] = str(repo_root)
    path_parts = ([extra_path] if extra_path else []) + [_DEFAULT_PATH]
    data["EnvironmentVariables"] = {
        "PYTHONPATH": f"{repo_root}:{repo_root}/src",
        "PATH": ":".join(path_parts),
    }
    return plistlib.dumps(data).decode()


def preflight(cfg, claude_bin, repo_root) -> list:
    from .envpath import augmented_path
    problems = []
    if (shutil.which(claude_bin, path=augmented_path()) is None
            and not Path(claude_bin).exists()):
        problems.append(f"claude CLI not found: {claude_bin}")
    if not Path(cfg["inbox_dir"]).exists():
        problems.append(f"inbox dir does not exist: {cfg['inbox_dir']}")
    if not (Path(repo_root) / "automation").is_dir():
        problems.append(f"automation package not found under {repo_root}")
    if not (Path(repo_root) / "src" / "scribetex").is_dir():
        problems.append(f"scribetex package not found under {repo_root}/src")
    return problems


def _ensure_dirs(cfg):
    for d in (_config.done_dir(cfg), _config.needs_review_dir(cfg),
              Path(cfg["inbox_dir"]) / ".scribetex"):
        d.mkdir(parents=True, exist_ok=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Install ScribeTeX launchd agents.")
    ap.add_argument("--uninstall", action="store_true")
    ap.add_argument("--no-load", action="store_true",
                    help="write/remove plists but don't call launchctl")
    ap.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    args = ap.parse_args(argv)

    cfg = _config.load_config(
        toml_path=Path.home() / ".config" / "scribetex" / "automation.toml"
    )
    paths = plist_paths(cfg)

    if args.uninstall:
        for label, p in ((WATCH_LABEL, paths["watch"]), (SWEEP_LABEL, paths["sweep"])):
            if not args.no_load and p.exists():
                subprocess.run(["launchctl", "unload", str(p)],
                               capture_output=True)
            p.unlink(missing_ok=True)
            print(f"removed {p}")
        return 0

    problems = preflight(cfg, cfg["claude_bin"], args.repo_root)
    if problems:
        print("Cannot install — fix these first:")
        for pr in problems:
            print(f"  - {pr}")
        return 1

    _ensure_dirs(cfg)
    LAUNCH_AGENTS.mkdir(parents=True, exist_ok=True)
    for target, xml in build_plists(cfg, sys.executable, args.repo_root).items():
        target.write_text(xml)
        print(f"wrote {target}")
        if not args.no_load:
            subprocess.run(["launchctl", "unload", str(target)],
                           capture_output=True)
            subprocess.run(["launchctl", "load", str(target)],
                           capture_output=True)
    print("Installed. Drop a PDF into", cfg["inbox_dir"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
