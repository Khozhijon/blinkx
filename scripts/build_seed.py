"""Save IRSA search results for well-known targets into seed/ (committed with the code).

Live search needs IRSA's query service to say which exposures cover a position; the pixels then
come from AWS. When IRSA is not answering, the backend falls back to these saved lists, so popular
targets keep working. Run again any time to refresh:  python scripts/build_seed.py [--refresh]

With --from-index the list is not asked from IRSA at all: it is worked out from the pointing index
(seed/pointings.npz, see scripts/build_pointing_index.py) and every exposure is confirmed from its
own FITS header, which gives the same list. Use it when IRSA's search is down.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from concurrent.futures import ThreadPoolExecutor  # noqa: E402

from backend import cache, pointings, resolver, spherex as sx  # noqa: E402

TARGETS = [
    "Barnard's star", "Proxima Centauri", "Wolf 359", "Kapteyn's star", "Teegarden's star", "61 Cyg", "Luhman 16",
    "TRAPPIST-1", "Sirius", "Vega", "Betelgeuse", "Polaris", "Altair", "Arcturus",
    "M31", "M33", "M51", "M81", "M82", "M87", "M101", "M104", "NGC 253", "Centaurus A",
    "M1", "M42", "M45", "M57", "M27", "M8", "M16", "M17", "Eta Carinae", "Horsehead Nebula", "Sgr A*",
    "Omega Centauri", "M13", "47 Tuc",
    # the objects the "Planet X and SPHEREx" challenge says to test on (WISE 0855 also at the coordinates it prints)
    "eps Indi B", "WISE J085510.83-071442.5", "08h55m10.831s -7d14m42.53s", "RW Aur", "R Dra",
]


def from_index(ra: float, dec: float) -> dict:
    """The list IRSA would give, worked out from the pointing index and confirmed header by header."""
    cand = pointings.covering(ra, dec, every_exposure=True)
    if cand is None:
        raise SystemExit("seed/pointings.npz is missing: run scripts/build_pointing_index.py first")

    def confirm(exp):
        try:
            meta = sx.read_exposure_meta(exp, ra, dec)
            if not meta["on_detector"]:
                return None
            eh = sx.read_header(exp["key"], exp.get("alt_keys") or ())
            return {"id": exp["id"], "obs_id": exp["obs_id"], "detector": exp["detector"], "collection": exp["collection"], "key": eh.key,
                    "mjd": round(float(eh.header.get("MJD-OBS", exp["mjd"])), 6), "exptime": float(eh.header.get("XPOSURE", exp["exptime"]))}
        except sx.ArchiveError as exc:
            return None if ("HTTP 404" in str(exc) or "HTTP 403" in str(exc)) else exc

    with ThreadPoolExecutor(24) as pool:
        out = list(pool.map(confirm, cand["exposures"]))
    errors = [o for o in out if isinstance(o, Exception)]
    if errors:
        raise sx.ArchiveError(f"{len(errors)} headers could not be read: {errors[0]}")
    rows = sorted((o for o in out if o), key=lambda r: r["mjd"])
    return {"exposures": rows, "truncated": False, "confirmed": "pointing index + FITS headers", "candidates": len(cand["exposures"])}


def main() -> None:
    names = [a for a in sys.argv[1:] if not a.startswith("--")] or TARGETS
    ok = 0
    for name in names:
        try:
            pos = resolver.resolve(name)
            ra, dec = round(pos["ra"], 5), round(pos["dec"], 5)
            if "--refresh" not in sys.argv and cache._path(f"sia3/{ra:.5f}_{dec:.5f}", "json", cache.SEED_DIR).is_file():
                ok += 1
                print(f"{name:20s} already seeded", flush=True)
                continue
            res = None
            if "--from-index" in sys.argv:
                res = from_index(ra, dec)
            for attempt in range(0 if res else 6):  # IRSA can be flaky; be patient here, nobody is waiting
                try:
                    res = sx._sia_all(ra, dec)
                    break
                except sx.ArchiveError:
                    time.sleep(5 + 5 * attempt)
            if res is None:
                print(f"{name:20s} IRSA did not answer, skipped")
                continue
            if res["truncated"]:
                print(f"{name:20s} deep field, not seeded")
                continue
            res["saved_at"] = int(time.time())
            cache.put_seed(f"sia3/{ra:.5f}_{dec:.5f}", res)
            cache.put_json(f"sia3/{ra:.5f}_{dec:.5f}", res)
            ok += 1
            print(f"{name:20s} RA {ra:9.5f} Dec {dec:+9.5f}  {len(res['exposures']):4d} exposures", flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"{name:20s} failed: {exc}")
    print(f"seeded {ok} of {len(names)} targets into {cache.SEED_DIR}")


if __name__ == "__main__":
    main()
