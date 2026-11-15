"""Precompute the "Try an example" bundles from the live archive.

Each bundle is one static JSON file holding real SPHEREx pixels and header metadata, so the demo
keeps working when IRSA is slow or unreachable. Nothing in a bundle is invented: every frame is
produced by the same code path as the live API (backend.spherex.get_frame).

    python scripts/build_examples.py            # rebuild all
    python scripts/build_examples.py vesta      # rebuild the ones whose slug contains "vesta"
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend import main as api  # noqa: E402
from backend import catalogs, detect, gaia, skybot, spherex as sx  # noqa: E402

OUT = ROOT / "frontend" / "examples"
DEFS = ROOT / "scripts" / "examples.json"
CANDIDATES = ROOT / "scripts" / "mover_candidates.json"


def pick_frames(frames: list[dict], spec) -> list[dict]:
    """spec: "all" | {"ids": [...]} | {"near_um": 1.5, "tol": 0.08} | {"max": 24}"""
    if spec == "all" or spec is None:
        return frames
    if "ids" in spec:
        by = {f["id"]: f for f in frames}
        missing = [i for i in spec["ids"] if i not in by]
        if missing:
            raise SystemExit(f"frames not found at this position/band: {missing}")
        return [by[i] for i in spec["ids"]]
    out = frames
    if "near_um" in spec:
        out = [f for f in out if f["wavelength_um"] and abs(f["wavelength_um"] - spec["near_um"]) <= spec.get("tol", 0.08)]
    if "max" in spec and len(out) > spec["max"]:
        step = len(out) / spec["max"]
        out = [out[int(i * step)] for i in range(spec["max"])]
    return out


def separation_arcsec(ra1, dec1, ra2, dec2) -> float:
    import math

    return 3600 * math.hypot((ra1 - ra2) * math.cos(math.radians(dec1)), dec1 - dec2)


def apply_candidate(ex: dict) -> dict:
    """Fill position, band, frame list and predicted track from scripts/mover_candidates.json."""
    if "candidate" not in ex:
        return ex
    cand = {c["slug"]: c for c in json.loads(CANDIDATES.read_text())}[ex["candidate"]]
    out = {"ra": cand["ra"], "dec": cand["dec"], "band": cand["band"], "frames": {"ids": cand["frames"]}, **ex}
    out["predicted"] = cand["predicted"]  # JPL Horizons position of the object at each exposure
    return out


def build_simulated(ex: dict) -> dict:
    """The offline demo: a made-up field run through the same detection code. Labelled as simulated everywhere."""
    from backend import simulate

    sim = simulate.planet_x_field(size_deg=float(ex["size"]), n=192, per_group=2)  # a coarser grid keeps the file small
    ra, dec, size = float(ex["ra"]), float(ex["dec"]), float(ex["size"])
    frames = sorted(sim["frames"], key=lambda f: f["mjd"])
    found = detect.detect(detect.frames_from_encoded(frames, sx.decode_frame), ra, dec, size)
    for d in found["doodles"]:  # nothing to look up: these objects do not exist
        d["status"], d["known"], d["checked"] = "candidate", None, []
        d["simulated"] = True
        detect.explain(d)
        d["explain"] = d["explain"].split(" It did not match")[0].split(" The catalogue services")[0] + " (Simulated object: it was put into this made-up field on purpose.)"
    bands = [{"detector": k, **v, "count": len(frames) if k == 2 else 0, "visits": 4 if k == 2 else 0} for k, v in sx.BANDS.items()]
    return {
        "slug": ex["slug"], "title": ex["title"], "blurb": ex["blurb"], "story": ex.get("story", ""), "simulated": True,
        "target": {"name": ex["name"], "ra": ra, "dec": dec}, "band": 2, "size": size, "mode": ex.get("mode", "blink"),
        "a": frames[0]["id"], "b": frames[4]["id"], "settings": ex.get("settings", {}),
        "search": {"ra": ra, "dec": dec, "total": len(frames), "deep": False, "bands": bands, "visits": api._visits([{"mjd": f["mjd"], "detector": 2} for f in frames]), "collections": [], "stale": False, "saved_on": None},
        "total_in_band": len(frames), "frames": frames, "doodles": found["doodles"], "align": found["align"], "detect_stats": found["stats"],
        "checked": {"skybot": None, "simbad": None, "horizons": False}, "truth": sim["truth"],
        "generated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "source": "SIMULATED — not NASA data",
    }


def build(ex: dict) -> dict:
    if ex.get("simulated"):
        return build_simulated(ex)
    ex = apply_candidate(ex)
    ra, dec, band, size = round(ex["ra"], 5), round(ex["dec"], 5), int(ex["band"]), float(ex["size"])
    path = OUT / f"{ex['slug']}.json"
    old = json.loads(path.read_text()) if path.exists() else None
    try:
        search = api.api_search(ra, dec)
        if search.get("from_index") and old:  # IRSA is down: the list saved in the bundle is the exact one, keep it
            raise RuntimeError("IRSA search unavailable")
        exposures = {e["id"]: e for e in sx.search_exposures(ra, dec)}
        listed = sx.list_frames(ra, dec, band)
        chosen = pick_frames(listed, ex.get("frames"))
    except Exception as exc:  # noqa: BLE001 - IRSA's search is down: rebuild from the exposure list we already saved
        if not old:
            raise
        print(f"  ({ex['slug']}: IRSA search unavailable ({type(exc).__name__}); reusing the saved exposure list, pixels re-read from AWS)")
        search = old["search"]
        exposures = {f["id"]: {"id": f["id"], "obs_id": f["obs_id"], "detector": f["detector"], "collection": f["collection"],
                               "key": f["irsa_url"].split("/ibe/data/spherex/", 1)[1], "mjd": f["mjd"], "exptime": f["exptime"]} for f in old["frames"]}
        listed = [None] * old.get("total_in_band", len(old["frames"]))
        chosen = [{"id": f["id"]} for f in old["frames"]]
    if len(chosen) < 2:
        raise SystemExit(f"{ex['slug']}: fewer than two frames — not a usable example")

    with ThreadPoolExecutor(8) as pool:
        frames = list(pool.map(lambda f: sx.get_frame(exposures[f["id"]], ra, dec, size), chosen))
    frames = [f for f in frames if f["coverage"] >= ex.get("min_coverage", 0.6)]
    frames.sort(key=lambda f: f["mjd"])
    ids = {f["id"] for f in frames}
    for key in ("a", "b"):
        if ex.get(key) and ex[key] not in ids:
            raise SystemExit(f"{ex['slug']}: frame {key}={ex[key]} is not in the bundle")

    # Catalogued movers at the moment of each frame: the object's JPL Horizons position (found by
    # scripts/find_movers.py) plus anything else SkyBoT knows in the field that is bright enough to see.
    known = {}
    if ex.get("predicted") or ex.get("known"):
        for f in frames:
            objs = []
            pred = (ex.get("predicted") or {}).get(f["id"])
            if pred:
                objs.append({"name": ex["object_label"], "number": None, "ra": pred[0], "dec": pred[1], "source": "JPL Horizons"})
            try:
                for o in skybot.cone(ra, dec, size, f["mjd"]):
                    # SkyBoT's own entry for the same body can sit up to its 120" error filter away
                    if not pred or separation_arcsec(o["ra"], o["dec"], pred[0], pred[1]) > 120:
                        objs.append({**o, "source": "IMCCE SkyBoT"})
            except skybot.SkybotError as exc:
                print(f"  (SkyBoT unavailable for {f['id']}: {exc})")
            known[f["id"]] = objs

    # Sky Doodles: automatic change detection on exactly these frames, then catalogue cross-checks
    found = detect.detect(detect.frames_from_encoded(frames, sx.decode_frame), ra, dec, size)
    found["checked"] = catalogs.annotate(found["doodles"], ra, dec, size, predicted=ex.get("predicted"), label=ex.get("object_label"), kind=ex.get("object_kind"))
    found["dismissed"] = [d["dismissed"] for d in found["doodles"] if d.get("dismissed")]
    found["doodles"] = [d for d in found["doodles"] if not d.get("dismissed")]

    bundle = {
        "slug": ex["slug"],
        "title": ex["title"],
        "blurb": ex["blurb"],
        "story": ex.get("story", ""),
        "target": {"name": ex["name"], "ra": ra, "dec": dec},
        "band": band,
        "size": size,
        "mode": ex.get("mode", "blink"),
        "depth": ex.get("depth"),  # "visit": open with each visit's exposures added together
        "a": ex.get("a"),
        "b": ex.get("b"),
        "settings": ex.get("settings", {}),
        "search": search,
        "total_in_band": len(listed),
        "frames": frames,
        "doodles": found["doodles"],
        "align": found["align"],
        "detect_stats": found["stats"],
        "checked": found["checked"],
        "dismissed": found["dismissed"],
        "expected": catalogs.expected_movers(found["doodles"], ra, dec, size, sum(f["mjd"] for f in frames) / len(frames)),
        "generated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "NASA/IPAC IRSA SPHEREx Level-2 spectral images (collections spherex_dr1, spherex_qr3)",
    }
    try:  # Gaia stars of the field, so the catalogue overlay also works when the catalogue service does not
        bundle["gaia"] = [{k: (round(v, 6) if isinstance(v, float) and k in ("ra", "dec") else v) for k, v in s.items()} for s in gaia.cone(ra, dec, size)]
    except gaia.GaiaError as exc:
        print(f"  (Gaia catalogue unavailable for {ex['slug']}: {exc})")
    if known:
        bundle["known"] = known
        bundle["known_default"] = bool(ex.get("known_default", False))
    return bundle


def main() -> None:
    defs = json.loads(DEFS.read_text())
    want = sys.argv[1:]
    OUT.mkdir(parents=True, exist_ok=True)
    for ex in defs:
        path = OUT / f"{ex['slug']}.json"
        if want and not any(w in ex["slug"] for w in want):
            continue
        bundle = build(ex)
        path.write_text(json.dumps(bundle, separators=(",", ":"), allow_nan=False))
        f0, f1 = bundle["frames"][0], bundle["frames"][-1]
        print(f"{ex['slug']:24s} {len(bundle['frames']):3d} frames  {f0['date_obs'][:10]} → {f1['date_obs'][:10]}  {path.stat().st_size/1024:.0f} kB")
    index = []
    for e in defs:
        f = OUT / f"{e['slug']}.json"
        if not f.exists():
            continue
        t = json.loads(f.read_text())["target"]
        index.append({"slug": e["slug"], "title": e["title"], "blurb": e["blurb"], "kind": e.get("kind", ""), "group": e.get("group", "more"), "simulated": bool(e.get("simulated")),
                      "ra": t["ra"], "dec": t["dec"], "label": e.get("object_label") or e["title"]})
    (OUT / "index.json").write_text(json.dumps(index, indent=1))
    print("index:", [e["slug"] for e in index])


if __name__ == "__main__":
    main()
