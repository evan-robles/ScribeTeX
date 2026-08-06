import os, subprocess, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RUN = REPO / "skills" / "watch-inbox" / "scripts" / "run.py"


def test_skill_md_exists_and_has_frontmatter():
    md = (REPO / "skills" / "watch-inbox" / "SKILL.md").read_text()
    assert md.startswith("---")
    assert "name: watch-inbox" in md
    assert "category:" in md


def test_run_status_imports_without_pythonpath():
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    r = subprocess.run([sys.executable, str(RUN), "status"],
                       capture_output=True, text=True, env=env,
                       cwd=str(Path.home()))
    assert "ModuleNotFoundError" not in r.stderr, r.stderr
    assert r.returncode == 0, r.stderr
