"""Idempotency seen-set + an atomic single-holder lockfile."""
from __future__ import annotations
import json
import os
from pathlib import Path


def identity(path) -> str:
    """A stable idempotency key for an inbox file: name:size:inode.

    Uses the inode (st_ino), NOT mtime: a cloud-sync client (iCloud/Dropbox) can
    rewrite a file in place and bump its mtime without the note actually changing,
    which under an mtime key would silently re-ingest an already-filed note. The
    inode is stable across such in-place rewrites and across an in-place rename,
    and it changes for a genuinely new file. name+size are included so the rare
    case of a recycled inode still needs a matching name and size to collide.
    """
    st = Path(path).stat()
    return f"{Path(path).name}:{st.st_size}:{st.st_ino}"


def _atomic_write_text(path: Path, text: str) -> None:
    """Write via a temp file + os.replace so a crash mid-write can't truncate
    the existing JSON (which would lose the whole seen-set / error map)."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, path)


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
    _atomic_write_text(p, json.dumps(sorted(seen)))


def _load_error_counts(error_file) -> dict:
    p = Path(error_file)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text())
        if not isinstance(data, dict):
            return {}
        return {str(k): int(v) for k, v in data.items()}
    except Exception:
        return {}


def get_error_count(error_file, key) -> int:
    return _load_error_counts(error_file).get(key, 0)


def bump_error_count(error_file, key) -> int:
    p = Path(error_file)
    p.parent.mkdir(parents=True, exist_ok=True)
    counts = _load_error_counts(p)
    counts[key] = counts.get(key, 0) + 1
    _atomic_write_text(p, json.dumps(counts))
    return counts[key]


def clear_error_count(error_file, key) -> None:
    p = Path(error_file)
    counts = _load_error_counts(p)
    if key in counts:
        del counts[key]
        p.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write_text(p, json.dumps(counts))


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
            # Stale (or ours): atomically reclaim. Unlink then O_EXCL-recreate,
            # so a concurrent acquirer between our failed open and now cannot be
            # clobbered by a plain overwrite (TOCTOU).
            try:
                os.unlink(str(p))
            except FileNotFoundError:
                pass  # someone else already cleared it
            try:
                fd = os.open(str(p), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(pid).encode())
                os.close(fd)
                return True
            except FileExistsError:
                return False  # a concurrent process won the reclaim; we didn't
        return False


def release_lock(lock_file) -> None:
    try:
        Path(lock_file).unlink()
    except FileNotFoundError:
        pass
