# tests/test_run_self_locating.py
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SKILLS = ["process-note", "new-course", "list-courses", "compile-course"]


def _run_help(skill: str):
    script = REPO / "skills" / skill / "scripts" / "run.py"
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    return subprocess.run(
        [sys.executable, str(script), "--help"],
        capture_output=True, text=True, env=env, cwd=str(Path.home()),
    )


def test_every_run_imports_without_pythonpath():
    for skill in SKILLS:
        r = _run_help(skill)
        # --help exits 0 after argparse prints usage; a broken import exits 1
        # with ModuleNotFoundError on stderr.
        assert "ModuleNotFoundError" not in r.stderr, f"{skill}: {r.stderr}"
        assert r.returncode == 0, f"{skill} rc={r.returncode}: {r.stderr}"
