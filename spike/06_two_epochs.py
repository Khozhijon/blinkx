"""DATA SPIKE: list SPHEREx epochs for one position and save two aligned cutouts from different dates.

Usage: python spike/06_two_epochs.py [ra dec [detector]]
"""
import sys, time, io, warnings
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend import spherex as sx
warnings.simplefilter("ignore")

ra, dec = (float(sys.argv[1]), float(sys.argv[2])) if len(sys.argv) > 2 else (269.44855, 4.73900)
det = int(sys.argv[3]) if len(sys.argv) > 3 else 2
out = Path(__file__).parent / "out"; out.mkdir(exist_ok=True)

t = time.time(); exps = sx.search_exposures(ra, dec)
print(f"SIA: {len(exps)} exposures cover RA={ra} Dec={dec}  ({time.time()-t:.1f}s)")
by = {}
for e in exps: by.setdefault(e["detector"], []).append(e)
print("per detector:", {f"D{k}": len(v) for k, v in sorted(by.items())})

t = time.time(); frames = sx.list_frames(ra, dec, det, exps)
print(f"D{det}: {len(frames)} exposures really contain the target pixel ({time.time()-t:.1f}s)")
for f in frames:
    print(f"  {f['date_obs'][:19]}  {f['wavelength_um']:.4f} um  pix=({f['pixel'][0]:7.1f},{f['pixel'][1]:7.1f})  {f['collection']}  {f['id']}")

# pick the pair from different visits (>60 d apart) with the closest wavelengths
best = None
for a in frames:
    for b in frames:
        if b["mjd"] - a["mjd"] > 60:
            d = abs(a["wavelength_um"] - b["wavelength_um"])
            if best is None or d < best[0]: best = (d, a, b)
_, a, b = best
print(f"\nchosen pair: {a['date_obs'][:10]} ({a['wavelength_um']:.3f} um)  vs  {b['date_obs'][:10]} ({b['wavelength_um']:.3f} um)")
ex = {e["id"]: e for e in exps}
from PIL import Image
for tag, f in (("A", a), ("B", b)):
    t = time.time(); enc = sx.get_frame(ex[f["id"]], ra, dec, 0.1)
    png = sx.frame_to_png(enc)
    name = out / f"barnard_{tag}_{f['date_obs'][:10]}.png"
    Image.open(io.BytesIO(png)).resize((512, 512), Image.NEAREST).save(name)
    print(f"  {tag}: {name.name}  DATE-OBS={enc['date_obs']}  wl={enc['wavelength_um']:.4f}um  sky={enc['sky']:.4f} MJy/sr  sigma={enc['sigma']:.4g}  coverage={enc['coverage']}  ({time.time()-t:.1f}s)")
