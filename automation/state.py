"""Idempotency seen-set + an atomic single-holder lockfile."""
from __future__ import annotations
import json
import os
from pathlib import Path


def identity(path) -> str:
    st = Path(path).stat()
    return f"{Path(path).name}:{st.st_size}:{st.st_mtime_ns}"


def load_seen(state_file) -> set:
    p = Path(state_file)
    if not p.exists():
        return set()
    try:
        return set(json.loads(p.read_text()))
    except Exception:
        return set()


def mark_seen(state_file, key) -> None:
    p = Path(state_file)
    p.parent.mkdir(parents=True, exist_ok=True)
    seen = load_seen(p)
    seen.add(key)
    p.write_text(json.dumps(sorted(seen)))


def _default_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists but not ours


def acquire_lock(lock_file, pid=None, pid_alive=None) -> bool:
    p = Path(lock_file)
    p.parent.mkdir(parents=True, exist_ok=True)
    pid = os.getpid() if pid is None else pid
    pid_alive = pid_alive or _default_alive
    try:
        fd = os.open(str(p), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(pid).encode())
        os.close(fd)
        return True
    except FileExistsError:
        try:
            holder = int(p.read_text().strip() or "-1")
        except Exception:
            holder = -1
        if holder == pid or not pid_alive(holder):
            # stale (or ours): reclaim
            p.write_text(str(pid))
            return True
        return False


def release_lock(lock_file) -> None:
    try:
        Path(lock_file).unlink()
    except FileNotFoundError:
        pass
