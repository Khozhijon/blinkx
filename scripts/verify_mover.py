"""Render a contact sheet for a mover candidate and measure whether the object is really there.

For a run of exposures that should contain a solar-system object (from find_movers.py), cut every
frame around ONE fixed sky centre, mark the predicted position, and compare the brightness at the
predicted spot in "its" frame against the same sky position in the other frames.

Usage:
    python scripts/verify_mover.py spike/out/hits_a.json "4;" --band 2 --cluster 0 --size 0.2 --slug vesta
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import warnings
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from backend import spherex as sx  # noqa: E402
from find_movers import clusters  # noqa: E402

warnings.simplefilter("ignore")
OUT = Path(__file__).resolve().parent.parent / "spike" / "out"


def as_exposure(hit: dict) -> dict:
    return {"id": hit["id"], "obs_id": hit["id"][:-2], "detector": hit["detector"], "collection": hit["collection"],
            "key": hit["key"], "mjd": hit["mjd"], "exptime": 0.0}


def sky_to_grid(ra, dec, ra0, dec0, size_deg, n):
    """Pixel (x, y) on the north-up, east-left gnomonic grid used by sx.make_frame."""
    a, d, a0, d0 = (math.radians(v) for v in (ra, dec, ra0, dec0))
    cosc = math.sin(d0) * math.sin(d) + math.cos(d0) * math.cos(d) * math.cos(a - a0)
    xi = math.cos(d) * math.sin(a - a0) / cosc
    eta = (math.cos(d0) * math.sin(d) - math.sin(d0) * math.cos(d) * math.cos(a - a0)) / cosc
    step = math.radians(size_deg / n)
    c = (n - 1) / 2.0
    return c - xi / step, c - eta / step


def stretch(img, sigma, lo=-2.0, hi=150.0):
    t = np.arcsinh((img / sigma - lo) / 3.0) / math.asinh((hi - lo) / 3.0)
    return (np.clip(np.nan_to_num(t), 0, 1) * 255).astype(np.uint8)


def verify(hits: list[dict], size_deg: float, slug: str, centre=None, title="", hi=150.0):
    mid = hits[len(hits) // 2]
    if centre is None:
        ra0 = float(np.mean([hits[0]["ra"], hits[-1]["ra"]]))
        dec0 = float(np.mean([hits[0]["dec"], hits[-1]["dec"]]))
    else:
        ra0, dec0 = centre
    ra0, dec0 = round(ra0, 5), round(dec0, 5)
    frames = []
    for h in hits:
        enc = sx.get_frame(as_exposure(h), ra0, dec0, size_deg)
        img = sx.decode_frame(enc)
        x, y = sky_to_grid(h["ra"], h["dec"], ra0, dec0, size_deg, enc["n"])
        frames.append({"hit": h, "enc": enc, "img": img, "xy": (x, y)})
    n = frames[0]["enc"]["n"]
    pix = size_deg * 3600 / n
    rad = max(2.0, 13.0 / pix)  # ~2 SPHEREx pixels
    yy, xx = np.mgrid[0:n, 0:n]
    report = []
    for i, f in enumerate(frames):
        x, y = f["xy"]
        inside = 2 <= x <= n - 3 and 2 <= y <= n - 3
        row = {"id": f["hit"]["id"], "date_obs": f["enc"]["date_obs"], "in_field": bool(inside), "coverage": f["enc"]["coverage"]}
        if inside:
            m = (xx - x) ** 2 + (yy - y) ** 2 <= rad ** 2
            here = float(np.nanmax(f["img"][m] / f["enc"]["sigma"])) if np.isfinite(f["img"][m]).any() else float("nan")
            others = []
            for j, g in enumerate(frames):
                if j == i:
                    continue
                gx, gy = g["xy"]
                if math.hypot(gx - x, gy - y) < 2.5 * rad:  # the object has not moved away yet in that frame
                    continue
                v = g["img"][m] / g["enc"]["sigma"]
                if np.isfinite(v).any():
                    others.append(float(np.nanmax(v)))
            row["peak_sigma_here"] = round(here, 1)
            row["peak_sigma_same_spot_other_frames"] = round(float(np.median(others)), 1) if others else None
            row["n_other"] = len(others)
        report.append(row)

    # contact sheet
    S = 256
    cols = min(len(frames), 5)
    rows = math.ceil(len(frames) / cols)
    sheet = Image.new("RGB", (cols * (S + 8) + 8, rows * (S + 30) + 40), (12, 14, 22))
    dr = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 13)
    except Exception:  # noqa: BLE001
        font = ImageFont.load_default()
    dr.text((8, 6), f"{title or slug}  centre RA {ra0} Dec {dec0}  field {size_deg*60:.1f}'  N up, E left; circle = Horizons prediction", fill=(230, 235, 245), font=font)
    for i, f in enumerate(frames):
        cx, cy = 8 + (i % cols) * (S + 8), 30 + (i // cols) * (S + 30)
        im = Image.fromarray(stretch(f["img"], f["enc"]["sigma"], hi=hi)).convert("RGB").resize((S, S), Image.BICUBIC)
        sheet.paste(im, (cx, cy))
        x, y = f["xy"]
        k = S / n
        r = max(7, rad * k * 1.4)
        dr.ellipse([cx + (x + 0.5) * k - r, cy + (y + 0.5) * k - r, cx + (x + 0.5) * k + r, cy + (y + 0.5) * k + r], outline=(255, 170, 40), width=1)
        wl = f["enc"].get("wavelength_um")
        dr.text((cx + 2, cy + S + 3), f"{f['enc']['date_obs'][:16]}  {wl:.2f}um" if wl else f["enc"]["date_obs"][:16], fill=(190, 200, 215), font=font)
    path = OUT / f"mover_{slug}.png"
    sheet.save(path)
    return {"centre": [ra0, dec0], "size_deg": size_deg, "n": n, "sheet": str(path), "report": report}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("hits_json")
    ap.add_argument("command")
    ap.add_argument("--band", type=int, required=True)
    ap.add_argument("--cluster", type=int, default=0, help="index among clusters with >=3 exposures")
    ap.add_argument("--size", type=float, default=0.2)
    ap.add_argument("--slug", default="candidate")
    ap.add_argument("--first", type=int, default=0)
    ap.add_argument("--count", type=int, default=10)
    ap.add_argument("--gap", type=float, default=30.0)
    ap.add_argument("--hi", type=float, default=150.0)
    a = ap.parse_args()
    res = json.loads(Path(a.hits_json).read_text())[a.command]
    cl = [c for c in clusters(res["hits"], a.band, a.gap) if len(c) >= 3][a.cluster][a.first : a.first + a.count]
    out = verify(cl, a.size, a.slug, title=res["name"], hi=a.hi)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
