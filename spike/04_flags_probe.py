import io, time, warnings, requests, numpy as np
from astropy.io import fits
warnings.simplefilter("ignore")
url = "https://irsa.ipac.caltech.edu/ibe/data/spherex/qr3/level2/2026W33_2A/l2b-v27-2026-241/3/level2_2026W33_2A_0594_4D3_spx_l2b-v27-2026-241.fits"
for attempt in range(6):
    r = requests.get(url, params={"center": "269.4486,4.7380", "size": "0.1"}, timeout=120)
    print("attempt", attempt, r.status_code, len(r.content), dict(r.headers).get("Retry-After"), r.content[:40] if len(r.content) < 100 else "")
    if r.status_code == 200 and r.content[:6] == b"SIMPLE":
        break
    time.sleep(3 * (attempt + 1))
open("spike/sample_cutout.fits", "wb").write(r.content)
hdul = fits.open(io.BytesIO(r.content))
h = hdul["FLAGS"].header
for c in h.cards:
    if c.keyword.startswith(("MP_", "FLAG", "BIT")) or "bit" in str(c.comment).lower():
        print(c.keyword, "=", c.value, "/", c.comment)
print("--- WCS-WAVE header"); print(repr(hdul["WCS-WAVE"].header))
print("--- tail of IMAGE header (W wcs)")
ih = hdul[1].header
for c in ih.cards[-36:]:
    print(str(c)[:110])
f = hdul["FLAGS"].data
vals, cnt = np.unique(f, return_counts=True)
print("flag values:", dict(zip(vals.tolist()[:20], cnt.tolist()[:20])))
print("ZODI med", np.nanmedian(hdul["ZODI"].data), "IMAGE med", np.nanmedian(hdul[1].data), "VAR med", np.nanmedian(hdul["VARIANCE"].data))
