# tests/test_automation_state.py
from pathlib import Path
from automation import state


def test_identity_changes_with_size(tmp_path):
    p = tmp_path / "a.pdf"
    p.write_bytes(b"12345")
    id1 = state.identity(p)
    p.write_bytes(b"1234567890")
    id2 = state.identity(p)
    assert id1 != id2
    assert p.name in id1


def test_identity_stable_across_inplace_rewrite_same_size(tmp_path):
    # A cloud-sync in-place rewrite bumps mtime but not inode/size; the identity
    # must stay stable so an already-filed note is not re-ingested (H5).
    import os
    p = tmp_path / "note.pdf"
    p.write_bytes(b"AAAAA")
    id1 = state.identity(p)
    # Rewrite same-size content in place and bump mtime.
    p.write_bytes(b"BBBBB")
    os.utime(p, (10**9, 10**9))  # far-future mtime
    id2 = state.identity(p)
    assert id1 == id2  # inode + size unchanged -> same key despite new mtime


def test_seen_roundtrip(tmp_path):
    sf = tmp_path / ".scribetex" / "seen.json"
    assert state.load_seen(sf) == set()
    state.mark_seen(sf, "k1")
    state.mark_seen(sf, "k2")
    assert state.load_seen(sf) == {"k1", "k2"}


def test_seen_malformed_is_empty(tmp_path):
    sf = tmp_path / "seen.json"
    sf.write_text("{not json")
    assert state.load_seen(sf) == set()


def test_lock_acquire_then_blocked(tmp_path):
    lf = tmp_path / "ingest.lock"
    assert state.acquire_lock(lf, pid=111, pid_alive=lambda pid: True) is True
    # a second acquirer sees a live holder -> blocked
    assert state.acquire_lock(lf, pid=222, pid_alive=lambda pid: True) is False


def test_lock_reclaims_stale(tmp_path):
    lf = tmp_path / "ingest.lock"
    assert state.acquire_lock(lf, pid=111, pid_alive=lambda pid: True) is True
    # holder 111 is dead -> 222 reclaims
    assert state.acquire_lock(lf, pid=222, pid_alive=lambda pid: False) is True


def test_release_lock(tmp_path):
    lf = tmp_path / "ingest.lock"
    state.acquire_lock(lf, pid=111, pid_alive=lambda pid: True)
    state.release_lock(lf)
    assert not lf.exists()
    state.release_lock(lf)  # idempotent, no raise


def test_error_count_defaults_zero(tmp_path):
    ef = tmp_path / ".scribetex" / "errors.json"
    assert state.get_error_count(ef, "k1") == 0


def test_bump_error_count_increments_and_persists(tmp_path):
    ef = tmp_path / ".scribetex" / "errors.json"
    assert state.bump_error_count(ef, "k1") == 1
    assert state.bump_error_count(ef, "k1") == 2
    assert state.get_error_count(ef, "k1") == 2
    # a different key is tracked independently
    assert state.get_error_count(ef, "k2") == 0
    assert state.bump_error_count(ef, "k2") == 1
    assert state.get_error_count(ef, "k1") == 2


def test_error_count_malformed_file_is_zero(tmp_path):
    ef = tmp_path / "errors.json"
    ef.write_text("{not json")
    assert state.get_error_count(ef, "k1") == 0
    # bump should still work despite the malformed prior contents
    assert state.bump_error_count(ef, "k1") == 1


def test_clear_error_count(tmp_path):
    ef = tmp_path / "errors.json"
    state.bump_error_count(ef, "k1")
    state.bump_error_count(ef, "k1")
    state.clear_error_count(ef, "k1")
    assert state.get_error_count(ef, "k1") == 0


def test_lock_reclaim_atomicity(tmp_path):
    lf = tmp_path / "ingest.lock"
    # Acquire with pid 111 (alive)
    assert state.acquire_lock(lf, pid=111, pid_alive=lambda pid: True) is True
    assert lf.read_text().strip() == "111"
    # Reclaim with pid 222 (111 is now dead)
    assert state.acquire_lock(lf, pid=222, pid_alive=lambda pid: False) is True
    # Verify lockfile contains the NEW pid (atomicity: no clobbering by concurrent writes)
    assert lf.read_text().strip() == "222"
