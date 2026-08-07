import json
import re
import pytest
from automation import appcli, config, prompt


def _cfg(tmp_path, monkeypatch, **extra):
    monkeypatch.setenv("SCRIBETEX_NOTES_ROOT", str(tmp_path / "notes"))
    env = {"SCRIBETEX_INBOX": str(tmp_path)}
    env.update(extra)
    return config.load_config(env=env, toml_path=None)


def _course(tmp_path, name="Bio"):
    from scribetex.classify import course_slug
    from scribetex.placement import ENTRIES_START, ENTRIES_END, note_block
    d = tmp_path / "notes" / course_slug(name)
    d.mkdir(parents=True, exist_ok=True)
    body = note_block("\\section{Receptors}\ntext", "2026-08-06", "bio.pdf")
    (d / "main.tex").write_text(f"HEAD\n{ENTRIES_START}\n{body}{ENTRIES_END}\nTAIL\n")
    return d / "main.tex"


def _worker(status_json: dict):
    def invoke(prompt_text, claude_bin):
        prefix = re.search(r"SCRIBETEX_RESULT_[0-9a-f]+:", prompt_text).group(0)
        return f"{prefix} {json.dumps(status_json)}"
    return invoke


# --- prompt shape ---

def test_studyguide_prompt_guide_and_flashcards():
    g = prompt.build_studyguide_prompt("Bio", "guide")
    assert "read_course" in g and "write_study_aid" in g and "Study Guide" in g
    f = prompt.build_studyguide_prompt("Bio", "flashcards")
    assert "flashcards" in f.lower() and "tab-separated" in f.lower()


def test_verify_prompt_flags_with_uncertain():
    p = prompt.build_verify_prompt("Bio")
    assert "\\uncertain" in p and "patch_note_region" in p
    assert "FLAG" in p or "flag" in p


def test_caption_prompt_covers_captions_and_dupes():
    p = prompt.build_caption_prompt("Bio")
    assert "caption" in p.lower() and "duplicate" in p.lower()


# --- appcli drivers ---

def test_study_guide_runs_worker(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    _course(tmp_path, "Bio")
    r = appcli._study_guide(cfg, "Bio", kind="guide", reveal=False,
                            invoke_fn=_worker({"status": "study_aid", "course": "Bio",
                                               "kind": "guide", "path": "/x/main.tex"}))
    assert r["ok"] is True and r["result"]["kind"] == "guide"
    # The written path is surfaced at the top level so the app can reveal it.
    assert r["path"] == "/x/main.tex"


def test_verify_runs_worker(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    _course(tmp_path, "Bio")
    r = appcli._verify(cfg, "Bio",
                       invoke_fn=_worker({"status": "verified", "course": "Bio",
                                          "flagged": 2, "notes_flagged": ["2026-08-06:bio-pdf"]}))
    assert r["ok"] is True and r["result"]["flagged"] == 2


def test_caption_runs_worker(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    _course(tmp_path, "Bio")
    r = appcli._caption(cfg, "Bio",
                        invoke_fn=_worker({"status": "captioned", "course": "Bio",
                                           "captioned": 3, "duplicates": []}))
    assert r["ok"] is True and r["result"]["captioned"] == 3


def test_course_worker_reports_failure(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    _course(tmp_path, "Bio")
    r = appcli._verify(cfg, "Bio", invoke_fn=lambda *a, **k: "")
    assert r["ok"] is False


# --- write_study_aid tool ---

def test_write_study_aid_flashcards(tmp_path, monkeypatch):
    monkeypatch.setenv("SCRIBETEX_NOTES_ROOT", str(tmp_path / "notes"))
    _course(tmp_path, "Bio")
    from scribetex import server
    r = server._write_study_aid("Bio", "flashcards", "Q1\tA1\nQ2\tA2\n")
    assert r["written"] is True and r["path"].endswith("flashcards.tsv")
    from scribetex.classify import course_slug
    assert (tmp_path / "notes" / course_slug("Bio") / "flashcards.tsv").read_text().startswith("Q1")


def test_write_study_aid_guide_is_regenerable(tmp_path, monkeypatch):
    monkeypatch.setenv("SCRIBETEX_NOTES_ROOT", str(tmp_path / "notes"))
    main = _course(tmp_path, "Bio")
    from scribetex import server
    server._write_study_aid("Bio", "guide", "\\section{Study Guide}\nv1")
    server._write_study_aid("Bio", "guide", "\\section{Study Guide}\nv2")
    text = main.read_text()
    assert "v2" in text and "v1" not in text  # replaced, not duplicated


# --- read_course ---

def test_read_course_returns_body_and_notes(tmp_path, monkeypatch):
    monkeypatch.setenv("SCRIBETEX_NOTES_ROOT", str(tmp_path / "notes"))
    _course(tmp_path, "Bio")
    from scribetex import server
    r = server._read_course("Bio")
    assert r["ok"] is True
    assert r["notes"][0]["key"] == "2026-08-06:bio-pdf"
    assert "Receptors" in r["body"]


# --- output_dir delivery (C7) ---

def test_deliver_pdf_copies_to_output_dir(tmp_path, monkeypatch):
    out = tmp_path / "pdfs"
    cfg = _cfg(tmp_path, monkeypatch, SCRIBETEX_OUTPUT_DIR=str(out))
    pdf = tmp_path / "main.pdf"; pdf.write_bytes(b"%PDF-1.4")
    dest = appcli._deliver_pdf(cfg, str(pdf))
    assert dest == str(out / "main.pdf")
    assert (out / "main.pdf").exists()


def test_deliver_pdf_noop_when_unset(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)  # output_dir empty
    pdf = tmp_path / "main.pdf"; pdf.write_bytes(b"%PDF-1.4")
    assert appcli._deliver_pdf(cfg, str(pdf)) is None
