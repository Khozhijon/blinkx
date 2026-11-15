"""Spike result figure: two real SPHEREx epochs of Barnard's Star + their difference."""
import sys, io, math, warnings
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
warnings.simplefilter("ignore")
from PIL import Image, ImageDraw, ImageFont
from backend import spherex as sx

ra, dec, det, size = 269.44840, 4.76800, 2, 0.06     # Barnard's Star near its 2026 position
exps = sx.search_exposures(ra, dec)
frames = sx.list_frames(ra, dec, det, exps)
ex = {e["id"]: e for e in exps}
best = min(((abs(a["wavelength_um"] - b["wavelength_um"]), a["id"], b["id"]) for a in frames for b in frames if b["mjd"] - a["mjd"] > 300))
a = sx.get_frame(ex[best[1]], ra, dec, size); b = sx.get_frame(ex[best[2]], ra, dec, size)
ia, ib = sx.decode_frame(a), sx.decode_frame(b)

def stretch(img, sigma, lo=-2, hi=400):
    t = np.arcsinh((img / sigma - lo) / 3) / math.asinh((hi - lo) / 3)
    return (np.clip(np.nan_to_num(t), 0, 1) * 255).astype(np.uint8)

m = (ia > 20 * a["sigma"]) & (ib > 20 * b["sigma"])
scale = float((ia[m] * ib[m]).sum() / (ia[m] ** 2).sum())
d = ib - scale * ia
lim = 60 * b["sigma"]
t = np.clip(np.nan_to_num(d) / lim, -1, 1)
rgb = np.zeros(d.shape + (3,), np.uint8)
rgb[..., 0] = (np.clip(t, 0, 1) * 255 + np.clip(-t, 0, 1) * 40).astype(np.uint8)
rgb[..., 1] = (np.clip(t, 0, 1) * 150 + np.clip(-t, 0, 1) * 150).astype(np.uint8)
rgb[..., 2] = (np.clip(t, 0, 1) * 30 + np.clip(-t, 0, 1) * 255).astype(np.uint8)

S = 384
panels = [Image.fromarray(stretch(ia, a["sigma"])).convert("RGB"), Image.fromarray(stretch(ib, b["sigma"])).convert("RGB"), Image.fromarray(rgb)]
labels = [f"A  {a['date_obs'][:10]}   {a['wavelength_um']:.3f} um", f"B  {b['date_obs'][:10]}   {b['wavelength_um']:.3f} um", "B - A   (orange = new, blue = gone)"]
canvas = Image.new("RGB", (3 * S + 4 * 12, S + 70), (12, 14, 22))
dr = ImageDraw.Draw(canvas)
try: font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 17)
except Exception: font = ImageFont.load_default()
for i, (im, lab) in enumerate(zip(panels, labels)):
    x = 12 + i * (S + 12)
    canvas.paste(im.resize((S, S), Image.BICUBIC), (x, 40))
    dr.text((x, 12), lab, fill=(235, 238, 245), font=font)
dr.text((12, S + 46), f"SPHEREx band D{det}, {size*60:.1f}' field, north up. Real DATE-OBS from FITS headers. Barnard's Star moves 10.4\"/yr.", fill=(150, 160, 180), font=font)
out = Path(__file__).parent / "out" / "spike_barnard.png"
canvas.save(out)
print("saved", out, "| A", a["date_obs"], "| B", b["date_obs"], "| flux scale", round(scale, 3))
