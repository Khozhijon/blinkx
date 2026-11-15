"""Run change detection on saved example bundles and print what it finds: python scripts/try_detect.py [slug ...]"""
import json, sys, time, warnings
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
warnings.simplefilter("ignore")
from backend import detect, spherex as sx

slugs = sys.argv[1:] or ["3i-atlas", "vesta", "psyche", "barnards-star", "3i-atlas-co2"]
for slug in slugs:
    b = json.loads((ROOT / "frontend" / "examples" / f"{slug}.json").read_text())
    t = time.time()
    frames = detect.frames_from_encoded(b["frames"], sx.decode_frame)
    res = detect.detect(frames, b["target"]["ra"], b["target"]["dec"], b["size"])
    al = res["align"].values()
    print(f"== {slug}: {len(frames)} frames, {res['stats']} in {time.time()-t:.1f}s; align max offset {max(a['offset_arcsec'] for a in al):.2f}\" (stars {min(a['stars'] for a in al)}-{max(a['stars'] for a in al)})")
    for d in res["doodles"]:
        m = d.get("motion") or {}
        p0, p1 = d["points"][0], d["points"][-1]
        print(f"   {d['id']:9s} {d['type']:6s} conf={d['confidence']:.2f} sightings={d['sightings']} epochs={d['epochs']} peak={d['peak_sigma']:.0f}σ "
              f"({p0['x']:.0f},{p0['y']:.0f})→({p1['x']:.0f},{p1['y']:.0f}) "
              + (f"{m.get('dist_arcsec')}\" {m.get('direction')} {m.get('rate_arcsec_per_hour')}\"/h {m.get('rate_arcsec_per_year')}\"/yr rms={m.get('fit_rms_arcsec')}" if m else str(d.get('brightness'))))
    truth = b.get("known") or {}
    if truth:
        fid = b["frames"][0]["id"]; o = truth.get(fid, [{}])[0]
        if o: print("   truth first frame:", o.get("name"), [round(float(v), 1) for v in detect.sky_to_pix(o["ra"], o["dec"], b["target"]["ra"], b["target"]["dec"], b["size"], b["frames"][0]["n"])])
