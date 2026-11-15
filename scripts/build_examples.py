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
from backend import skybot, spherex as sx  # noqa: E402

OUT = ROOT / "frontend" / "examples"
DEFS = ROOT / "scripts" / "examples.json"


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


def build(ex: dict) -> dict:
    ra, dec, band, size = round(ex["ra"], 5), round(ex["dec"], 5), int(ex["band"]), float(ex["size"])
    search = api.api_search(ra, dec)
    exposures = {e["id"]: e for e in sx.search_exposures(ra, dec)}
    listed = sx.list_frames(ra, dec, band)
    chosen = pick_frames(listed, ex.get("frames"))
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

    known = {}
    if ex.get("known"):
        for f in frames:
            objs = skybot.cone(ra, dec, size, f["mjd"])
            keep = ex.get("known_names")
            known[f["id"]] = [o for o in objs if not keep or o["name"] in keep]

    bundle = {
        "slug": ex["slug"],
        "title": ex["title"],
        "blurb": ex["blurb"],
        "story": ex.get("story", ""),
        "target": {"name": ex["name"], "ra": ra, "dec": dec},
        "band": band,
        "size": size,
        "mode": ex.get("mode", "blink"),
        "a": ex.get("a"),
        "b": ex.get("b"),
        "search": search,
        "total_in_band": len(listed),
        "frames": frames,
        "generated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "NASA/IPAC IRSA SPHEREx Level-2 spectral images (collections spherex_dr1, spherex_qr3)",
    }
    if known:
        bundle["known"] = known
        bundle["known_default"] = True
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
    index = [{"slug": e["slug"], "title": e["title"], "blurb": e["blurb"], "kind": e.get("kind", "")} for e in defs if (OUT / f"{e['slug']}.json").exists()]
    (OUT / "index.json").write_text(json.dumps(index, indent=1))
    print("index:", [e["slug"] for e in index])


if __name__ == "__main__":
    main()
