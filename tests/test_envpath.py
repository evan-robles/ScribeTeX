import os
from pathlib import Path
from automation import envpath


def test_prepends_local_bin():
    result = envpath.augmented_path("/usr/bin:/bin")
    parts = result.split(os.pathsep)
    assert str(Path.home() / ".local" / "bin") in parts
    # original entries preserved
    assert "/usr/bin" in parts and "/bin" in parts


def test_no_duplicates_when_already_present():
    homebrew = "/opt/homebrew/bin"
    result = envpath.augmented_path(f"{homebrew}:/usr/bin")
    parts = result.split(os.pathsep)
    assert parts.count(homebrew) == 1


def test_extra_bins_come_before_base():
    result = envpath.augmented_path("/usr/bin")
    parts = result.split(os.pathsep)
    assert parts.index(str(Path.home() / ".local" / "bin")) < parts.index("/usr/bin")


def test_augmented_env_sets_path(monkeypatch):
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    env = envpath.augmented_env()
    assert str(Path.home() / ".local" / "bin") in env["PATH"].split(os.pathsep)


def test_none_base_uses_minimal_fallback(monkeypatch):
    monkeypatch.delenv("PATH", raising=False)
    result = envpath.augmented_path(None)
    parts = result.split(os.pathsep)
    assert "/usr/bin" in parts  # minimal fallback present
    assert str(Path.home() / ".local" / "bin") in parts
