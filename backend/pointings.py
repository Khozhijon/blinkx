"""Which SPHEREx exposures cover a sky position, worked out without IRSA's search service.

``seed/pointings.npz`` (built by ``scripts/build_pointing_index.py`` from NASA's open AWS bucket)
holds one row per SPHEREx pointing: the time, direction and roll of detector 2 in its first
exposure. The six detectors sit at fixed places in the focal plane and the telescope steps a fixed
distance between the (up to four) exposures of a pointing, so the footprint of every exposure
follows from that one row.

This module only proposes candidates. Each one is then confirmed from its own FITS header by the
normal code path (``spherex.read_exposure_meta``), so a picture is never shown for a place it
does not cover. IRSA stays the first choice; this is what keeps the tool working when IRSA's
search is down.
"""
from __future__ import annotations

import threading
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "seed" / "pointings.npz"

# Focal plane, measured from image headers (scripts/build_pointing_index.py --check): where each
# detector's centre falls, in detector-2 pixels. Detectors 1-3 sit side by side; 4-6 see the same
# three fields through the dichroic.
DETECTOR_CENTRE = {1: (-2271.5, 28.0), 2: (0.0, 0.0), 3: (2274.8, 37.1), 4: (-2275.7, 39.5), 5: (-2.5, 9.8), 6: (2274.5, 49.4)}
STEP_Y = 115.2  # pixels the field moves between consecutive exposures of one pointing
STEP_SECONDS = 128.9  # and the time between them
HALF = 1020.0  # half the width of a detector, pixels
EXPTIME = 113.5826
COLLECTION = {"dr1": "spherex_dr1", "qr3": "spherex_qr3"}

_lock = threading.Lock()
_index: dict | None = None


def load() -> dict | None:
    """The pointing index as arrays, or None when the file is not there."""
    global _index
    with _lock:
        if _index is None and INDEX.is_file():
            with np.load(INDEX) as z:
                idx = {k: z[k] for k in z.files}
            a0, d0 = np.radians(idx["ra"]), np.radians(idx["dec"])
            idx.update(sin_d0=np.sin(d0), cos_d0=np.cos(d0), a0=a0, weeks=[str(w) for w in idx["weeks"]], versions=[str(v) for v in idx["versions"]])
            # other processing versions seen in the same week: tried when a file is not under the expected one
            alt: dict[int, set[int]] = {}
            for w, vers in zip(idx["week"].tolist(), idx["ver"].tolist()):
                alt.setdefault(w, set()).update(v for v in vers if v >= 0)
            idx["week_versions"] = alt
            _index = idx
        return _index


def available() -> bool:
    return load() is not None


def built() -> int:
    idx = load()
    return int(idx["built"]) if idx else 0


def last_mjd() -> float:
    idx = load()
    return float(idx["mjd"].max()) if idx else 0.0


def _key(rel: str, week: str, pt: int, k: int, det: int, ver: str) -> str:
    return f"{rel}/level2/{week}/{ver}/{det}/level2_{week}_{pt:04d}_{k}D{det}_spx_{ver}.fits"


def covering(ra: float, dec: float, margin: float = 90.0, every_exposure: bool = False) -> dict | None:
    """Exposures whose detector footprint should contain (ra, dec), oldest first, in the same shape as
    the IRSA search result. ``margin`` (pixels) is how far outside a detector a candidate may fall and
    still be proposed: the headers decide in the end. ``every_exposure`` also proposes exposures that
    the index did not see for detector 2 (the file may exist for another detector): slower to confirm,
    used when building the saved lists."""
    idx = load()
    if idx is None:
        return None
    a, d = np.radians(ra), np.radians(dec)
    da = a - idx["a0"]
    cosc = np.sin(d) * idx["sin_d0"] + np.cos(d) * idx["cos_d0"] * np.cos(da)
    near = np.where(cosc > np.cos(np.radians(8.5)))[0]  # farthest corner of the focal plane is about 6.9 deg from its centre
    rows = []
    if len(near):
        c = cosc[near]
        xi = np.degrees(np.cos(d) * np.sin(da[near]) / c)  # gnomonic projection about the detector-2 centre
        eta = np.degrees((np.sin(d) * idx["cos_d0"][near] - np.cos(d) * idx["sin_d0"][near] * np.cos(da[near])) / c)
        pc = idx["pc"][near]
        det = pc[:, 0] * pc[:, 3] - pc[:, 1] * pc[:, 2]
        x = (pc[:, 3] * xi - pc[:, 1] * eta) / det  # pixels from the centre of detector 2, first exposure
        y = (-pc[:, 2] * xi + pc[:, 0] * eta) / det
        reach = HALF + margin
        for j, i in enumerate(near.tolist()):
            if abs(x[j]) > 2275.0 + reach:
                continue
            rel, week = idx["weeks"][int(idx["week"][i])].split("/")
            pt, k0, mjd0 = int(idx["pt"][i]), int(idx["k0"][i]), float(idx["mjd"][i])
            for k in (1, 2, 3, 4):
                v = int(idx["ver"][i][k - 1])
                if v < 0:
                    if not every_exposure:
                        continue
                    v = int(idx["ver"][i][k0 - 1])
                yk = float(y[j]) - STEP_Y * (k - k0)
                for dnum, (cx, cy) in DETECTOR_CENTRE.items():
                    if abs(float(x[j]) - cx) <= reach and abs(yk - cy) <= reach:
                        ver = idx["versions"][v]
                        others = [idx["versions"][o] for o in sorted(idx["week_versions"].get(int(idx["week"][i]), ())) if o != v]
                        rows.append({
                            "id": f"{week}_{pt:04d}_{k}D{dnum}", "obs_id": f"{week}_{pt:04d}_{k}", "detector": dnum,
                            "collection": COLLECTION.get(rel, "spherex"), "key": _key(rel, week, pt, k, dnum, ver),
                            "mjd": round(mjd0 + (k - k0) * STEP_SECONDS / 86400.0, 6), "exptime": EXPTIME, "approx": True,
                            **({"alt_keys": [_key(rel, week, pt, k, dnum, o) for o in others]} if others else {}),
                        })
    rows.sort(key=lambda r: (r["mjd"], r["detector"]))
    return {"exposures": rows, "truncated": False, "from_index": True, "index_built": built()}
