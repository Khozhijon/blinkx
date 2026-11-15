"""A simulated SPHEREx-style field. NOT REAL DATA.

Used for two things only, and always labelled as simulated:

* tests of the change detection (we know exactly what was put in);
* the offline demo that shows all five doodle types at once, including the zigzag of a very
  distant planet, which nobody has found in real SPHEREx data.

The frames have the same format as real ones (``spherex.encode_frame``), so the whole app, and the
same detection code, runs on them unchanged.
"""
from __future__ import annotations

import math

import numpy as np
from astropy.time import Time

from . import spherex as sx

FWHM_ARCSEC = 7.4  # typical SPHEREx image sharpness


def _blob(img, x, y, flux, sigma_px):
    n = img.shape[0]
    r = int(math.ceil(5 * sigma_px))
    x0, x1, y0, y1 = max(0, int(x) - r), min(n, int(x) + r + 1), max(0, int(y) - r), min(n, int(y) + r + 1)
    if x0 >= x1 or y0 >= y1:
        return
    yy, xx = np.mgrid[y0:y1, x0:x1]
    img[y0:y1, x0:x1] += flux / (2 * math.pi * sigma_px**2) * np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (2 * sigma_px**2))


def planet_x_field(seed: int = 7, size_deg: float = 0.4, n: int | None = None, per_group: int = 3) -> dict:
    """Four visits six months apart with one of everything. Returns {"frames": [...], "truth": {...}}."""
    rng = np.random.default_rng(seed)
    n = n or sx.grid_size(size_deg)
    pix = size_deg * 3600 / n
    sig = FWHM_ARCSEC / 2.355 / pix
    noise = 0.02  # MJy/sr
    candidates = [(rng.uniform(8, n - 8), rng.uniform(8, n - 8), 10 ** rng.uniform(0.6, 2.6)) for _ in range(110)]
    # visits: mid-May and mid-November, 2025-2026; two groups of three exposures per visit
    visits = [60810.0, 60994.0, 61175.0, 61359.0]
    times = [v + g * 0.068 + k * 0.0015 for v in visits for g in range(2) for k in range(per_group)]
    c = n / 2

    def planet(t):  # 500 au: jumps 2 au / 500 au = 825" between visits, and drifts ~118"/yr
        k = min(range(4), key=lambda i: abs(visits[i] - t))
        side = 1 if k % 2 == 0 else -1
        yr = (t - visits[0]) / 365.25
        return c + side * (412.0 / pix) + 0.5 * 118.0 * yr / pix, c + 60 / pix - 0.86 * 118.0 * yr / pix, 2.2

    def fast_star(t):  # 8"/yr toward the north-east
        yr = (t - visits[0]) / 365.25
        return 0.27 * n - 5.7 * yr / pix, 0.3 * n - 5.7 * yr / pix, 60.0

    def asteroid(t):  # only during visit 2, 40"/h
        if abs(t - visits[1]) > 1:
            return None
        h = (t - visits[1]) * 24
        return 0.62 * n - 36.0 * h / pix, 0.78 * n - 17.0 * h / pix, 9.0

    def variable(t):  # brightens by 90% for visit 3
        return 0.78 * n, 0.24 * n, 14.0 * (1.9 if abs(t - visits[2]) < 1 else 1.0)

    def comet(t):  # fuzzy, only during visit 4, 55"/h
        if abs(t - visits[3]) > 1:
            return None
        h = (t - visits[3]) * 24
        return 0.2 * n + 48.0 * h / pix, 0.72 * n - 27.0 * h / pix, 30.0

    # keep the made-up stars off the paths of the made-up movers, so each one can be told apart
    path = [p for t in times for fn in (planet, fast_star, asteroid, variable, comet) if (p := fn(t))]
    stars = [st for st in candidates if min(math.hypot(st[0] - p[0], st[1] - p[1]) for p in path) > 16][:70]

    frames = []
    for i, t in enumerate(sorted(times)):
        img = np.zeros((n, n))
        wl = 1.45 + 0.02 * (i % (2 * per_group))
        colour = 1.0 + 0.15 * (wl - 1.5)  # every star a little different in each colour, like the real thing
        for x, y, f in stars:
            _blob(img, x, y, f * noise * 40 * colour, sig)
        for fn in (planet, fast_star, asteroid, variable):
            p = fn(t)
            if p:
                _blob(img, p[0], p[1], p[2] * noise * 40, sig)
        p = comet(t)
        if p:
            _blob(img, p[0], p[1], p[2] * noise * 40 * 0.35, sig)
            _blob(img, p[0] - 2.0 / pix * 6, p[1] + 1.0 / pix * 6, p[2] * noise * 40 * 0.65, sig * 3.2)  # coma + stubby tail
        img += rng.normal(0.3, noise, img.shape)
        iso = Time(t, format="mjd").isot
        meta = {
            "id": f"SIM{i:02d}D2", "obs_id": f"SIM{i:02d}", "detector": 2, "collection": "simulated", "band": "D2",
            "date_obs": iso, "date_avg": iso, "mjd": float(t), "exptime": 113.6, "wavelength_um": wl, "bandwidth_um": 0.03,
            "pixel": [1020.0, 1020.0], "on_detector": True, "psf_fwhm_arcsec": FWHM_ARCSEC, "quality": "Simulated", "pipeline_version": "simulated",
            "file": "simulated (not a NASA file)", "irsa_url": "", "n": n, "size_deg": size_deg, "pixscale_arcsec": round(pix, 4),
            "flags_used": False, "masked_fraction": 0.0, "coverage": 1.0, "unit": "MJy / sr", "simulated": True,
        }
        frames.append(sx.encode_frame({"image": img.astype(np.float32), "filled": np.zeros((n, n), bool), "meta": meta}))
    truth = {"planet_jump_arcsec": 825.0, "planet_distance_au": 500, "star_pm_arcsec_per_year": 8.06, "asteroid_arcsec_per_hour": 39.8, "comet_arcsec_per_hour": 55.1, "variable_change_pct": 90}
    return {"frames": frames, "truth": truth, "size_deg": size_deg, "n": n}
