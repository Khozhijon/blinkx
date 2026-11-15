"""The full SPHEREx spectrum of one object, made on the fly: its brightness in all six colour bands.

Every SPHEREx exposure sees a given spot of sky at one wavelength. During one visit (a couple of
weeks) the spot crosses all six detectors, so the exposures of a single visit add up to a complete
0.75-5.0 micron spectrum taken at one moment in the object's life. This module picks the visit with
the best coverage, cuts a small picture out of each exposure, and measures the brightness on the
object's spot (moved along with the object when it has a known drift).

Honesty rules built in:
- A band counts as "the object" only if, in that band's exposures added together, a source sits on
  the expected spot. Otherwise the numbers measured there are kept but marked: they are the sky or
  a neighbour inside the measuring circle, not the object.
- Brightness is a small-aperture sum (radius 1.5 SPHEREx pixels) without aperture correction.
"""
from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from . import cache, detect, spherex as sx

SIZE = 0.05  # degrees: a 3 arcminute cutout is plenty for one object and quick to read
PER_BAND = 24
VISIT_GAP_DAYS = 20.0
MAX_SPAN_DAYS = 30.0  # near the ecliptic poles SPHEREx never stops looking: there, take the best month
SWAMPED_MJY = 1000.0  # a star this bright fills the measuring circle, whatever its overloaded middle does to the centre found for it
ON_SPOT = 0.6  # SPHEREx pixels: how close a stacked source must sit to count as the object
SNAP = 1.0  # SPHEREx pixels: a spot pointed at by hand may be moved this far, onto the nearest source
JUMPY = 0.3  # more than this share of dots a quarter off their neighbours: not a spectrum to read closely
OVERLOAD_MJY = 2500.0  # above a few janskys the middle of a star overloads the detector
# where molecules in cool atmospheres absorb (microns): (window, left shoulder, right shoulder, what, verb)
DIPS = [
    ((1.36, 1.45), (1.24, 1.32), (1.56, 1.68), "1.4", "water vapour"),
    ((1.80, 1.98), (1.60, 1.70), (2.05, 2.20), "1.9", "water vapour"),
    ((3.15, 3.45), (2.85, 3.05), (3.85, 4.10), "3.3", "methane"),
]


def _iso(mjd: float) -> str:
    from astropy.time import Time

    return Time(mjd, format="mjd").isot[:10]


def _where(ra: float, dec: float, pm_e: float, pm_n: float, t0: float, mjd: float) -> tuple[float, float]:
    """The object's position at a given time: (ra, dec) at t0 plus its yearly drift (arcsec east, north)."""
    yr = (mjd - t0) / 365.25
    return ra + pm_e * yr / 3600.0 / max(math.cos(math.radians(dec)), 1e-6), dec + pm_n * yr / 3600.0


def _median(a: np.ndarray) -> float:
    return float(np.median(a)) if len(a) else float("nan")


