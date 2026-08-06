import json
import tomllib
from pathlib import Path
from automation import appcli


def test_write_inbox_creates_config_and_dirs(tmp_path):
    toml = tmp_path / "cfg" / "automation.toml"
    inbox = tmp_path / "MyInbox"
    res = appcli._write_inbox_config(str(inbox), toml)
    assert res["ok"] is True
    assert res["inbox_dir"] == str(inbox)
    # config written + parseable
    data = tomllib.loads(toml.read_text())
    assert data["inbox_dir"] == str(inbox)
    # dirs created
    assert (inbox / "Done").is_dir()
    assert (inbox / "NeedsReview").is_dir()
    assert (inbox / ".scribetex").is_dir()


def test_write_inbox_preserves_other_keys(tmp_path):
    toml = tmp_path / "automation.toml"
    toml.write_text('sweep_seconds = 300\ninbox_dir = "/old"\n')
    appcli._write_inbox_config(str(tmp_path / "new"), toml)
    data = tomllib.loads(toml.read_text())
    assert data["inbox_dir"] == str(tmp_path / "new")
    assert data["sweep_seconds"] == 300  # preserved


def test_set_inbox_subcommand_json(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(appcli, "_config_toml_path", lambda: tmp_path / "automation.toml")
    rc = appcli.main(["set-inbox", "--path", str(tmp_path / "Inbox")])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True
    assert out["inbox_dir"] == str(tmp_path / "Inbox")
