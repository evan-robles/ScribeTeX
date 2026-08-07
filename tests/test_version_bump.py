import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def test_all_manifests_are_1_1_0():
    pj = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())
    mp = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text())
    assert pj["version"] == "1.1.0"
    assert mp["plugins"][0]["version"] == "1.1.0"
    pyproject = (ROOT / "pyproject.toml").read_text()
    assert re.search(r'^version\s*=\s*"1\.1\.0"', pyproject, re.M)
    # The Python package version must not drift from the manifests.
    init = (ROOT / "src" / "scribetex" / "__init__.py").read_text()
    assert re.search(r'__version__\s*=\s*"1\.1\.0"', init)
