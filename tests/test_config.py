from pathlib import Path
from scribe_tex.config import notes_root


def test_default_notes_root(monkeypatch):
    monkeypatch.delenv("SCRIBE_TEX_NOTES_ROOT", raising=False)
    assert notes_root() == (Path.home() / "Desktop" / "College" / "Notes")


def test_env_override_is_expanded(monkeypatch):
    monkeypatch.setenv("SCRIBE_TEX_NOTES_ROOT", "~/somewhere/notes")
    assert notes_root() == (Path.home() / "somewhere" / "notes")


def test_notes_root_does_not_create_dir(monkeypatch, tmp_path):
    target = tmp_path / "made_up"
    monkeypatch.setenv("SCRIBE_TEX_NOTES_ROOT", str(target))
    _ = notes_root()
    assert not target.exists()
