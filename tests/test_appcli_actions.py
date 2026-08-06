import json
from pathlib import Path
from automation import appcli, config


def _cfg(tmp_path):
    return config.load_config(env={"SCRIBETEX_INBOX": str(tmp_path)}, toml_path=None)


def test_process_copies_into_inbox_and_runs(tmp_path):
    cfg = _cfg(tmp_path)
    (tmp_path).mkdir(parents=True, exist_ok=True)
    src = tmp_path / "outside" / "note.pdf"
    src.parent.mkdir(parents=True)
    src.write_bytes(b"%PDF-1.4")
    captured = {}
    def fake_process(c):
        captured["ran"] = True
        return [{"file": "note.pdf", "outcome": "filed", "result": {"status": "filed"}}]
    res = appcli._process_path(cfg, str(src), process_fn=fake_process)
    assert res["ok"] is True
    assert captured.get("ran") is True
    assert (tmp_path / "note.pdf").exists()   # copied into inbox
    assert res["processed"][0]["outcome"] == "filed"


def test_process_missing_file(tmp_path):
    cfg = _cfg(tmp_path)
    res = appcli._process_path(cfg, str(tmp_path / "nope.pdf"), process_fn=lambda c: [])
    assert res["ok"] is False
    assert "file not found" in res["error"]


def test_sweep_subcommand(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SCRIBETEX_INBOX", str(tmp_path))
    monkeypatch.setattr(appcli, "_config_toml_path", lambda: tmp_path / "none.toml")
    monkeypatch.setattr(appcli._ingest, "process_inbox", lambda c: [])
    rc = appcli.main(["sweep"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True


def test_install_subcommand_wraps_install_main(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SCRIBETEX_INBOX", str(tmp_path))
    monkeypatch.setattr(appcli, "_config_toml_path", lambda: tmp_path / "none.toml")
    monkeypatch.setattr(appcli._install, "main", lambda argv: 0)
    monkeypatch.setattr(appcli._install, "plist_paths",
                        lambda c: {"watch": tmp_path / "w", "sweep": tmp_path / "s"})
    rc = appcli.main(["install"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert "watcher_running" in out
