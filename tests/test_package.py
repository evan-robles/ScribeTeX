import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_package_version_matches_manifest():
    # Assert against the source of truth (the plugin manifest), not a hardcoded
    # literal — a hardcoded value silently certifies drift and fails on a correct
    # bump. This keeps the Python package version and the plugin version in lockstep.
    import scribetex
    manifest = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())
    assert scribetex.__version__ == manifest["version"]
