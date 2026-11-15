"""List every SPHEREx exposure covering a position, grouped into visits."""
import sys, warnings
import pyvo, numpy as np
from astropy.coordinates import SkyCoord
from astropy.time import Time
import astropy.units as u
warnings.simplefilter("ignore")
ra, dec = float(sys.argv[1]), float(sys.argv[2])
svc = pyvo.dal.SIA2Service("https://irsa.ipac.caltech.edu/SIA")
pos = SkyCoord(ra, dec, unit="deg")
rows = []
for coll in ["spherex_dr1", "spherex_qr3", "spherex_dr1_deep", "spherex_qr3_deep"]:
    tab = svc.search(pos=(pos, 0.001 * u.deg), collection=coll).to_table()
    for r in tab:
        rows.append((float(r["t_min"]), str(r["energy_bandpassname"]), coll, str(r["obs_id"]), str(r["access_url"])))
rows.sort()
print("total exposures:", len(rows))
last = None; grp = 0
for t, band, coll, obs, url in rows:
    if last is None or t - last > 20:
        grp += 1
        print(f"--- visit {grp} starts {Time(t, format='mjd').iso[:16]}")
    last = t
    print(f"  {Time(t, format='mjd').iso[:19]}  {band[-2:]}  {coll:12s} {obs}")
