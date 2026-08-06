import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def test_all_manifests_are_0_2_0():
    pj = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())
    mp = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text())
    assert pj["version"] == "0.2.0"
    assert mp["plugins"][0]["version"] == "0.2.0"
    pyproject = (ROOT / "pyproject.toml").read_text()
    assert re.search(r'^version\s*=\s*"0\.2\.0"', pyproject, re.M)
