"""Download one SPHEREx cutout and dump its structure + key header cards."""
import sys, time, io, warnings
import requests
from astropy.io import fits
from astropy.wcs import WCS
from astropy.coordinates import SkyCoord
import astropy.units as u
import numpy as np
warnings.simplefilter("ignore")

url = "https://irsa.ipac.caltech.edu/ibe/data/spherex/qr3/level2/2026W33_2A/l2b-v27-2026-241/3/level2_2026W33_2A_0594_4D3_spx_l2b-v27-2026-241.fits"
ra, dec = 269.4486, 4.7380   # Barnard's Star, roughly epoch 2026
t = time.time()
r = requests.get(url, params={"center": f"{ra},{dec}", "size": "0.1"}, timeout=120)
print("status", r.status_code, "bytes", len(r.content), "t=%.1fs" % (time.time() - t))
print("resp headers:", {k: v for k, v in r.headers.items() if k.lower() in ("content-type", "access-control-allow-origin", "content-length", "cache-control")})
hdul = fits.open(io.BytesIO(r.content))
hdul.info()
print("--- PRIMARY header")
print(repr(hdul[0].header))
print("--- IMAGE header")
print(repr(hdul[1].header))
img = hdul[1].data
print("image", img.shape, img.dtype, "min/med/max", np.nanmin(img), np.nanmedian(img), np.nanmax(img))
for i in range(2, len(hdul)):
    h = hdul[i]
    print(i, h.name, None if h.data is None else (h.data.shape, h.data.dtype), h.header.get("BUNIT"))
coord = SkyCoord(ra, dec, unit="deg")
w = WCS(hdul[1].header)
x, y = w.world_to_pixel(coord)
print("target pixel in cutout:", x, y)
sw = WCS(hdul[1].header, fobj=hdul, key="W")
sw.sip = None
wl, bw = sw.pixel_to_world(x, y)
print("wavelength at target:", wl.to(u.um), "bandwidth:", bw.to(u.um))
