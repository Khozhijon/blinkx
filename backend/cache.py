"""Tiny on-disk cache (JSON and raw bytes) so repeat views never re-hit the archive."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = Path(os.environ.get("BLINKX_CACHE", ROOT / "cache"))
# Read-only search results for well-known targets, committed with the code (scripts/build_seed.py),
# used when IRSA's query service is not answering.
SEED_DIR = ROOT / "seed"


def _path(key: str, ext: str, base: Path | None = None) -> Path:
    group, _, name = key.partition("/")
    safe = "".join(c if c.isalnum() or c in "._-+" else "_" for c in name)[:80]
    digest = hashlib.sha1(key.encode()).hexdigest()[:10]
    return (base or CACHE_DIR) / group / f"{safe}.{digest}.{ext}"


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


def get_json_stale(key: str):
    """Any copy we have, however old: the cache first, then the committed seed. None if neither."""
    for base in (CACHE_DIR, SEED_DIR):
        p = _path(key, "json", base)
        try:
            if p.is_file():
                return json.loads(p.read_text())
        except (OSError, ValueError):
            continue
    return None


def put_seed(key: str, obj) -> Path:
    p = _path(key, "json", SEED_DIR)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, separators=(",", ":")))
    return p
