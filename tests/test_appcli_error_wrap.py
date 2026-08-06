import json
from automation import appcli


def test_status_with_bad_config_emits_error_json(tmp_path, monkeypatch, capsys):
    # A config that fails to load (bad int) must surface as {"ok": false, ...}
    # JSON with exit 0, not an uncaught traceback / nonzero exit.
    monkeypatch.setenv("SCRIBETEX_SWEEP_SECONDS", "not-a-number")
    monkeypatch.setattr(appcli, "_config_toml_path", lambda: tmp_path / "none.toml")
    rc = appcli.main(["status"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False
    assert "error" in out
    assert "SCRIBETEX_SWEEP_SECONDS" in out["error"]


def test_good_config_status_still_ok(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SCRIBETEX_INBOX", str(tmp_path))
    monkeypatch.setattr(appcli, "_config_toml_path", lambda: tmp_path / "none.toml")
    rc = appcli.main(["status"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True