def full_spectrum(ra: float, dec: float, pm_e: float = 0.0, pm_n: float = 0.0, t0: float | None = None, snap: bool = False) -> dict:
    """``snap``: the spot was pointed at by hand, so first move it onto the nearest source (at most one
    SPHEREx pixel away) and say so in the answer."""
    ck = f"fullspec10/{ra:.5f}_{dec:.5f}_{pm_e:.2f}_{pm_n:.2f}_{0 if t0 is None else round(t0)}_{int(bool(snap))}"
    hit = cache.get_json(ck, max_age=7 * 86400)
    if hit is not None:
        return hit
    listed = {det: sx.list_frames(ra, dec, det) for det in sx.BANDS}
    every = sorted((f for fs in listed.values() for f in fs if f.get("wavelength_um")), key=lambda f: f["mjd"])
    if len(every) < 12:
        return {"points": [], "hint": "SPHEREx has too few exposures of this spot for a spectrum."}
    # one visit: the one that covers the most bands, then has the most exposures we would use, then the latest
    visits, cur = [], [every[0]]
    for f in every[1:]:
        if f["mjd"] - cur[-1]["mjd"] > VISIT_GAP_DAYS:
            visits.append(cur)
            cur = []
        cur.append(f)
    visits.append(cur)
    visit = max((_best_month(v) for v in visits), key=_coverage)
    lo, hi = visit[0]["mjd"], visit[-1]["mjd"]
    if t0 is None:
        t0 = 0.5 * (lo + hi)
    exposures = {e["id"]: e for e in sx.search_exposures(ra, dec)}
    chosen: dict[int, list[dict]] = {}
    for det in sx.BANDS:
        fs = sorted((f for f in visit if f["detector"] == det and f["id"] in exposures), key=lambda f: f["wavelength_um"])
        if len(fs) > PER_BAND:
            step = len(fs) / PER_BAND
            fs = [fs[int(i * step)] for i in range(PER_BAND)]
        chosen[det] = fs
    flat = [f for fs in chosen.values() for f in fs]
    with ThreadPoolExecutor(8) as pool:
        encoded = list(pool.map(lambda f: sx.get_frame(exposures[f["id"]], ra, dec, SIZE), flat))
    by_id = {f["id"]: e for f, e in zip(flat, encoded)}

    loaded = {}  # band -> (its exposures, their pictures, the pictures added together)
    for det, fs in chosen.items():
        good = [(f, by_id[f["id"]]) for f in fs if by_id[f["id"]]["coverage"] >= 0.6]
        if good:
            frames = detect.frames_from_encoded([e for _, e in good], sx.decode_frame)
            loaded[det] = (good, frames, detect._stack(frames, list(range(len(frames)))) if len(frames) >= 3 else None)
    if not loaded:
        return {"points": [], "hint": "SPHEREx's pictures of that visit do not cover this spot well enough for a spectrum."}

    ora, odec, snapped = ra, dec, None  # where the object is at t0 (the cutouts stay centred on ra, dec)
    if snap:
        near = []  # (distance in SPHEREx pixels, peak, ra, dec) of the source nearest the spot, band by band
        for _, frames, stack in loaded.values():
            if stack is None or not len(stack.x):
                continue
            n, s = frames[0].img.shape[0], detect.NATIVE / frames[0].pix
            d = np.hypot(stack.x - (n - 1) / 2.0, stack.y - (n - 1) / 2.0)
            k = int(np.argmin(d))
            if d[k] <= SNAP * s and stack.peak[k] >= 6.0:
                a, b = detect.pix_to_sky(stack.x[k], stack.y[k], ra, dec, SIZE, n)
                near.append((float(d[k] / s), float(stack.peak[k]), float(a), float(b)))
        if near:
            d0, _, a0, b0 = min(near)  # the closest one decides which source is meant; bands that see the same one sharpen it
            cosd = max(math.cos(math.radians(dec)), 1e-6)
            same = [q for q in near if math.hypot((q[2] - a0) * cosd, q[3] - b0) * 3600.0 <= 0.5 * detect.NATIVE]
            w = np.array([q[1] for q in same])
            ora, odec = float(np.sum(w * np.array([q[2] for q in same])) / w.sum()), float(np.sum(w * np.array([q[3] for q in same])) / w.sum())
            snapped = round(math.hypot((ora - ra) * cosd, odec - dec) * 3600.0, 1)

    points, bands, neighbour = [], [], None
    for det, (good, frames, stack) in loaded.items():
        n, pix = frames[0].img.shape[0], frames[0].pix
        s = detect.NATIVE / pix
        to_mjy = 1e9 * (pix / 206264.8) ** 2
        # is something sitting on the object's spot in this band? look in the exposures added together
        on_spot, sep_other = False, None
        if stack is not None:
            x0, y0 = (float(v) for v in detect.sky_to_pix(*_where(ora, odec, pm_e, pm_n, t0, stack.mjd), ra, dec, SIZE, n))
            if len(stack.x):
                d = np.hypot(stack.x - x0, stack.y - y0)
                k = int(np.argmin(d))
                on_spot = bool(d[k] <= ON_SPOT * s and stack.peak[k] >= 6.0)
                if not on_spot and d[k] * pix < 20.0:
                    sep_other = round(float(d[k] * pix), 1)
        else:  # too few exposures to add up: judge on the single exposures
            hits = 0
            for fr in frames:
                detect.find_sources(fr)
                x0, y0 = (float(v) for v in detect.sky_to_pix(*_where(ora, odec, pm_e, pm_n, t0, fr.mjd), ra, dec, SIZE, n))
                hits += int(len(fr.x) > 0 and float(np.min(np.hypot(fr.x - x0, fr.y - y0))) <= ON_SPOT * s)
            on_spot = hits >= max(1, len(frames) // 2)
        by_frame = {fr.id: fr for fr in frames}  # frames_from_encoded returns them in time order, not ours
        got = []
        for f, _ in good:
            fr = by_frame[f["id"]]
            x, y = (float(v) for v in detect.sky_to_pix(*_where(ora, odec, pm_e, pm_n, t0, fr.mjd), ra, dec, SIZE, n))
            v = float(detect.forced_flux(fr, np.array([x]), np.array([y]))[0])
            if math.isfinite(v):
                got.append((f, v * to_mjy, fr.sigma * s * s * math.sqrt(math.pi * 1.5**2) * to_mjy))  # noise: roughly that of so many SPHEREx pixels
        if not got:
            continue
        if not on_spot and sep_other is not None and sep_other <= 1.6 * detect.NATIVE and _median(np.array([v for _, v, _ in got])) >= SWAMPED_MJY:
            on_spot, sep_other = True, None  # an overloaded star: its knocked-out middle shifts the centre found for it, but the light is its own
        if sep_other is not None and (neighbour is None or sep_other < neighbour):
            neighbour = sep_other
        wl = [f["wavelength_um"] for f, _, _ in got]
        bands.append({"band": det, "range_um": [round(min(wl), 3), round(max(wl), 3)], "exposures": len(got), "on_spot": on_spot})
        for f, v, err in got:
            points.append({"wl": round(f["wavelength_um"], 4), "mjy": float(f"{v:.4g}"), "err": float(f"{err:.2g}"), "band": det, "frame": f["id"], "ours": on_spot})
    points.sort(key=lambda p: p["wl"])
    out = {
        "unit": "mJy", "aperture_arcsec": round(1.5 * detect.NATIVE, 1), "points": points, "bands": bands,
        "visit": {"first": _iso(lo), "last": _iso(hi), "exposures": len(points)}, "neighbour_arcsec": neighbour,
        "position": {"ra": round(ora, 6), "dec": round(odec, 6)}, "snapped_arcsec": snapped,
    }
    out["line"] = _line(points)
    out["hint"] = _read(out)
    cache.put_json(ck, out)
    return out


def _score(counts: dict, start: float) -> tuple:
    return (sum(1 for c in counts.values() if c >= 3), sum(min(c, PER_BAND) for c in counts.values()), start)


def _coverage(visit: list[dict]) -> tuple:
    """How good a stretch of exposures is for a spectrum: colour bands covered, exposures we would use, how recent."""
    counts: dict[int, int] = {}
    for f in visit:
        counts[f["detector"]] = counts.get(f["detector"], 0) + 1
    return _score(counts, visit[0]["mjd"])


def _best_month(visit: list[dict]) -> list[dict]:
    """A visit longer than a month (the deep fields near the ecliptic poles): the month of it that covers
    the most colour bands, then holds the most exposures we would use, then is the latest."""
    if visit[-1]["mjd"] - visit[0]["mjd"] <= MAX_SPAN_DAYS:
        return visit
    best, j, counts = None, 0, {}
    for i, f in enumerate(visit):
        while j < len(visit) and visit[j]["mjd"] - f["mjd"] <= MAX_SPAN_DAYS:
            counts[visit[j]["detector"]] = counts.get(visit[j]["detector"], 0) + 1
            j += 1
        score = _score(counts, f["mjd"])
        if best is None or score >= best[0]:
            best = (score, i, j)
        counts[f["detector"]] -= 1
    return visit[best[1]:best[2]]


def doodle_args(d: dict) -> tuple | None:
    """What to measure for a doodle: its spot, plus its yearly drift when it is an arrow, so that the
    measuring circle follows it. None for the kinds that do not stay put (asteroids, comets) and for made-up ones."""
    if d.get("simulated") or d.get("type") not in ("arrow", "pulse") or not d.get("points"):
        return None
    first, last, m = d["points"][0], d["points"][-1], d.get("motion") or {}
    if d["type"] == "arrow" and m.get("rate_arcsec_per_year") and m.get("pa_deg") is not None:
        pa, rate = math.radians(m["pa_deg"]), m["rate_arcsec_per_year"]
        return (round(last["ra"], 5), round(last["dec"], 5), round(rate * math.sin(pa), 2), round(rate * math.cos(pa), 2), round(last["t"], 2))
    return (round(first["ra"], 5), round(first["dec"], 5), 0.0, 0.0, None)


def _line(points: list[dict]) -> list[list[float]]:
    """One value per wavelength step through the bands where the object is seen: every channel for a bright
    object, the middle value of a handful of neighbouring exposures for a faint one. [wl, mJy, error]."""
    line = []
    for det in sorted({p["band"] for p in points}):
        ps = [p for p in points if p["band"] == det and p["ours"]]
        if len(ps) < 3:
            continue
        snr = _median(np.array([abs(p["mjy"]) / max(p["err"], 1e-9) for p in ps]))
        per = 1 if snr >= 8.0 else max(3, int(math.ceil(len(ps) / 5)))
        for i in range(0, len(ps), per):
            g = ps[i:i + per]
            if per > 1 and len(g) < 2:
                continue
            f = np.array([p["mjy"] for p in g])
            w = float(np.mean([p["wl"] for p in g]))
            e = g[0]["err"] if len(g) == 1 else max(1.2533 * 1.4826 * float(np.median(np.abs(f - np.median(f)))) / math.sqrt(len(g)), g[0]["err"] / math.sqrt(len(g)))
            line.append([round(w, 4), float(f"{float(np.median(f)):.4g}"), float(f"{e:.2g}")])
    return line


def _flux(mjy: float) -> str:
    return f"{mjy / 1000.0:.1f} Jy" if mjy >= 950 else f"{mjy:.0f} mJy" if mjy >= 9.5 else f"{mjy:.2g} mJy"


def _smooth(fx: np.ndarray, k: int = 2) -> np.ndarray:
    """Running median over 2k+1 points: the shape without single stray measurements."""
    return np.array([float(np.median(fx[max(0, i - k):i + k + 1])) for i in range(len(fx))])


def _read(sp: dict) -> str:
    """A careful plain-language reading of the full spectrum."""
    bands, line = sp["bands"], sp["line"]
    seen = [b for b in bands if b["on_spot"]]
    if not seen or not line:
        near = f" The nearest source is {sp['neighbour_arcsec']:.0f}″ away." if sp.get("neighbour_arcsec") else ""
        return ("Nothing sits on this exact spot in any colour band of that visit, so no spectrum can be given for it. "
                "What the dots show is the sky, or light from a neighbour inside the measuring circle." + near)
    parts = []
    if sp.get("snapped_arcsec") and sp["snapped_arcsec"] >= 3.0:
        parts.append(f"Measured on the source {sp['snapped_arcsec']:.0f}″ from the spot you chose.")
    missing = [b for b in bands if not b["on_spot"]]
    wl = np.array([p[0] for p in line])
    fx = np.array([p[1] for p in line])
    sm = _smooth(fx, 1 if len(fx) < 12 else 2)
    if missing:
        runs = []  # neighbouring colour bands in which it is seen, joined into stretches of wavelength
        for b in sorted(seen, key=lambda b: b["band"]):
            if runs and b["band"] == runs[-1][2] + 1:
                runs[-1][1], runs[-1][2] = b["range_um"][1], b["band"]
            else:
                runs.append([b["range_um"][0], b["range_um"][1], b["band"]])
        where = (f"from {runs[0][0]:.1f} to {runs[0][1]:.1f} µm" if len(runs) == 1
                 else "at " + ", ".join(f"{a:.1f}–{z:.1f}" for a, z, _ in runs[:-1]) + f" and {runs[-1][0]:.1f}–{runs[-1][1]:.1f} µm")
        other = f"a neighbour {sp['neighbour_arcsec']:.0f}″ away that reaches into the measuring circle" if sp.get("neighbour_arcsec") else "the sky, not from it"
        parts.append(f"It shows up only {where}. In the other colour bands nothing sits on its spot: the hollow dots there are light from {other}.")
        if sp.get("neighbour_arcsec"):
            parts.append("That neighbour also adds a little to the object's own dots.")
    k = int(np.argmax(sm))
    jumpy = float(np.mean(np.abs(fx / np.clip(sm, 1e-9, None) - 1.0) > 0.25)) if len(fx) >= 12 else 0.0  # share of dots far off their neighbours
    overloaded = float(sm.max()) >= OVERLOAD_MJY or jumpy > JUMPY  # a very bright star: the detector overloads and single measurements jump about
    if overloaded:
        parts.append(f"Here it reaches about {_flux(float(sm[k]))} near {wl[k]:.1f} µm, but it is bright enough to overload SPHEREx's detector: the single measurements jump about, "
                     "and its true brightness is probably higher. Read nothing into the ups and downs.")
    else:
        parts.append(f"It is brightest near {wl[k]:.1f} µm, at about {_flux(float(sm[k]))}.")
    dips = []
    for (a, b), left, right, where, what in DIPS:
        mid = fx[(wl >= a) & (wl <= b)]
        sh = np.r_[fx[(wl >= left[0]) & (wl <= left[1])], fx[(wl >= right[0]) & (wl <= right[1])]]
        if len(mid) >= 1 and len(sh) >= 2 and _median(sh) > 0 and _median(mid) < 0.6 * _median(sh):
            dips.append((where, what))
    if overloaded:
        pass
    elif dips:
        by: dict[str, list[str]] = {}
        for where, what in dips:
            by.setdefault(what, []).append(where)
        parts.append("It dips near " + ", and near ".join(f"{' and '.join(v)} µm, where {k_} absorbs" for k_, v in by.items())
                     + ": the mark of a very cool atmosphere, as in brown dwarfs and the coolest stars.")
    elif not missing and len(fx) >= 20:
        short, long_ = _median(sm[(wl >= 0.9) & (wl <= 1.3)]), _median(sm[(wl >= 4.0) & (wl <= 5.0)])
        if short > 0 and long_ > 2.5 * short:
            parts.append("It keeps getting brighter toward longer wavelengths: more infrared light than a bare star gives. Warm dust around a star does that.")
        elif long_ > 0 and short > 2.5 * long_:
            parts.append("It fades steadily toward longer wavelengths, as ordinary stars do.")
    parts.append(f"All of it was measured in one visit, {sp['visit']['first']} to {sp['visit']['last']}.")
    return " ".join(parts)
