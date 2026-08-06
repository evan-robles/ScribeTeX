import json
from pathlib import Path
from automation import ingest, config


def _cfg(tmp_path):
    return config.load_config(env={"SCRIBETEX_INBOX": str(tmp_path)}, toml_path=None)


def _pdf(p):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"%PDF-1.4")
    return p


def test_route_ambiguous_writes_json_sidecar(tmp_path):
    cfg = _cfg(tmp_path)
    note = _pdf(tmp_path / "note.pdf")
    result = {"status": "ambiguous", "reason": "no date",
              "course": "BIOS 20200", "section": "Receptors",
              "subsection": "Receptors", "date": None}
    outcome = ingest.route_file(str(note), result, cfg)
    assert outcome == "ambiguous"
    nr = tmp_path / "NeedsReview"
    assert (nr / "note.pdf").exists()
    sidecar = nr / "note.pdf.review.json"
    assert sidecar.exists()
    data = json.loads(sidecar.read_text())
    assert data["reason"] == "no date"
    assert data["kind"] == "ambiguous"
    assert data["guess"]["course"] == "BIOS 20200"
    assert data["guess"]["date"] is None
    # legacy .txt no longer written
    assert not (nr / "note.pdf.review.txt").exists()


def test_give_up_writes_error_json_sidecar(tmp_path):
    cfg = _cfg(tmp_path)
    note = _pdf(tmp_path / "bad.pdf")
    result = {"status": "error", "reason": "boom"}
    ingest.give_up_file(str(note), result, cfg)
    nr = tmp_path / "NeedsReview"
    sidecar = nr / "bad.pdf.review.json"
    assert sidecar.exists()
    data = json.loads(sidecar.read_text())
    assert data["kind"] == "error"
    assert data["reason"] == "boom"
    assert data["guess"]["course"] is None


def test_build_prompt_ambiguous_contract_documents_guesses():
    from automation.prompt import build_prompt
    p = build_prompt("/x/note.pdf")
    # ambiguous result now carries best-guess fields for prefill
    assert '"status":"ambiguous"' in p
    assert "course" in p and "section" in p and "subsection" in p and "date" in p
