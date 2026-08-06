import json
from pathlib import Path
import fitz
from automation import ingest, config, prompt


def _pdf(path):
    doc = fitz.open(); doc.new_page(); doc.save(str(path)); doc.close()
    return path


def _cfg(tmp_path):
    return config.load_config(
        env={"SCRIBETEX_INBOX": str(tmp_path), "SCRIBETEX_SETTLE_SECONDS": "0"},
        toml_path=None,
    )


def _result_line(d):
    return f'{prompt.RESULT_PREFIX} {json.dumps(d)}'


def test_filed_moves_to_done(tmp_path):
    cfg = _cfg(tmp_path)
    note = _pdf(tmp_path / "note.pdf")
    invoke = lambda p, b: _result_line(
        {"status": "filed", "course": "Bio", "section": "R", "subsection": "S",
         "date": "2026-08-06", "target": "/x/main.tex", "figures": 0})
    out = ingest.process_inbox(
        cfg, invoke_fn=invoke, notify_fn=lambda *a: None,
        ready_fn=lambda p, s: True, now_fn=lambda: __import__("datetime").datetime(2026, 8, 6),
    )
    assert any(r["outcome"] == "filed" for r in out)
    assert not note.exists()
    moved = list((tmp_path / "Done" / "2026-08-06").glob("note.pdf"))
    assert len(moved) == 1


def test_ambiguous_moves_to_needsreview_with_sidecar(tmp_path):
    cfg = _cfg(tmp_path)
    note = _pdf(tmp_path / "amb.pdf")
    invoke = lambda p, b: _result_line({"status": "ambiguous", "reason": "course unclear"})
    ingest.process_inbox(cfg, invoke_fn=invoke, notify_fn=lambda *a: None,
                         ready_fn=lambda p, s: True)
    assert not note.exists()
    nr = tmp_path / "NeedsReview"
    assert (nr / "amb.pdf").exists()
    sidecar = nr / "amb.pdf.review.txt"
    assert sidecar.exists() and "course unclear" in sidecar.read_text()


def test_error_leaves_in_place(tmp_path):
    cfg = _cfg(tmp_path)
    note = _pdf(tmp_path / "err.pdf")
    invoke = lambda p, b: _result_line({"status": "error", "reason": "boom"})
    ingest.process_inbox(cfg, invoke_fn=invoke, notify_fn=lambda *a: None,
                         ready_fn=lambda p, s: True)
    assert note.exists()  # stays for retry


def test_seen_prevents_reprocessing(tmp_path):
    cfg = _cfg(tmp_path)
    _pdf(tmp_path / "once.pdf")
    calls = []
    invoke = lambda p, b: calls.append(p) or _result_line(
        {"status": "filed", "course": "C", "date": "2026-08-06", "target": "/x"})
    ingest.process_inbox(cfg, invoke_fn=invoke, notify_fn=lambda *a: None,
                         ready_fn=lambda p, s: True,
                         now_fn=lambda: __import__("datetime").datetime(2026, 8, 6))
    # second pass: file already moved to Done AND marked seen -> no new invoke
    ingest.process_inbox(cfg, invoke_fn=invoke, notify_fn=lambda *a: None,
                         ready_fn=lambda p, s: True,
                         now_fn=lambda: __import__("datetime").datetime(2026, 8, 6))
    assert len(calls) == 1


def test_not_ready_skipped(tmp_path):
    cfg = _cfg(tmp_path)
    _pdf(tmp_path / "slow.pdf")
    calls = []
    invoke = lambda p, b: calls.append(p) or _result_line({"status": "filed"})
    ingest.process_inbox(cfg, invoke_fn=invoke, notify_fn=lambda *a: None,
                         ready_fn=lambda p, s: False)
    assert calls == []
    assert (tmp_path / "slow.pdf").exists()


def test_subdirs_ignored(tmp_path):
    cfg = _cfg(tmp_path)
    (tmp_path / "Done").mkdir()
    _pdf(tmp_path / "Done" / "already.pdf")
    calls = []
    invoke = lambda p, b: calls.append(p) or _result_line({"status": "filed"})
    ingest.process_inbox(cfg, invoke_fn=invoke, notify_fn=lambda *a: None,
                         ready_fn=lambda p, s: True)
    assert calls == []  # files under Done/ are not candidates
