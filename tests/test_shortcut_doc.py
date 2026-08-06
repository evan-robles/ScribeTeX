from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_shortcut_doc_exists_and_covers_steps():
    doc = (ROOT / "docs" / "shortcut-setup.md").read_text().lower()
    assert "share sheet" in doc
    assert "save file" in doc
    assert "inbox" in doc
    assert "goodnotes" in doc


def test_readme_links_shortcut_and_app():
    readme = (ROOT / "README.md").read_text().lower()
    assert "shortcut" in readme
    assert "menu-bar" in readme or "menu bar" in readme
