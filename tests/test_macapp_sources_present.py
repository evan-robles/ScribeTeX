# tests/test_macapp_sources_present.py
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "macapp"


def test_swift_sources_exist():
    for f in ("ScribeTeX/ScribeTeXApp.swift", "ScribeTeX/Bridge.swift",
              "ScribeTeX/Models.swift", "ScribeTeX/MenuContent.swift", "README.md"):
        assert (APP / f).exists(), f"missing {f}"


def test_bridge_references_appcli_commands():
    bridge = (APP / "ScribeTeX" / "Bridge.swift").read_text()
    # The bridge must invoke the real appcli module + the frozen command names.
    assert "automation.appcli" in bridge
    for cmd in ("status", "needs-review", "set-inbox", "process", "install", "uninstall"):
        assert cmd in bridge, f"bridge missing command {cmd}"


def test_readme_covers_unsigned_gatekeeper():
    readme = (APP / "README.md").read_text().lower()
    assert "right-click" in readme or "right click" in readme
    assert "open" in readme
    assert "claude code" in readme  # prerequisite documented
