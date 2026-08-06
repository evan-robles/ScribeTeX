# tests/test_automation_config.py
from pathlib import Path
import pytest
from automation import config


def test_defaults_when_no_env_no_toml():
    cfg = config.load_config(env={}, toml_path=None)
    assert cfg["inbox_dir"] == (Path.home() / "ScribeTeX-Inbox")
    assert cfg["sweep_seconds"] == 600
    assert cfg["settle_seconds"] == 4
    assert cfg["claude_bin"] == "claude"


def test_env_overrides(tmp_path):
    env = {
        "SCRIBETEX_INBOX": str(tmp_path / "in"),
        "SCRIBETEX_SWEEP_SECONDS": "120",
        "SCRIBETEX_SETTLE_SECONDS": "2",
        "SCRIBETEX_CLAUDE_BIN": "/usr/local/bin/claude",
    }
    cfg = config.load_config(env=env, toml_path=None)
    assert cfg["inbox_dir"] == (tmp_path / "in")
    assert cfg["sweep_seconds"] == 120
    assert cfg["settle_seconds"] == 2
    assert cfg["claude_bin"] == "/usr/local/bin/claude"


def test_toml_used_and_env_wins(tmp_path):
    toml = tmp_path / "automation.toml"
    toml.write_text('inbox_dir = "%s"\nsweep_seconds = 300\n' % (tmp_path / "t"))
    cfg = config.load_config(env={"SCRIBETEX_SWEEP_SECONDS": "45"}, toml_path=toml)
    assert cfg["inbox_dir"] == (tmp_path / "t")   # from toml
    assert cfg["sweep_seconds"] == 45             # env overrides toml


def test_missing_toml_is_ok(tmp_path):
    cfg = config.load_config(env={}, toml_path=tmp_path / "nope.toml")
    assert cfg["sweep_seconds"] == 600


def test_malformed_toml_raises(tmp_path):
    bad = tmp_path / "bad.toml"
    bad.write_text("this is = = not toml")
    with pytest.raises(ValueError, match="bad.toml"):
        config.load_config(env={}, toml_path=bad)


def test_derived_paths(tmp_path):
    cfg = config.load_config(env={"SCRIBETEX_INBOX": str(tmp_path)}, toml_path=None)
    assert config.done_dir(cfg) == tmp_path / "Done"
    assert config.needs_review_dir(cfg) == tmp_path / "NeedsReview"
    assert config.state_file(cfg) == tmp_path / ".scribetex" / "seen.json"
    assert config.lock_file(cfg) == tmp_path / ".scribetex" / "ingest.lock"
