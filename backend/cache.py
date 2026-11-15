"""Tiny on-disk cache (JSON and raw bytes) so repeat views never re-hit the archive."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from pathlib import Path

CACHE_DIR = Path(os.environ.get("BLINKX_CACHE", Path(__file__).resolve().parent.parent / "cache"))


def _path(key: str, ext: str) -> Path:
    group, _, name = key.partition("/")
    safe = "".join(c if c.isalnum() or c in "._-+" else "_" for c in name)[:80]
    digest = hashlib.sha1(key.encode()).hexdigest()[:10]
    return CACHE_DIR / group / f"{safe}.{digest}.{ext}"


def _fresh(p: Path, max_age: float | None) -> bool:
    try:
        return p.is_file() and (max_age is None or time.time() - p.stat().st_mtime < max_age)
    except OSError:
        return False


def _write(p: Path, data: bytes) -> None:
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=p.parent, suffix=".tmp")
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.replace(tmp, p)
    except OSError:
        pass  # a read-only or full disk must never break a request


def get_bytes(key: str, max_age: float | None = None) -> bytes | None:
    p = _path(key, "bin")
    if not _fresh(p, max_age):
        return None
    try:
        return p.read_bytes()
    except OSError:
        return None


def put_bytes(key: str, data: bytes) -> None:
    _write(_path(key, "bin"), data)


def get_json(key: str, max_age: float | None = None):
    p = _path(key, "json")
    if not _fresh(p, max_age):
        return None
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return None


def put_json(key: str, obj) -> None:
    _write(_path(key, "json"), json.dumps(obj, separators=(",", ":")).encode())
