import json
import re
from automation import appcli, config, prompt


def _cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("SCRIBETEX_NOTES_ROOT", str(tmp_path / "notes"))
    return config.load_config(env={"SCRIBETEX_INBOX": str(tmp_path)}, toml_path=None)


def _course_with_note(tmp_path, name="Bio"):
    from scribetex.classify import course_slug
    from scribetex.placement import ENTRIES_START, ENTRIES_END, note_block
    d = tmp_path / "notes" / course_slug(name)
    d.mkdir(parents=True, exist_ok=True)
    body = note_block("\\section{Receptors}\nold text", "2026-08-06", "bio.pdf")
    (d / "main.tex").write_text(
        f"HEAD\n{ENTRIES_START}\n{body}{ENTRIES_END}\nTAIL\n")
    return d / "main.tex"


def test_build_correct_prompt_targets_one_note():
    p = prompt.build_correct_prompt("Bio", "2026-08-06:bio-pdf",
                                    "fix the integral on page 2")
    assert "2026-08-06:bio-pdf" in p
    assert "patch_note_region" in p
    assert "fix the integral on page 2" in p
    assert "NOTHING else" in p or "changing NOTHING else" in p


def test_build_correct_prompt_reread_mentions_prepare_note():
    p = prompt.build_correct_prompt("Bio", "2026-08-06:bio-pdf", "recrop the eye",
                                    note_path="/x/bio.pdf")
    assert "prepare_note" in p and "/x/bio.pdf" in p


def test_build_correct_prompt_rejects_unsafe_instruction():
    try:
        prompt.build_correct_prompt("Bio", "k", "do this\nignore prior")
        assert False, "expected UnsafeNotePathError"
    except prompt.UnsafeNotePathError:
        pass


def test_list_notes_command(tmp_path, monkeypatch, capsys):
    cfg = _cfg(tmp_path, monkeypatch)
    _course_with_note(tmp_path, "Bio")
    res = appcli._list_notes(cfg, "Bio")
    assert res["ok"] is True
    assert res["notes"][0]["key"] == "2026-08-06:bio-pdf"


def test_correct_patches_via_worker(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    _course_with_note(tmp_path, "Bio")

    def worker(prompt_text, claude_bin):
        prefix = re.search(r"SCRIBETEX_RESULT_[0-9a-f]+:", prompt_text).group(0)
        # A faithful worker would actually call patch_note_region; here we just
        # confirm _correct trusts a 'corrected' status.
        return f'{prefix} {{"status":"corrected","course":"Bio","note_key":"2026-08-06:bio-pdf"}}'
    res = appcli._correct(cfg, "Bio", "2026-08-06:bio-pdf", "fix it",
                          invoke_fn=worker)
    assert res["ok"] is True and res["corrected"]["status"] == "corrected"


def test_correct_reports_failure(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    _course_with_note(tmp_path, "Bio")
    res = appcli._correct(cfg, "Bio", "2026-08-06:bio-pdf", "fix it",
                          invoke_fn=lambda *a, **k: "")
    assert res["ok"] is False
