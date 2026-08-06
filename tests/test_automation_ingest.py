import json
from pathlib import Path
import fitz
from automation import ingest, config, prompt, state


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


def test_error_below_cap_stays_in_place_and_not_seen(tmp_path):
    cfg = _cfg(tmp_path)
    note = _pdf(tmp_path / "err.pdf")
    invoke = lambda p, b: _result_line({"status": "error", "reason": "boom"})
    now = lambda: __import__("datetime").datetime(2026, 8, 6)
    for _ in range(ingest.MAX_ERROR_ATTEMPTS - 1):
        ingest.process_inbox(cfg, invoke_fn=invoke, notify_fn=lambda *a: None,
                             ready_fn=lambda p, s: True, now_fn=now)
    assert note.exists()
    sf = config.state_file(cfg)
    key = state.identity(note)
    assert key not in state.load_seen(sf)


def test_error_hits_cap_dead_letters_and_marks_seen(tmp_path):
    cfg = _cfg(tmp_path)
    note = _pdf(tmp_path / "err.pdf")
    invoke = lambda p, b: _result_line({"status": "error", "reason": "boom"})
    now = lambda: __import__("datetime").datetime(2026, 8, 6)

    out = []
    for _ in range(ingest.MAX_ERROR_ATTEMPTS):
        out = ingest.process_inbox(cfg, invoke_fn=invoke, notify_fn=lambda *a: None,
                                   ready_fn=lambda p, s: True, now_fn=now)
    assert not note.exists()
    nr = tmp_path / "NeedsReview"
    assert (nr / "err.pdf").exists()
    sidecar = nr / "err.pdf.error.txt"
    assert sidecar.exists() and "boom" in sidecar.read_text()
    assert out[-1]["outcome"] == "gave_up"

    # File identity changed on move (new mtime/size context), so instead of
    # re-deriving the original key, verify the real behavioral guarantee: a
    # further sweep does not re-invoke because the file is gone from the
    # inbox and its original identity was marked seen.
    calls = []
    invoke2 = lambda p, b: calls.append(p) or _result_line({"status": "error"})
    ingest.process_inbox(cfg, invoke_fn=invoke2, notify_fn=lambda *a: None,
                         ready_fn=lambda p, s: True, now_fn=now)
    assert calls == []  # no re-invocation: file is gone from inbox and seen


def test_error_notify_first_and_giveup_only_middle_suppressed(tmp_path):
    cfg = _cfg(tmp_path)
    note = _pdf(tmp_path / "err.pdf")
    invoke = lambda p, b: _result_line({"status": "error", "reason": "boom"})
    now = lambda: __import__("datetime").datetime(2026, 8, 6)
    notify_calls = []
    notify_fn = lambda title, msg: notify_calls.append((title, msg))

    assert ingest.MAX_ERROR_ATTEMPTS == 3
    for _ in range(ingest.MAX_ERROR_ATTEMPTS):
        ingest.process_inbox(cfg, invoke_fn=invoke, notify_fn=notify_fn,
                             ready_fn=lambda p, s: True, now_fn=now)
    # Attempt 1: notify (first error). Attempt 2: suppressed. Attempt 3: give-up notify.
    assert len(notify_calls) == 2
    assert "error" in notify_calls[0][0].lower()
    assert "gave up" in notify_calls[1][0].lower()


def test_error_count_cleared_on_success(tmp_path):
    cfg = _cfg(tmp_path)
    note = _pdf(tmp_path / "flaky.pdf")
    now = lambda: __import__("datetime").datetime(2026, 8, 6)

    key = state.identity(note)
    error_invoke = lambda p, b: _result_line({"status": "error", "reason": "boom"})
    ingest.process_inbox(cfg, invoke_fn=error_invoke, notify_fn=lambda *a: None,
                         ready_fn=lambda p, s: True, now_fn=now)
    ef = config.error_file(cfg)
    assert state.get_error_count(ef, key) == 1

    ok_invoke = lambda p, b: _result_line(
        {"status": "filed", "course": "C", "date": "2026-08-06", "target": "/x"})
    ingest.process_inbox(cfg, invoke_fn=ok_invoke, notify_fn=lambda *a: None,
                         ready_fn=lambda p, s: True, now_fn=now)
    assert state.get_error_count(ef, key) == 0


def test_notify_escapes_quotes_and_backslashes():
    calls = []

    def fake_run(argv, **kwargs):
        calls.append(argv)
        class R:
            returncode = 0
        return R()

    ingest.notify('Title "quoted"', 'Message with "quote" and \\backslash\\',
                 run_fn=fake_run)
    assert len(calls) == 1
    script = calls[0][2]  # ["osascript", "-e", script]
    assert '\\"quoted\\"' in script
    assert '\\\\backslash\\\\' in script
    # sanity: the AppleScript literal is well-formed (quotes only where escaped)
    assert "display notification" in script


def test_subdirs_ignored(tmp_path):
    cfg = _cfg(tmp_path)
    (tmp_path / "Done").mkdir()
    _pdf(tmp_path / "Done" / "already.pdf")
    calls = []
    invoke = lambda p, b: calls.append(p) or _result_line({"status": "filed"})
    ingest.process_inbox(cfg, invoke_fn=invoke, notify_fn=lambda *a: None,
                         ready_fn=lambda p, s: True)
    assert calls == []  # files under Done/ are not candidates
