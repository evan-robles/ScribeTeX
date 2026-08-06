import datetime
import json
from pathlib import Path
from automation import appcli, config


def _cfg(tmp_path):
    return config.load_config(env={"SCRIBETEX_INBOX": str(tmp_path)}, toml_path=None)


def _touch(p):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x")


def test_status_keys_and_types(tmp_path):
    cfg = _cfg(tmp_path)
    st = appcli._status_dict(
        cfg,
        plist_paths_fn=lambda c: {"watch": tmp_path / "w.plist", "sweep": tmp_path / "s.plist"},
        which_fn=lambda b: "/usr/local/bin/claude",
        now_fn=lambda: datetime.datetime(2026, 8, 6),
    )
    for k in ("ok", "watcher_running", "inbox_dir", "filed_today", "filed_total",
              "needs_review_count", "claude_ok", "settle_seconds", "sweep_seconds"):
        assert k in st, f"missing key {k}"
    assert st["ok"] is True
    assert st["claude_ok"] is True
    assert st["watcher_running"] is False  # plists don't exist


def test_status_counts(tmp_path):
    cfg = _cfg(tmp_path)
    # 2 filed today, 1 filed on another day -> total 3
    _touch(tmp_path / "Done" / "2026-08-06" / "a.pdf")
    _touch(tmp_path / "Done" / "2026-08-06" / "b.pdf")
    _touch(tmp_path / "Done" / "2026-08-01" / "c.pdf")
    # 1 needs-review note + its sidecar (sidecar must NOT be counted)
    _touch(tmp_path / "NeedsReview" / "d.pdf")
    _touch(tmp_path / "NeedsReview" / "d.pdf.review.txt")
    st = appcli._status_dict(
        cfg,
        plist_paths_fn=lambda c: {"watch": tmp_path / "w", "sweep": tmp_path / "s"},
        which_fn=lambda b: None,
        now_fn=lambda: datetime.datetime(2026, 8, 6),
    )
    assert st["filed_today"] == 2
    assert st["filed_total"] == 3
    assert st["needs_review_count"] == 1
    assert st["claude_ok"] is False


def test_status_needs_review_count_excludes_json_sidecar(tmp_path):
    cfg = _cfg(tmp_path)
    # 1 needs-review note + its .review.json sidecar -> count must be 1, not 2
    _touch(tmp_path / "NeedsReview" / "a.pdf")
    (tmp_path / "NeedsReview" / "a.pdf.review.json").write_text(
        json.dumps({"reason": "no date", "kind": "ambiguous",
                    "guess": {"course": None, "section": None,
                              "subsection": None, "date": None}})
    )
    st = appcli._status_dict(
        cfg,
        plist_paths_fn=lambda c: {"watch": tmp_path / "w", "sweep": tmp_path / "s"},
        which_fn=lambda b: None,
        now_fn=lambda: datetime.datetime(2026, 8, 6),
    )
    assert st["needs_review_count"] == 1


def test_status_watcher_running_when_both_plists_exist(tmp_path):
    cfg = _cfg(tmp_path)
    w = tmp_path / "w.plist"; s = tmp_path / "s.plist"
    w.write_text("x"); s.write_text("x")
    st = appcli._status_dict(
        cfg, plist_paths_fn=lambda c: {"watch": w, "sweep": s},
        which_fn=lambda b: "claude", now_fn=lambda: datetime.datetime(2026, 8, 6),
    )
    assert st["watcher_running"] is True


def test_status_subcommand_emits_json(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SCRIBETEX_INBOX", str(tmp_path))
    monkeypatch.setattr(appcli, "_config_toml_path", lambda: tmp_path / "none.toml")
    rc = appcli.main(["status"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True
    assert "watcher_running" in out
