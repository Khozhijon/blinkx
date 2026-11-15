"""Probe which SPHEREx SIA2 collections return results at a test position."""
import sys, time
import pyvo
from astropy.coordinates import SkyCoord
import astropy.units as u

ra, dec = (float(sys.argv[1]), float(sys.argv[2])) if len(sys.argv) > 2 else (269.452, 4.693)  # Barnard's Star
svc = pyvo.dal.SIA2Service("https://irsa.ipac.caltech.edu/SIA")
pos = SkyCoord(ra, dec, unit="deg")
for coll in ["spherex_qr3", "spherex_qr3_deep", "spherex_dr1", "spherex_dr1_deep", "spherex_qr2", "spherex_qr2_deep", "spherex_qr", "spherex_qr_deep"]:
    t = time.time()
    try:
        res = svc.search(pos=(pos, 0.01 * u.deg), collection=coll)
        tab = res.to_table()
        print(f"{coll:20s} rows={len(tab):5d}  t={time.time()-t:.1f}s")
        if len(tab) and coll in ("spherex_qr3", "spherex_dr1"):
            print("  columns:", tab.colnames)
            tab.sort("t_min")
            for row in tab[:3]:
                print("  ", {k: (row[k].item() if hasattr(row[k], "item") else row[k]) for k in tab.colnames})
            print("  t_min range (MJD):", tab["t_min"].min(), tab["t_max"].max())
    except Exception as e:
        print(f"{coll:20s} ERROR {type(e).__name__}: {str(e)[:200]}  t={time.time()-t:.1f}s")
