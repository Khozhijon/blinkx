"""Can we read just the header + a few rows straight from the public AWS bucket?"""
import time, requests, numpy as np, warnings
from astropy.io import fits
warnings.simplefilter("ignore")
key = "qr3/level2/2026W33_2A/l2b-v27-2026-241/3/level2_2026W33_2A_0594_4D3_spx_l2b-v27-2026-241.fits"
url = "https://nasa-irsa-spherex.s3.amazonaws.com/" + key
s = requests.Session()
t = time.time(); r = s.head(url, timeout=30); print("HEAD", r.status_code, r.headers.get("Content-Length"), r.headers.get("Accept-Ranges"), "%.2fs" % (time.time() - t))
t = time.time(); r = s.get(url, headers={"Range": "bytes=0-40319"}, timeout=30); print("hdr", r.status_code, len(r.content), "%.2fs" % (time.time() - t))
raw = r.content
prim = fits.Header.fromstring(raw[:2880].decode("ascii"))
# find END of IMAGE header
pos = 2880
while True:
    block = raw[pos:pos + 2880]
    pos += 2880
    if any(block[i:i + 8] == b"END     " for i in range(0, 2880, 80)):
        break
hdr = fits.Header.fromstring(raw[2880:pos].decode("ascii"))
print("IMAGE header bytes", pos - 2880, "data offset", pos, "NAXIS", hdr["NAXIS1"], hdr["NAXIS2"], "BITPIX", hdr["BITPIX"], hdr.get("BSCALE"), hdr.get("ZIMAGE"))
print([ (k, hdr[k]) for k in hdr if k.endswith("W") and len(k) > 5][:40])
y0, y1 = 900, 960
t = time.time(); r = s.get(url, headers={"Range": f"bytes={pos + y0 * 2040 * 4}-{pos + y1 * 2040 * 4 - 1}"}, timeout=30)
print("rows", r.status_code, len(r.content), "%.2fs" % (time.time() - t))
a = np.frombuffer(r.content, dtype=">f4").reshape(y1 - y0, 2040)
print("rows median", np.nanmedian(a))
# IRSA on-prem range request support?
iu = "https://irsa.ipac.caltech.edu/ibe/data/spherex/" + key
t = time.time(); r = requests.get(iu, headers={"Range": "bytes=0-40319"}, timeout=60); print("IRSA range", r.status_code, len(r.content), "%.2fs" % (time.time() - t))
