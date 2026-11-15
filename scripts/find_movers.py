"""Find SPHEREx exposures that caught a known solar-system object.

SPHEREx looks roughly 90 degrees away from the Sun, so an asteroid or comet is only imaged
while its solar elongation is near 90 degrees. For each object we:

  1. ask JPL Horizons for a geocentric ephemeris (RA, Dec, V mag, elongation) over the survey;
  2. keep the times when the elongation is 80-100 degrees;
  3. ask IRSA (SIA2, with a TIME window) which Level-2 images cover the object's position
     on those days;
  4. confirm with the real FITS header WCS that the object's position *at the exposure
     mid-time* falls on the detector.

Output: one JSON line per hit on stdout and, with --out, a JSON file of all hits per object.

Usage:
    python scripts/find_movers.py "4;" "1;" "2;" --out spike/out/hits.json
    python scripts/find_movers.py "DES=C/2025 N1;" --start 2025-07-01

Object strings are Horizons COMMAND values ("4;" = (4) Vesta, "DES=C/2025 N1;" = 3I/ATLAS).
Nothing here is simulated: positions come from Horizons, images from the SPHEREx archive.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
import time
import warnings
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from astropy.wcs import WCS  # noqa: E402

from backend import spherex as sx  # noqa: E402

warnings.simplefilter("ignore")

HORIZONS = "https://ssd.jpl.nasa.gov/api/horizons.api"
COLLECTIONS = ("spherex_dr1", "spherex_qr3")
SURVEY_START, SURVEY_STOP = "2025-05-01", "2026-10-01"
# Measured from the archive on 2026-11-15: DR1 images end in May 2026, QR3 images start in mid-2026.
DR1_LAST_MJD, QR3_FIRST_MJD = 61250.0, 61150.0


def horizons(command: str, start: str, stop: str, step: str) -> dict:
    """Geocentric ephemeris: dict of numpy arrays mjd, ra, dec, vmag, elong (+ 'name')."""
    params = {
        "format": "text",
        "COMMAND": f"'{command}'",
        "OBJ_DATA": "NO",
        "MAKE_EPHEM": "YES",
        "EPHEM_TYPE": "OBSERVER",
        "CENTER": "'500@399'",
        "START_TIME": f"'{start}'",
        "STOP_TIME": f"'{stop}'",
        "STEP_SIZE": f"'{step}'",
        "QUANTITIES": "'1,9,23'",
        "ANG_FORMAT": "DEG",
        "CSV_FORMAT": "YES",
        "CAL_FORMAT": "JD",
    }
    text = sx._get(HORIZONS, params=params).text
    if "$$SOE" not in text:
        raise RuntimeError(f"Horizons gave no ephemeris for {command!r}: {text[-400:]}")
    m = re.search(r"Target body name:\s*(.+?)\s{2,}", text)
    name = m.group(1).strip() if m else command
    head = text.split("$$SOE")[0].strip().splitlines()[-2]
    cols = [c.strip() for c in head.split(",")]
    body = text.split("$$SOE")[1].split("$$EOE")[0].strip().splitlines()
    rows = [[c.strip() for c in line.split(",")] for line in body]

    def col(prefixes):
        for i, c in enumerate(cols):
            if any(c.startswith(p) for p in prefixes):
                return i
        return None

    i_jd, i_ra, i_dec = col(["Date_________JDUT"]), col(["R.A."]), col(["DEC"])
    i_mag, i_el = col(["APmag", "T-mag"]), col(["S-O-T"])

    def num(v):
        try:
            return float(v)
        except ValueError:
            return np.nan

    return {
        "name": name,
        "mjd": np.array([float(r[i_jd]) - 2400000.5 for r in rows]),
        "ra": np.array([float(r[i_ra]) for r in rows]),
        "dec": np.array([float(r[i_dec]) for r in rows]),
        "vmag": np.array([num(r[i_mag]) if i_mag is not None else np.nan for r in rows]),
        "elong": np.array([num(r[i_el]) for r in rows]),
    }


def interp_pos(eph: dict, mjd: float) -> tuple[float, float]:
    """Linear interpolation of RA/Dec (handles the 0/360 wrap)."""
    ra = np.degrees(np.unwrap(np.radians(eph["ra"])))
    return float(np.interp(mjd, eph["mjd"], ra)) % 360.0, float(np.interp(mjd, eph["mjd"], eph["dec"]))


def sia_time(collection: str, ra: float, dec: float, radius: float, mjd0: float, mjd1: float) -> list[dict]:
    """SIA2 query restricted in time; returns exposures in the same shape as sx.search_exposures."""
    r = sx._get(
        sx.SIA_URL,
        params={
            "COLLECTION": collection,
            "POS": f"circle {ra:.6f} {dec:.6f} {radius}",
            "TIME": f"{mjd0:.5f} {mjd1:.5f}",
            "RESPONSEFORMAT": "CSV",
        },
    )
    out = []
    for row in csv.DictReader(io.StringIO(r.text)):
        url = row.get("access_url", "")
        m = re.search(r"SPHEREx-D(\d)", row.get("energy_bandpassname", ""))
        if "/ibe/data/spherex/" not in url or not m:
            continue
        t = float(row["t_min"])
        if not (mjd0 - 0.01 <= t <= mjd1 + 0.01):  # belt and braces if TIME were ignored
            continue
        det = int(m.group(1))
        out.append(
            {
                "id": f"{row['obs_id']}D{det}",
                "obs_id": row["obs_id"],
                "detector": det,
                "collection": collection,
                "key": url.split("/ibe/data/spherex/", 1)[1],
                "mjd": t,
                "exptime": float(row["t_exptime"]),
            }
        )
    return out


def find_hits(command: str, start: str = SURVEY_START, stop: str = SURVEY_STOP, elong=(80.0, 100.0), verbose=True) -> dict:
    """All exposures whose detector really contained the object at exposure mid-time."""
    coarse = horizons(command, start, stop, "6 h")
    ok = (coarse["elong"] >= elong[0]) & (coarse["elong"] <= elong[1])
    if verbose:
        print(f"# {coarse['name']}: {int(ok.sum())} of {len(ok)} 6-h steps have elongation {elong}", file=sys.stderr)
    # merge consecutive 6-h steps into windows
    windows, cur = [], None
    for i, good in enumerate(ok):
        if good and cur is None:
            cur = [i, i]
        elif good:
            cur[1] = i
        elif cur is not None:
            windows.append(cur)
            cur = None
    if cur is not None:
        windows.append(cur)

    candidates: dict[str, dict] = {}
    jobs = []
    for i0, i1 in windows:
        for i in range(i0, i1 + 1):  # one small-radius query per 6-h step, each covering +-3.2 h
            jobs.append((coarse["ra"][i], coarse["dec"][i], coarse["mjd"][i]))

    def run(job):
        ra, dec, mjd = job
        found = []
        for coll in COLLECTIONS:
            # DR1 holds the first survey year, QR3 the following quarter; skip the impossible half.
            if (coll == "spherex_dr1" and mjd > DR1_LAST_MJD) or (coll == "spherex_qr3" and mjd < QR3_FIRST_MJD):
                continue
            # A tiny search radius keeps IRSA fast; the detector is 3.5 deg wide, so an image that
            # holds the object within +-3 h almost always also holds this exact point.
            # IRSA's SIA front end intermittently answers "502 Proxy Error"; be patient and retry.
            for attempt in range(5):
                try:
                    found += sia_time(coll, ra, dec, 0.02, mjd - 0.135, mjd + 0.135)
                    break
                except Exception as exc:  # noqa: BLE001
                    if attempt == 4:
                        print(f"# SIA error {coll} mjd={mjd:.2f}: {str(exc)[:80]}", file=sys.stderr)
                    else:
                        time.sleep(3.0 * (attempt + 1))
        return found

    with ThreadPoolExecutor(4) as pool:
        for k, found in enumerate(pool.map(run, jobs)):
            for e in found:
                candidates[e["id"]] = e
            if verbose and k % 50 == 49:
                print(f"#   {k + 1}/{len(jobs)} SIA windows, {len(candidates)} exposures so far", file=sys.stderr, flush=True)
    if verbose:
        print(f"# {coarse['name']}: {len(candidates)} exposures near the track, checking WCS...", file=sys.stderr)
    if not candidates:
        return {"name": coarse["name"], "command": command, "hits": []}

    mjds = [e["mjd"] for e in candidates.values()]
    from astropy.time import Time

    t0 = Time(min(mjds) - 0.1, format="mjd").iso[:16]
    t1 = Time(max(mjds) + 0.1, format="mjd").iso[:16]
    span_min = (max(mjds) - min(mjds) + 0.2) * 1440
    step = max(10, int(np.ceil(span_min / 80000)))  # Horizons allows ~90k lines
    fine = horizons(command, t0, t1, f"{step} m")

    def check(e):
        try:
            eh = sx.read_header(e["key"])
        except Exception as exc:  # noqa: BLE001
            return None
        h = eh.header
        mjd = float(h.get("MJD-AVG", e["mjd"]))
        ra, dec = interp_pos(fine, mjd)
        x, y = (float(v) for v in WCS(h).all_world2pix([[ra, dec]], 0, quiet=True)[0])
        margin = 12
        if not (margin <= x <= eh.nx - margin and margin <= y <= eh.ny - margin):
            return None
        try:
            wl, _ = sx.wavelength_at(h, sx._wave_table(eh), x, y)
        except Exception:  # noqa: BLE001
            wl = None
        return {
            **{k: e[k] for k in ("id", "detector", "collection", "key")},
            "mjd": mjd,
            "date_obs": str(h.get("DATE-OBS", "")),
            "ra": round(ra, 6),
            "dec": round(dec, 6),
            "pixel": [round(x, 1), round(y, 1)],
            "wavelength_um": wl,
            "vmag": float(np.interp(mjd, fine["mjd"], fine["vmag"])) if np.isfinite(fine["vmag"]).any() else None,
            "elong": float(np.interp(mjd, fine["mjd"], fine["elong"])),
        }

    with ThreadPoolExecutor(16) as pool:
        hits = [h for h in pool.map(check, candidates.values()) if h]
    hits.sort(key=lambda h: h["mjd"])
    return {"name": coarse["name"], "command": command, "hits": hits}


def clusters(hits: list[dict], detector: int, max_gap_h: float = 30.0) -> list[list[dict]]:
    """Runs of same-band hits with gaps shorter than max_gap_h."""
    mine = [h for h in hits if h["detector"] == detector]
    out: list[list[dict]] = []
    for h in mine:
        if out and (h["mjd"] - out[-1][-1]["mjd"]) * 24 <= max_gap_h:
            out[-1].append(h)
        else:
            out.append([h])
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("objects", nargs="+", help="Horizons COMMAND strings, e.g. '4;' or 'DES=C/2025 N1;'")
    ap.add_argument("--start", default=SURVEY_START)
    ap.add_argument("--stop", default=SURVEY_STOP)
    ap.add_argument("--out", help="write all hits to this JSON file")
    args = ap.parse_args()
    results = {}
    for obj in args.objects:
        try:
            res = find_hits(obj, args.start, args.stop)
        except Exception as exc:  # noqa: BLE001
            print(f"# {obj}: FAILED {exc}", file=sys.stderr)
            continue
        results[obj] = res
        per = {}
        for h in res["hits"]:
            per.setdefault(h["detector"], []).append(h)
        print(f"== {res['name']}: {len(res['hits'])} exposures contain it; per band " + str({f"D{k}": len(v) for k, v in sorted(per.items())}))
        for det in sorted(per):
            for cl in clusters(res["hits"], det):
                if len(cl) >= 3:
                    span_h = (cl[-1]["mjd"] - cl[0]["mjd"]) * 24
                    sep = np.hypot((cl[-1]["ra"] - cl[0]["ra"]) * np.cos(np.radians(cl[0]["dec"])), cl[-1]["dec"] - cl[0]["dec"]) * 3600
                    print(
                        f"   D{det}: {len(cl)} exposures {cl[0]['date_obs'][:16]} -> {cl[-1]['date_obs'][:16]} ({span_h:.1f} h), "
                        f"moves {sep:.0f}\"  V~{cl[0]['vmag']}"
                    )
        if args.out:
            Path(args.out).write_text(json.dumps(results, indent=1))


if __name__ == "__main__":
    main()
