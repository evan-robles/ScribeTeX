import json
from pathlib import Path
from automation import appcli, config


def _cfg(tmp_path):
    return config.load_config(env={"SCRIBETEX_INBOX": str(tmp_path)}, toml_path=None)


def test_reads_json_sidecar_guesses(tmp_path):
    cfg = _cfg(tmp_path)
    nr = tmp_path / "NeedsReview"; nr.mkdir(parents=True)
    (nr / "a.pdf").write_bytes(b"x")
    (nr / "a.pdf.review.json").write_text(json.dumps({
        "reason": "no date", "kind": "ambiguous",
        "guess": {"course": "BIOS 20200", "section": "Receptors",
                  "subsection": "Receptors", "date": None}}))
    items = {i["name"]: i for i in appcli._needs_review_items(cfg)}
    it = items["a.pdf"]
    assert it["kind"] == "ambiguous"
    assert it["reason"] == "no date"
    assert it["course"] == "BIOS 20200"
    assert it["section"] == "Receptors"
    assert it["date"] is None


def test_legacy_txt_sidecar_fallback(tmp_path):
    cfg = _cfg(tmp_path)
    nr = tmp_path / "NeedsReview"; nr.mkdir(parents=True)
    (nr / "old.pdf").write_bytes(b"x")
    (nr / "old.pdf.review.txt").write_text("Needs review: course unclear")
    it = {i["name"]: i for i in appcli._needs_review_items(cfg)}["old.pdf"]
    assert it["kind"] == "ambiguous"
    assert "course unclear" in it["reason"]
    assert it["course"] is None and it["date"] is None
