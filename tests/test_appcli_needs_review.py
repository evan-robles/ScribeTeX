# tests/test_appcli_needs_review.py
from pathlib import Path
from automation import appcli, config


def _cfg(tmp_path):
    return config.load_config(env={"SCRIBETEX_INBOX": str(tmp_path)}, toml_path=None)


def _mk(p, text=None):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x")


def test_needs_review_parses_sidecars(tmp_path):
    cfg = _cfg(tmp_path)
    nr = tmp_path / "NeedsReview"
    nr.mkdir(parents=True)
    (nr / "amb.pdf").write_bytes(b"x")
    (nr / "amb.pdf.review.txt").write_text("Needs review: course unclear\n")
    (nr / "err.pdf").write_bytes(b"x")
    (nr / "err.pdf.error.txt").write_text("failed: boom\n")
    (nr / "bare.pdf").write_bytes(b"x")  # no sidecar

    items = {i["name"]: i for i in appcli._needs_review_items(cfg)}
    assert set(items) == {"amb.pdf", "err.pdf", "bare.pdf"}
    assert items["amb.pdf"]["kind"] == "ambiguous"
    assert "course unclear" in items["amb.pdf"]["reason"]
    assert items["err.pdf"]["kind"] == "error"
    assert "boom" in items["err.pdf"]["reason"]
    assert items["bare.pdf"]["kind"] == "unknown"
    assert items["bare.pdf"]["reason"] is None


def test_needs_review_empty_when_no_dir(tmp_path):
    cfg = _cfg(tmp_path)
    assert appcli._needs_review_items(cfg) == []


def test_needs_review_subcommand_json(tmp_path, monkeypatch, capsys):
    import json
    monkeypatch.setenv("SCRIBETEX_INBOX", str(tmp_path))
    monkeypatch.setattr(appcli, "_config_toml_path", lambda: tmp_path / "none.toml")
    (tmp_path / "NeedsReview").mkdir(parents=True)
    (tmp_path / "NeedsReview" / "x.pdf").write_bytes(b"x")
    rc = appcli.main(["needs-review"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True
    assert out["items"][0]["name"] == "x.pdf"
