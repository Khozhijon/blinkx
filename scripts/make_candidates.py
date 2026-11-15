"""Build scripts/mover_candidates.json from the hit lists made by find_movers.py.

Each entry in SELECTIONS names a hits file, the object, a band and a time range; this script
re-renders the frames around one fixed sky centre (verify_mover.verify), keeps only frames where
the object is inside the field, and records the measured evidence that it is really there.

Usage:  python scripts/make_candidates.py
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from verify_mover import verify  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "spike" / "out"

SELECTIONS = [
    {
        "slug": "vesta",
        "title": "Asteroid (4) Vesta crossing a star field",
        "kind": "asteroid",
        "hits": "hits_vesta.json",
        "command": "4;",
        "band": 2,
        "from": "2026-07-16T18",
        "to": "2026-07-17T05",
        "size_deg": 0.15,
        "notes": "Brightest asteroid in the sky. Three visits about 3 h and 6.5 h apart; within each visit the "
        "four exposures are 2 min apart, so Vesta barely moves inside a visit and jumps between visits.",
    },
    {
        "slug": "3i-atlas",
        "title": "Interstellar comet 3I/ATLAS streaking past the stars",
        "kind": "comet",
        "hits": "hits_3i.json",
        "command": "DES=C/2025 N1;",
        "band": 2,
        "from": "2025-12-14T04",
        "to": "2025-12-14T08",
        "size_deg": 0.2,
        "hi": 40.0,
        "notes": "Third known interstellar object, five days before its closest approach to Earth. Fuzzy coma with a "
        "faint extension towards the east (left); three visits one SPHEREx orbit (about 97 min) apart. It moves "
        "about 6 arcsec (one SPHEREx pixel) even between exposures 2 min apart.",
    },
    {
        "slug": "3i-atlas-co2",
        "title": "3I/ATLAS lights up in carbon dioxide (4.26 µm)",
        "kind": "comet",
        "hits": "hits_3i.json",
        "command": "DES=C/2025 N1;",
        "band": 5,
        "from": "2025-12-14T04",
        "to": "2025-12-14T08",
        "size_deg": 0.2,
        "hi": 40.0,
        "notes": "Same twelve exposures as the D2 field, seen by detector 5. Each exposure samples a different "
        "wavelength at the comet; it is a faint dot at 3.96-4.18 um and a huge glowing coma at 4.21-4.32 um, "
        "the CO2 emission band. The brightness change here is colour, not time.",
    },
    {
        "slug": "psyche",
        "title": "Spot the asteroid: (16) Psyche among the stars of Taurus",
        "kind": "asteroid",
        "hits": "hits_psyche.json",
        "command": "16;",
        "band": 3,
        "from": "2025-09-09T07",
        "to": "2025-09-09T14",
        "size_deg": 0.1,
        "notes": "Metal-rich asteroid and target of NASA's Psyche mission, magnitude 11: it looks exactly like a "
        "star until you blink the frames. Three visits over 6.6 h (07:03-07:07, 11:56, 13:30-13:37 UTC); in the "
        "first visit it sits right beside a field star.",
    },
]


def build(sel: dict) -> dict | None:
    path = OUT / sel["hits"]
    if not path.exists():
        print(f"skip {sel['slug']}: {path.name} missing")
        return None
    res = json.loads(path.read_text())[sel["command"]]
    hits = [h for h in res["hits"] if h["detector"] == sel["band"] and sel["from"] <= h["date_obs"] <= sel["to"]]
    if sel.get("ids"):
        hits = [h for h in hits if h["id"] in sel["ids"]]
    if len(hits) < 2:
        print(f"skip {sel['slug']}: only {len(hits)} frames")
        return None
    v = verify(hits, sel["size_deg"], sel["slug"], centre=sel.get("centre"), title=f"{res['name']}  SPHEREx D{sel['band']}", hi=sel.get("hi", 150.0))
    keep = [(h, r) for h, r in zip(hits, v["report"]) if r["in_field"] and r["coverage"] > 0.5]
    hits = [h for h, _ in keep]
    a, b = hits[0], hits[-1]
    sep = math.hypot((b["ra"] - a["ra"]) * math.cos(math.radians(a["dec"])), b["dec"] - a["dec"]) * 3600
    hours = (b["mjd"] - a["mjd"]) * 24
    vm = [h["vmag"] for h in hits if h.get("vmag") is not None]
    return {
        "slug": sel["slug"],
        "title": sel["title"],
        "kind": sel["kind"],
        "object": res["name"],
        "horizons_command": sel["command"],
        "ra": v["centre"][0],
        "dec": v["centre"][1],
        "size_deg": sel["size_deg"],
        "band": sel["band"],
        "frames": [h["id"] for h in hits],
        "predicted": {h["id"]: [h["ra"], h["dec"]] for h in hits},
        "dates": {h["id"]: h["date_obs"] for h in hits},
        "motion_arcsec_per_hour": round(sep / hours, 1) if hours > 0 else None,
        "total_motion_arcsec": round(sep, 1),
        "span_hours": round(hours, 2),
        "vmag": round(sum(vm) / len(vm), 1) if vm else None,
        "vmag_source": "JPL Horizons T-mag (predicted total magnitude)" if sel["kind"] == "comet" else "JPL Horizons apparent V magnitude",
        "evidence": [
            {k: r.get(k) for k in ("id", "peak_sigma_here", "peak_sigma_same_spot_other_frames")} for _, r in keep
        ],
        "contact_sheet": str(Path(v["sheet"]).relative_to(ROOT)),
        "notes": sel["notes"],
    }


def main():
    out = [c for c in (build(s) for s in SELECTIONS) if c]
    path = ROOT / "scripts" / "mover_candidates.json"
    path.write_text(json.dumps(out, indent=1))
    for c in out:
        print(f"{c['slug']}: {len(c['frames'])} frames, {c['total_motion_arcsec']}\" in {c['span_hours']} h, centre {c['ra']} {c['dec']}")
    print("wrote", path)


if __name__ == "__main__":
    main()
