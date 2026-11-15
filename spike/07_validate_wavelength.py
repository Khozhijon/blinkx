"""Check our hand-written WAVE-TAB lookup and resampling against astropy on a real IRSA cutout."""
import sys, io, warnings
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
warnings.simplefilter("ignore")
from astropy.io import fits
from astropy.wcs import WCS
from astropy.coordinates import SkyCoord
import astropy.units as u
from backend import spherex as sx

ra, dec = 269.4486, 4.7380
key = "qr3/level2/2026W33_2A/l2b-v27-2026-241/3/level2_2026W33_2A_0594_4D3_spx_l2b-v27-2026-241.fits"
hdul = fits.open(Path(__file__).parent / "sample_cutout.fits")   # cut by IRSA's cutout service
h = hdul[1].header
x, y = WCS(h).world_to_pixel(SkyCoord(ra, dec, unit="deg"))
sw = WCS(h, fobj=hdul, key="W"); sw.sip = None
wl_ref, bw_ref = sw.pixel_to_world(x, y)
print("astropy on IRSA cutout :", wl_ref.to(u.um), bw_ref.to(u.um), " DATE-OBS", h["DATE-OBS"])

exp = {"id": "t", "obs_id": "t", "detector": 3, "collection": "spherex_qr3", "key": key, "mjd": 0, "exptime": 0}
m = sx.read_exposure_meta(exp, ra, dec)
print("ours via AWS full frame :", m["wavelength_um"], m["bandwidth_um"], " DATE-OBS", m["date_obs"], "pix", m["pixel"])
assert abs(m["wavelength_um"] - wl_ref.to_value(u.um)) < 1e-4, "wavelength mismatch"
assert m["date_obs"] == h["DATE-OBS"]

# pixel check: the IRSA cutout pixel nearest the target must equal the full-frame pixel we read from AWS
eh = sx.read_header(key)
fx, fy = m["pixel"]
row = sx._read_rows(key, eh.data_offset, eh.nx, int(round(fy)), int(round(fy)) + 1, ">f4")
print("pixel value  IRSA cutout:", hdul[1].data[int(round(float(y))), int(round(float(x)))], " AWS full frame:", row[0, int(round(fx))])
assert np.isclose(hdul[1].data[int(round(float(y))), int(round(float(x)))], row[0, int(round(fx))])
print("OK: wavelength, date and pixel values agree")
