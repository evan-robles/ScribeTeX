import datetime
from automation import appcli, config

STATUS_KEYS = {
    "ok", "watcher_running", "inbox_dir", "filed_today", "filed_total",
    "needs_review_count", "claude_ok", "settle_seconds", "sweep_seconds",
}
NEEDS_REVIEW_ITEM_KEYS = {"name", "path", "reason", "kind",
                          "course", "section", "subsection", "date"}


def test_status_contract(tmp_path):
    cfg = config.load_config(env={"SCRIBETEX_INBOX": str(tmp_path)}, toml_path=None)
    st = appcli._status_dict(
        cfg, plist_paths_fn=lambda c: {"watch": tmp_path / "w", "sweep": tmp_path / "s"},
        which_fn=lambda b: None, now_fn=lambda: datetime.datetime(2026, 8, 6),
    )
    assert set(st.keys()) == STATUS_KEYS


def test_needs_review_item_contract(tmp_path):
    cfg = config.load_config(env={"SCRIBETEX_INBOX": str(tmp_path)}, toml_path=None)
    nr = tmp_path / "NeedsReview"; nr.mkdir(parents=True)
    (nr / "x.pdf").write_bytes(b"x")
    (nr / "x.pdf.review.txt").write_text("r")
    items = appcli._needs_review_items(cfg)
    assert items and set(items[0].keys()) == NEEDS_REVIEW_ITEM_KEYS
