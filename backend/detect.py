"""Automatic change detection: what moved, changed brightness, appeared or vanished.

Input: a set of Blink X frames of one field (same centre, size and band), already resampled onto
one north-up grid by ``spherex.get_frame``. Output: a list of "Sky Doodles", one per flagged object.

Steps (all on real pixels; nothing is invented):

1. Find sources in every frame (photutils peak finding + aperture photometry).
2. Group detections that fall on the same spot of sky across frames.
3. Stars that are there all the time become anchors: they give a per-frame alignment check
   (star-pattern shift on top of the WCS) and a per-frame brightness scale.
4. Detections that exist only for part of the time are linked into straight tracks (movers).
5. Anchors are tested for slow drift (proper motion) and for brightness changes between visits.
6. Each result gets a doodle type:

   SPARK   seen during one visit only (an asteroid or comet passing through)
   TAIL    the same, but fuzzy: a comet
   ARROW   moves steadily from visit to visit (a nearby star or brown dwarf)
   ZIGZAG  jumps back and forth between visits (parallax of a very distant solar-system body)
   PULSE   stays put but changes brightness, appears or fades

Nothing here is a discovery claim. Catalogue cross-checks live in ``catalogs.py``; anything not
matched is called a candidate.
"""
from __future__ import annotations

import hashlib
import math
import warnings
from dataclasses import dataclass, field

import numpy as np

NATIVE = 6.15  # arcsec per SPHEREx detector pixel
THRESH = 6.0  # detection threshold, in units of the frame's sky noise
MAX_SOURCES = 140  # per frame, brightest first
VISIT_GAP_DAYS = 20.0
BURST_GAP_DAYS = 20.0 / 1440.0  # exposures less than 20 min apart belong to one "burst"
VMAX_ARCSEC_PER_HOUR = 2500.0

PREFIX = {"zigzag": "ZIG", "arrow": "ARW", "spark": "SPK", "tail": "TAIL", "pulse": "PLS"}


# --------------------------------------------------------------------------- geometry


def pix_to_sky(x, y, ra0: float, dec0: float, size_deg: float, n: int):
    """Grid pixel (0-based, pixel centres) -> RA/Dec in degrees; same projection as the frames."""
    step = math.radians(size_deg / n)
    c = (n - 1) / 2.0
    xi = -(np.asarray(x, float) - c) * step
    eta = (c - np.asarray(y, float)) * step
    a0, d0 = math.radians(ra0), math.radians(dec0)
    den = math.cos(d0) - eta * math.sin(d0)
    ra = a0 + np.arctan2(xi, den)
    dec = np.arctan2((math.sin(d0) + eta * math.cos(d0)) * np.cos(ra - a0), den)
    return np.degrees(ra) % 360.0, np.degrees(dec)


def sky_to_pix(ra, dec, ra0: float, dec0: float, size_deg: float, n: int):
    step = math.radians(size_deg / n)
    c = (n - 1) / 2.0
    a, d = np.radians(ra), np.radians(dec)
    a0, d0 = math.radians(ra0), math.radians(dec0)
    cosc = math.sin(d0) * np.sin(d) + math.cos(d0) * np.cos(d) * np.cos(a - a0)
    xi = np.cos(d) * np.sin(a - a0) / cosc
    eta = (math.cos(d0) * np.sin(d) - math.sin(d0) * np.cos(d) * np.cos(a - a0)) / cosc
    return c - xi / step, c - eta / step


def compass(pa_deg: float) -> str:
    names = ["north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west"]
    return names[int(((pa_deg % 360) + 22.5) // 45) % 8]


# --------------------------------------------------------------------------- per-frame sources


@dataclass
class Frame:
    id: str
    mjd: float
    date: str
    wl: float
    img: np.ndarray  # sky-subtracted, in units of this frame's noise; NaN = no data
    pix: float  # arcsec per grid pixel
    sigma: float = 1.0  # that noise in MJy/sr, so brightness can be compared between frames
    x: np.ndarray = field(default_factory=lambda: np.zeros(0))
    y: np.ndarray = field(default_factory=lambda: np.zeros(0))
    flux: np.ndarray = field(default_factory=lambda: np.zeros(0))  # small aperture
    wide: np.ndarray = field(default_factory=lambda: np.zeros(0))  # large aperture
    peak: np.ndarray = field(default_factory=lambda: np.zeros(0))
    scale: float = 1.0  # brightness of this frame relative to the others (stars in common)
    shift: tuple[float, float] = (0.0, 0.0)  # star-pattern offset removed, grid px
    n_align: int = 0


def _photometry(img: np.ndarray, pos: np.ndarray, pix: float):
    """Centroid, small- and large-aperture flux (local sky removed) and the local sky level at the given positions."""
    from photutils.aperture import ApertureStats, CircularAnnulus, CircularAperture

    s = NATIVE / pix
    mask = ~np.isfinite(img)
    data = np.where(mask, 0.0, img)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        bg = np.nan_to_num(np.asarray(ApertureStats(data, CircularAnnulus(pos, 4.0 * s, 6.0 * s), mask=mask).median, float))
        st = ApertureStats(data, CircularAperture(pos, 1.5 * s), local_bkg=bg, mask=mask)
        cx, cy = np.asarray(st.xcentroid, float), np.asarray(st.ycentroid, float)
        flux = np.asarray(st.sum, float)
        good = np.isfinite(cx) & np.isfinite(cy) & (np.hypot(cx - pos[:, 0], cy - pos[:, 1]) < 1.5 * s)
        cx, cy = np.where(good, cx, pos[:, 0]), np.where(good, cy, pos[:, 1])
        wide = np.asarray(ApertureStats(data, CircularAperture(np.c_[cx, cy], 3.0 * s), local_bkg=bg, mask=mask).sum, float)
    return cx, cy, np.nan_to_num(flux), np.nan_to_num(wide), bg


def find_sources(fr: Frame) -> None:
    """Fill fr.x, fr.y, fr.flux, fr.wide, fr.peak with the sources of one frame."""
    from photutils.detection import find_peaks

    img, s = fr.img, NATIVE / fr.pix
    mask = ~np.isfinite(img)
    data = np.where(mask, 0.0, img)
    box = int(max(3, round(2.0 * s))) | 1
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        tbl = find_peaks(data, threshold=THRESH, box_size=box, mask=mask, border_width=int(math.ceil(1.6 * s)))
    if tbl is None or len(tbl) == 0:
        return
    order = np.argsort(-np.asarray(tbl["peak_value"], float))[:MAX_SOURCES]
    pos = np.c_[np.asarray(tbl["x_peak"], float)[order], np.asarray(tbl["y_peak"], float)[order]]
    peak = np.asarray(tbl["peak_value"], float)[order]
    cx, cy, flux, wide, bg = _photometry(img, pos, fr.pix)
    # What counts is how far a source stands above its own surroundings. On the diffuse light of a
    # galaxy or nebula every bump is "bright", and such bumps come and go from frame to frame.
    peak = peak - np.maximum(bg, 0.0)
    keep = (flux > 0) & (peak >= THRESH)
    # A very bright object throws a halo, spikes and ghosts around itself. Those travel with it and
    # would look like extra movers, so faint detections inside the glare of a bright one are dropped.
    for i in np.where(peak >= 300.0)[0]:
        r = s * (2.0 + 4.0 * math.log10(peak[i] / 100.0))
        near = np.hypot(cx - cx[i], cy - cy[i]) < r
        keep &= ~(near & (peak < peak[i] / 30.0))
    fr.x, fr.y, fr.peak = cx[keep], cy[keep], peak[keep]
    fr.flux, fr.wide = flux[keep] * fr.sigma, wide[keep] * fr.sigma


def forced_flux(fr: Frame, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Small-aperture flux at fixed positions (NaN where the frame has no data there)."""
    from photutils.aperture import ApertureStats, CircularAnnulus, CircularAperture

    if len(x) == 0:
        return np.zeros(0)
    s = NATIVE / fr.pix
    n = fr.img.shape[0]
    pos = np.c_[x + fr.shift[0], y + fr.shift[1]]
    mask = ~np.isfinite(fr.img)
    data = np.where(mask, 0.0, fr.img)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        bg = np.nan_to_num(np.asarray(ApertureStats(data, CircularAnnulus(pos, 4.0 * s, 6.0 * s), mask=mask).median, float))
        out = np.asarray(ApertureStats(data, CircularAperture(pos, 1.5 * s), local_bkg=bg, mask=mask).sum, float) * fr.sigma
    xi, yi = np.clip(np.rint(pos[:, 0]).astype(int), 0, n - 1), np.clip(np.rint(pos[:, 1]).astype(int), 0, n - 1)
    m = 1.6 * s
    off = (pos[:, 0] < m) | (pos[:, 1] < m) | (pos[:, 0] > n - 1 - m) | (pos[:, 1] > n - 1 - m) | mask[yi, xi]
    out[off] = np.nan
    return out


# --------------------------------------------------------------------------- grouping


@dataclass
class Det:
    f: int  # frame index
    x: float
    y: float
    flux: float  # scaled to the common brightness scale
    wide: float
    peak: float
    t: float


def _cluster(dets: list[Det], r: float) -> list[list[int]]:
    """Group detections lying within r pixels of each other (at most one per frame per group)."""
    if not dets:
        return []
    x = np.array([d.x for d in dets])
    y = np.array([d.y for d in dets])
    fidx = np.array([d.f for d in dets])
    peak = np.array([d.peak for d in dets])
    free = np.ones(len(dets), bool)
    groups = []
    for i in np.argsort(-peak):
        if not free[i]:
            continue
        cx, cy = x[i], y[i]
        members = np.array([i])
        for _ in range(3):
            d = np.hypot(x - cx, y - cy)
            cand = np.where(free & (d <= r))[0]
            best: dict[int, int] = {}
            for k in cand[np.argsort(d[cand])]:
                best.setdefault(int(fidx[k]), int(k))
            members = np.array(sorted(best.values()))
            cx, cy = float(np.median(x[members])), float(np.median(y[members]))
        free[members] = False
        groups.append([int(m) for m in members])
    return groups


def _coarse_shifts(frames: list[Frame], s: float) -> None:
    """Star-pattern matching: find any whole-pixel x/y shift of a frame against the others.

    The frames are already aligned with their image coordinates (WCS). This is the fallback for an
    exposure whose WCS is off: the offsets between its bright stars and a reference frame's bright
    stars pile up at one value, and that value is the shift. The majority of frames define zero.
    """
    if len(frames) < 3:
        return

    def clean(fr):
        """Bright-ish sources well away from any very bright one (whose halo features move with it)."""
        keep = np.ones(len(fr.x), bool)
        for i in np.where(fr.peak >= 1000.0)[0]:
            keep &= np.hypot(fr.x - fr.x[i], fr.y - fr.y[i]) > s * (4.0 + 6.0 * math.log10(fr.peak[i] / 100.0))
        return fr.x[keep][:50], fr.y[keep][:50]

    lists = [clean(fr) for fr in frames]
    r = int(np.argmax([len(x) for x, _ in lists]))
    ref_x, ref_y = lists[r]
    ref = frames[r]
    if len(ref_x) < 12:
        return
    reach = int(math.ceil(12 * s))
    shifts = []
    for fr, (fx, fy) in zip(frames, lists):
        if fr is ref:
            continue
        if len(fx) < 12:
            shifts.append((0, 0, 0))
            continue
        dx = np.rint(fx[:, None] - ref_x[None, :]).astype(int).ravel()
        dy = np.rint(fy[:, None] - ref_y[None, :]).astype(int).ravel()
        ok = (np.abs(dx) <= reach) & (np.abs(dy) <= reach)
        if not ok.any():
            shifts.append((0, 0, 0))
            continue
        hist = np.zeros((2 * reach + 1, 2 * reach + 1), int)
        np.add.at(hist, (dy[ok] + reach, dx[ok] + reach), 1)
        iy, ix = np.unravel_index(int(hist.argmax()), hist.shape)
        shifts.append((ix - reach, iy - reach, int(hist[iy, ix]) if int(hist[iy, ix]) >= max(8, 0.5 * min(len(fx), len(ref_x))) else 0))
    med_x, med_y = float(np.median([v[0] for v in shifts])), float(np.median([v[1] for v in shifts]))
    k = 0
    for fr in frames:
        if fr is ref:
            fr.shift = (-med_x, -med_y)
            continue
        sx_, sy_, votes = shifts[k]
        k += 1
        if votes:  # many stars agree on this shift
            fr.shift = (sx_ - med_x, sy_ - med_y)


def _bursts(times: np.ndarray) -> np.ndarray:
    """Label exposures taken within 20 minutes of each other with the same burst number."""
    order = np.argsort(times)
    lab = np.zeros(len(times), int)
    b = 0
    for a, c in zip(order[:-1], order[1:]):
        if times[c] - times[a] > BURST_GAP_DAYS:
            b += 1
        lab[c] = b
    return lab


def _visits(times: np.ndarray) -> np.ndarray:
    order = np.argsort(times)
    lab = np.zeros(len(times), int)
    v = 0
    for a, c in zip(order[:-1], order[1:]):
        if times[c] - times[a] > VISIT_GAP_DAYS:
            v += 1
        lab[c] = v
    return lab


# --------------------------------------------------------------------------- naming

_ADJ = {
    "zigzag": ["Restless", "Shy", "Far-flung", "Wobbling", "Patient", "Elusive", "Dancing", "Hidden"],
    "arrow": ["Speedy", "Steady", "Marching", "Determined", "Gliding", "Runaway", "Bold", "Homesick"],
    "spark": ["Sudden", "Blinking", "Passing", "Quick", "Skipping", "Darting", "Cheeky", "Fleeting"],
    "tail": ["Frosty", "Feathery", "Misty", "Glowing", "Wandering", "Breezy", "Dusty", "Icy"],
    "pulse": ["Breathing", "Winking", "Beating", "Flickering", "Sleepy", "Moody", "Shimmering", "Humming"],
}
_NOUN = {
    "zigzag": ["Lantern", "Wanderer", "Marble", "Ghost", "Pendulum", "Nomad", "Stranger", "Outlier"],
    "arrow": ["Runner", "Arrow", "Neighbour", "Ember", "Traveller", "Sprinter", "Comet-not", "Pilgrim"],
    "spark": ["Pebble", "Firefly", "Visitor", "Sparkler", "Hopper", "Boulder", "Drifter", "Skipper"],
    "tail": ["Snowball", "Broom", "Feather", "Plume", "Dandelion", "Kite", "Paintbrush", "Streamer"],
    "pulse": ["Heartbeat", "Lighthouse", "Candle", "Beacon", "Firefly", "Drum", "Lamp", "Bell"],
}


def name_doodle(kind: str, ra: float, dec: float) -> tuple[str, str]:
    """Stable short ID and nickname from the type and the sky position."""
    h = int(hashlib.sha1(f"{kind}:{ra:.3f}:{dec:.3f}".encode()).hexdigest(), 16)
    return f"{PREFIX[kind]}-{h % 1000:03d}", f"{_ADJ[kind][(h >> 12) % 8]} {_NOUN[kind][(h >> 20) % 8]}"


# --------------------------------------------------------------------------- main entry


def frames_from_encoded(encoded: list[dict], decode) -> list[Frame]:
    out = []
    for m in sorted(encoded, key=lambda m: m["mjd"]):
        if m.get("coverage", 1.0) < 0.3:
            continue
        img = decode(m).astype(np.float64) / m["sigma"]
        out.append(Frame(m["id"], float(m["mjd"]), str(m.get("date_obs", "")), float(m.get("wavelength_um") or 0.0), img, float(m["pixscale_arcsec"]), float(m["sigma"])))
    return out


def detect(frames: list[Frame], ra0: float, dec0: float, size_deg: float) -> dict:
    """Run the whole analysis. Returns {"doodles": [...], "align": {...}, "stats": {...}}."""
    result = {"doodles": [], "align": {}, "stats": {"frames": len(frames)}}
    if len(frames) < 2:
        return result
    n = frames[0].img.shape[0]
    pix = frames[0].pix
    s = NATIVE / pix
    times = np.array([f.mjd for f in frames])
    burst = _bursts(times)
    visit = _visits(times)
    span = float(times.max() - times.min())
    for fr in frames:
        find_sources(fr)

    def all_dets() -> list[Det]:
        return [
            Det(i, fr.x[k] - fr.shift[0], fr.y[k] - fr.shift[1], fr.flux[k] / fr.scale, fr.wide[k] / fr.scale, fr.peak[k], fr.mjd)
            for i, fr in enumerate(frames)
            for k in range(len(fr.x))
        ]

    _coarse_shifts(frames, s)
    r_match = 0.6 * s
    # ---- anchors: stars seen (almost) all the time -> alignment check and brightness scale
    for _ in range(2):
        dets = all_dets()
        groups = _cluster(dets, r_match)
        anchors = [g for g in groups if len(g) >= max(3, math.ceil(0.7 * len(frames)))]
        if len(anchors) < 4:
            break
        ax = np.array([np.median([dets[k].x for k in g]) for g in anchors])
        ay = np.array([np.median([dets[k].y for k in g]) for g in anchors])
        af = np.array([np.median([dets[k].flux for k in g]) for g in anchors])
        for i, fr in enumerate(frames):
            dx, dy, ratio = [], [], []
            for j, g in enumerate(anchors):
                for k in g:
                    if dets[k].f == i:
                        dx.append(dets[k].x - ax[j])
                        dy.append(dets[k].y - ay[j])
                        ratio.append(dets[k].flux / af[j])
            if len(dx) >= 4:
                fr.shift = (fr.shift[0] + float(np.median(dx)), fr.shift[1] + float(np.median(dy)))
                fr.scale *= float(np.median(ratio))
                fr.n_align = len(dx)
    dets = all_dets()
    groups = _cluster(dets, r_match)
    for fr in frames:
        off = math.hypot(*fr.shift) * pix
        result["align"][fr.id] = {
            "dx_arcsec": round(fr.shift[0] * pix, 2),
            "dy_arcsec": round(fr.shift[1] * pix, 2),
            "offset_arcsec": round(off, 2),
            "stars": fr.n_align,
            "method": "wcs" if fr.n_align < 4 else ("wcs+stars" if off > 0.5 * NATIVE else "wcs, checked on stars"),
            "shift_px": [round(fr.shift[0], 2), round(fr.shift[1], 2)] if off > 0.5 * NATIVE else [0, 0],
            # how bright the stars are in this exposure relative to the others (its colour differs): used to compare pictures fairly
            "scale": round(float(fr.scale), 4) if fr.n_align >= 4 else None,
        }
    result["stats"].update({"sources": int(np.median([len(f.x) for f in frames])), "anchors": sum(len(g) >= 0.7 * len(frames) for g in groups)})

    # ---- describe every group
    info = []
    for g in groups:
        gx = np.array([dets[k].x for k in g])
        gy = np.array([dets[k].y for k in g])
        gt = np.array([dets[k].t for k in g])
        gf = np.array([dets[k].f for k in g])
        cx, cy = float(np.median(gx)), float(np.median(gy))
        info.append({"members": g, "x": cx, "y": cy, "t0": float(gt.min()), "t1": float(gt.max()), "frames": set(gf.tolist()), "peak": float(np.median([dets[k].peak for k in g])), "flux": float(np.median([dets[k].flux for k in g]))})
    if not info:
        return result
    gx_all = np.array([c["x"] for c in info])
    gy_all = np.array([c["y"] for c in info])
    forced = np.vstack([forced_flux(fr, gx_all, gy_all) / fr.scale for fr in frames])  # [frame, group]
    for j, c in enumerate(info):
        avail = np.isfinite(forced[:, j])
        det_mask = np.zeros(len(frames), bool)
        det_mask[list(c["frames"])] = True
        c["avail"] = int(avail.sum())
        c["frac"] = len(c["frames"]) / max(1, c["avail"])
        outside = avail & ~det_mask & ((times < c["t0"] - 1e-6) | (times > c["t1"] + 1e-6))
        c["n_outside"] = int(outside.sum())
        c["contrast"] = float(np.median(forced[outside, j]) / c["flux"]) if outside.any() and c["flux"] > 0 else float("nan")
        c["localized"] = span > 0 and (c["t1"] - c["t0"]) < 0.5 * span
        mine = visit == visit[c["members"] and dets[c["members"][0]].f]
        c["visit_frac"] = len(c["frames"]) / max(1, int((avail & mine).sum()))  # share of its own visit's exposures it was seen in
        # really there for a while and really gone the rest of the time
        c["orphan"] = bool(c["localized"] and c["peak"] >= 2.0 * THRESH and c["n_outside"] >= 2 and c["contrast"] < 0.35)

    doodles: list[dict] = []
    conc_star = _star_concentration(dets, groups, len(frames))

    to_mjy = 1e9 * (pix / 206264.8) ** 2  # image units are MJy/sr; a sum over grid pixels times their solid angle is a flux

    def sight(det_ids: list[int]) -> list[dict]:
        """One point per burst: mean position, time and brightness of the detections in it."""
        pts = []
        for b in sorted({int(burst[dets[k].f]) for k in det_ids}):
            ks = [k for k in det_ids if burst[dets[k].f] == b]
            x, y = float(np.mean([dets[k].x for k in ks])), float(np.mean([dets[k].y for k in ks]))
            ra, dec = pix_to_sky(x, y, ra0, dec0, size_deg, n)
            kmid = ks[len(ks) // 2]
            pts.append({
                "t": float(np.mean([dets[k].t for k in ks])), "date": frames[dets[kmid].f].date[:19], "frame": frames[dets[kmid].f].id,
                "frames": [frames[dets[k].f].id for k in ks], "x": round(x, 2), "y": round(y, 2),
                "ra": round(float(ra), 6), "dec": round(float(dec), 6), "n": len(ks),
                "flux": round(float(np.median([dets[k].flux for k in ks])), 2), "peak_sigma": round(float(np.median([dets[k].peak for k in ks])), 1),
                "wavelength_um": round(float(np.mean([frames[dets[k].f].wl for k in ks])), 4), "visit": int(visit[dets[kmid].f]),
                # per exposure: wavelength, brightness as measured (before the frame-to-frame scaling), exposure id
                "spec": [[frames[dets[k].f].wl, dets[k].flux * frames[dets[k].f].scale * to_mjy, frames[dets[k].f].id] for k in ks],
            })
        return pts

    # ---- movers: link time-limited detections into straight tracks
    orphan_ids = [k for c in info if c["orphan"] for k in c["members"]]
    used: set[int] = set()
    parked: set[int] = set()  # time-limited but standing still: not movers
    for _ in range(10):
        free = [k for k in orphan_ids if k not in used and k not in parked]
        track = _best_track(dets, free, burst, pix, visit)
        if track is None:
            break
        ends = sorted(track, key=lambda k: dets[k].t)
        if math.hypot(dets[ends[-1]].x - dets[ends[0]].x, dets[ends[-1]].y - dets[ends[0]].y) * pix < NATIVE:
            parked.update(track)
            continue
        used.update(track)
        comp = _companions(dets, track, [k for k in orphan_ids if k not in used], pix)
        used.update(comp)
        d = _mover_doodle(dets, track, sight, frames, visit, pix, conc_star)
        if d["type"] == "tail" and comp:
            # where the faint clumps sit relative to the head = which way the tail points
            head = {dets[k].f: (dets[k].x, dets[k].y) for k in track}
            off = [(dets[k].x - head[dets[k].f][0], dets[k].y - head[dets[k].f][1]) for k in comp if dets[k].f in head]
            if off:
                ox, oy = float(np.median([o[0] for o in off])), float(np.median([o[1] for o in off]))
                if math.hypot(ox, oy) * pix > NATIVE:
                    d["tail_pa_deg"] = round(math.degrees(math.atan2(-ox, -oy)) % 360.0, 0)
                    d["tail_direction"] = compass(d["tail_pa_deg"])
        doodles.append(d)

    # ---- zigzag: time-limited sightings in 3+ visits that jump back and forth
    left = [c for c in info if c["orphan"] and not (set(c["members"]) & used)]
    # a distant planet is there for the whole of each visit; a source that flickers in one or two exposures is not one
    steady = [c for c in left if len(c["frames"]) >= 3 and c["visit_frac"] >= 0.6]
    zig = _find_zigzag(steady, dets, visit, pix)
    if zig:
        ids = [k for c in zig for k in c["members"]]
        used.update(ids)
        doodles.append(_zigzag_doodle(dets, zig, sight, pix))
        left = [c for c in left if c not in zig]

    # ---- single sightings: sparks (one burst) or objects that appeared / faded (longer)
    star_shape = np.median([dets[k].flux / dets[k].peak for g in groups if len(g) >= 0.7 * len(frames) for k in g]) if result["stats"]["anchors"] else None
    singles = []
    for c in left:
        ks = c["members"]
        shape = float(np.median([dets[k].flux / dets[k].peak for k in ks]))
        if len(ks) < 2 or (star_shape is not None and not (0.4 * star_shape <= shape <= 4.0 * star_shape)):
            continue  # seen in one exposure only: most likely a cosmic-ray hit, leftover charge or a reflection
        singles.append(c)
    singles.sort(key=lambda c: -c["peak"])
    kept = []
    for c in singles:  # two groups a few pixels apart in the same exposures are one object
        if c["peak"] >= 3.0 * THRESH and not any(math.hypot(c["x"] - o["x"], c["y"] - o["y"]) < 3.0 * s and (c["frames"] & o["frames"] or abs(c["t0"] - o["t0"]) < BURST_GAP_DAYS) for o in kept):
            kept.append(c)
    for c in kept[:4]:
        pts = sight(c["members"])
        n_bursts_in_visit = len({int(burst[i]) for i in range(len(frames)) if visit[i] == pts[0]["visit"]})
        long_lived = len(pts) >= 2 and len(pts) >= 0.6 * n_bursts_in_visit and len(set(visit.tolist())) > 1
        fuzzy = _is_fuzzy(dets, c["members"], conc_star)
        kind = "pulse" if long_lived else ("tail" if fuzzy else "spark")
        d = _base(kind, pts)
        d["confidence"] = round(min(0.75, 0.25 + 0.1 * len(c["members"]) + 0.1 * math.log10(max(c["peak"], 10) / 10)), 2)
        d["brightness"] = {"change": "appeared and faded", "contrast": round(1.0 - max(c["contrast"], 0.0), 2)}
        d["fuzzy"] = fuzzy
        doodles.append(d)

    # ---- slow, steady movers (proper motion). A star that creeps a pixel or two between visits
    # splits into several tight groups above, so regroup the bright detections with a wide radius
    # and fit a straight line through each group.
    if int(visit.max()) >= 1:
        bright = [k for k in range(len(dets)) if dets[k].peak >= 20.0 and k not in used]
        sub = [dets[k] for k in bright]
        for g in _cluster(sub, 2.5 * s):
            ids = [bright[k] for k in g]
            if len(ids) < max(4, 0.6 * len(frames)) or len({int(visit[dets[k].f]) for k in ids}) < 2:
                continue
            drift = _drift(dets, ids, pix)
            if not drift:
                continue
            used.update(ids)
            pts = sight(ids)
            d = _base("arrow", pts)
            d["motion"] = drift
            d["confidence"] = round(min(0.95, 0.4 + 0.05 * drift["snr"]), 2)
            doodles.append(d)

    # ---- slow movers too faint to stand out in single exposures: search each visit's exposures added together
    if int(visit.max()) >= 1:
        taken = [(q["x"], q["y"]) for d in doodles for q in d["points"]]
        doodles += _deep_drifts(frames, visit, pix, n, ra0, dec0, size_deg, taken, to_mjy)

    # ---- brightness changes between visits, for sources that stay put
    static = [c for c in info if not c["orphan"] and c["frac"] >= 0.6 and len(c["frames"]) >= 4 and not (set(c["members"]) & used)]
    if result["stats"]["anchors"] < 5:
        static = []  # too few comparison stars to trust a brightness scale
    for c in static:
        var = _variability(dets, c["members"], frames, visit)
        if var:
            pts = sight(c["members"])
            d = _base("pulse", pts)
            d["brightness"] = var
            d["confidence"] = round(min(0.9, 0.3 + 0.05 * var["snr"]), 2)
            doodles.append(d)

    for d in doodles:
        d["status"] = "candidate"
        d["known"] = None
        d["field"] = {"ra": ra0, "dec": dec0, "size_deg": size_deg, "n": n, "pixscale_arcsec": round(pix, 3)}
        spec = [sp for q in d["points"] for sp in q.pop("spec", [])]
        d["spectrum"] = spectrum(spec, d["type"], faint=bool(d.get("deep")))
        explain(d)
    order = {"zigzag": 0, "tail": 1, "spark": 2, "arrow": 3, "pulse": 4}
    doodles.sort(key=lambda d: (order[d["type"]], -d.get("confidence", 0)))
    result["doodles"] = doodles
    result["stats"]["visits"] = int(visit.max() + 1)
    result["stats"]["bursts"] = int(burst.max() + 1)
    return result


# --------------------------------------------------------------------------- pieces


def _base(kind: str, pts: list[dict]) -> dict:
    did, nick = name_doodle(kind, pts[0]["ra"], pts[0]["dec"])
    return {"id": did, "nickname": nick, "type": kind, "points": pts, "epochs": len({p["visit"] for p in pts}), "sightings": len(pts),
            "peak_sigma": max(p["peak_sigma"] for p in pts)}


def _star_concentration(dets, groups, nframes):
    vals = [dets[k].wide / dets[k].flux for g in groups if len(g) >= 0.7 * nframes for k in g if dets[k].flux > 0 and 15 < dets[k].peak < 3000]
    if len(vals) < 5:
        return None
    med = float(np.median(vals))
    return med, float(1.4826 * np.median(np.abs(np.array(vals) - med))) or 0.05


def _is_fuzzy(dets, ids, conc_star) -> bool:
    """Light spread wider than the stars in the same frames (a coma), and not just a saturated glare."""
    if conc_star is None:
        return False
    vals = [dets[k].wide / dets[k].flux for k in ids if dets[k].flux > 0 and dets[k].peak < 3000]
    if not vals:
        return False
    med, mad = conc_star
    return float(np.median(vals)) > max(med + 6 * mad, 1.25 * med)


def _best_track(dets, ids, burst, pix, visit):
    """The straight, constant-speed line through the largest number of time-limited detections."""
    if len(ids) < 2:
        return None
    x = np.array([dets[k].x for k in ids]) * pix
    y = np.array([dets[k].y for k in ids]) * pix
    t = np.array([dets[k].t for k in ids])
    b = np.array([burst[dets[k].f] for k in ids])
    vis = np.array([visit[dets[k].f] for k in ids])
    fl = np.array([dets[k].flux for k in ids])
    pk = np.array([dets[k].peak for k in ids])
    tol = 0.9 * NATIVE
    best, best_score = None, (1, 0, 0.0)
    for i in range(len(ids)):
        for j in range(len(ids)):
            dt = t[j] - t[i]
            if dt < 10.0 / 1440.0 or b[i] == b[j]:
                continue
            vx, vy = (x[j] - x[i]) / dt, (y[j] - y[i]) / dt
            if math.hypot(vx, vy) / 24.0 > VMAX_ARCSEC_PER_HOUR:
                continue
            res = np.hypot(x - (x[i] + vx * (t - t[i])), y - (y[i] + vy * (t - t[i])))
            inl = np.where(res <= tol)[0]
            nb = len(set(b[inl].tolist()))
            if nb < 2:
                continue
            # a cosmic ray or a reflection shows up in one exposure only; a real object repeats
            if sum(int((b[inl] == bb).sum()) >= 2 for bb in set(b[inl].tolist())) < 2:
                continue
            # Two sightings months apart can always be joined by some straight line, so that proves
            # nothing. Across visits we ask for three or more visits in a row on the same line.
            vs = sorted(set(vis[inl].tolist()))
            if len(vs) == 2 or (len(vs) >= 3 and vs != list(range(vs[0], vs[-1] + 1))):
                continue
            if nb == 2:
                # two sightings alone are easy to mislink: ask for similar brightness and a clear signal
                f = fl[inl]
                if f.max() / max(f.min(), 1e-12) > 4.0 or pk[inl].min() < 3.0 * THRESH or len(inl) < 3:
                    continue
            score = (nb, len(inl), float(np.median(pk[inl])))
            if score[0] > best_score[0] or (score[0] == best_score[0] and score[2] * (1 + 0.1 * score[1]) > best_score[2] * (1 + 0.1 * best_score[1])):
                best_score, best = score, inl
    if best is None:
        return None
    return [ids[k] for k in best]


def _companions(dets, track, ids, pix):
    """Fainter time-limited detections that travel alongside a track: its halo, coma or ghosts."""
    t = np.array([dets[k].t for k in track])
    x = np.array([dets[k].x for k in track]) * pix
    y = np.array([dets[k].y for k in track]) * pix
    vx, vy, _ = _fit_line(t, x, y)
    tm, xm, ym = t.mean(), x.mean(), y.mean()
    peak = float(np.median([dets[k].peak for k in track]))
    reach = NATIVE * (12.0 + 5.0 * math.log10(max(peak, 100.0) / 100.0))
    out = []
    for k in ids:
        d = dets[k]
        px, py = xm + vx * (d.t - tm), ym + vy * (d.t - tm)
        r = math.hypot(d.x * pix - px, d.y * pix - py)
        if (r < reach and d.peak < peak) or (r < max(reach, 160.0) and d.peak < peak / 8.0):
            out.append(k)
    return out


def _fit_line(t, x, y):
    """Least-squares straight motion; returns (vx, vy, rms residual)."""
    tm = t.mean()
    den = float(((t - tm) ** 2).sum()) or 1.0
    vx = float(((t - tm) * (x - x.mean())).sum() / den)
    vy = float(((t - tm) * (y - y.mean())).sum() / den)
    res = np.hypot(x - (x.mean() + vx * (t - tm)), y - (y.mean() + vy * (t - tm)))
    return vx, vy, float(np.sqrt((res**2).mean()))


def _fit_line_weighted(t, x, y, sigma):
    """Straight motion through positions of unequal quality. Returns (vx, vy, weighted rms, error of the speed)."""
    w = 1.0 / np.maximum(np.asarray(sigma, float), 1e-6) ** 2
    tm = float((w * t).sum() / w.sum())
    den = float((w * (t - tm) ** 2).sum()) or 1.0
    xm, ym = float((w * x).sum() / w.sum()), float((w * y).sum() / w.sum())
    vx = float((w * (t - tm) * (x - xm)).sum() / den)
    vy = float((w * (t - tm) * (y - ym)).sum() / den)
    res2 = (x - (xm + vx * (t - tm))) ** 2 + (y - (ym + vy * (t - tm))) ** 2
    rms = float(np.sqrt((w * res2).sum() / w.sum()))
    return vx, vy, rms, 1.0 / math.sqrt(den)


def _motion(points: list[dict], pix: float, vx: float | None = None, vy: float | None = None) -> dict:
    a, b = points[0], points[-1]
    dx, dy = (b["x"] - a["x"]) * pix, (b["y"] - a["y"]) * pix  # arcsec; +x is west (east is left), +y is south
    dist = math.hypot(dx, dy)
    pa = math.degrees(math.atan2(-dx, -dy)) % 360.0  # position angle, east of north
    days = b["t"] - a["t"]
    out = {
        "dist_arcsec": round(dist, 2), "dist_spherex_px": round(dist / NATIVE, 2), "dist_grid_px": round(dist / pix, 2),
        "pa_deg": round(pa, 1), "direction": compass(pa), "days": round(days, 5),
    }
    if days > 0:
        out["rate_arcsec_per_hour"] = round(dist / (days * 24.0), 4)
        out["rate_arcsec_per_year"] = round(dist / days * 365.25, 3)
    return out


def _mover_doodle(dets, track, sight, frames, visit, pix, conc_star) -> dict:
    pts = sight(track)
    nvis = len({p["visit"] for p in pts})
    fuzzy = _is_fuzzy(dets, track, conc_star)
    kind = "arrow" if nvis >= 2 else ("tail" if fuzzy else "spark")
    d = _base(kind, pts)
    d["motion"] = _motion(pts, pix)
    t = np.array([dets[k].t for k in track])
    x = np.array([dets[k].x for k in track]) * pix
    y = np.array([dets[k].y for k in track]) * pix
    d["motion"]["fit_rms_arcsec"] = round(_fit_line(t, x, y)[2], 2)
    d["fuzzy"] = fuzzy
    d["confidence"] = round(min(0.98, 0.35 + 0.18 * (len(pts) - 1) + 0.03 * len(track) + 0.08 * math.log10(max(d["peak_sigma"], 10) / 10)), 2)
    return d


def _zigzag_plausible(chain, pix) -> bool:
    """A real parallax zigzag closes on itself. The size of the jump gives the distance, and at that
    distance Kepler's third law allows only a small net drift from one year to the next."""
    jumps = [math.hypot(b["x"] - a["x"], b["y"] - a["y"]) * pix for a, b in zip(chain[:-1], chain[1:])]
    jump = float(np.median(jumps))
    if jump <= 0:
        return False
    dist_au = 2.0 / math.radians(jump / 3600.0)
    allowed = 2.0 * 1296000.0 / dist_au ** 1.5                      # twice the circular-orbit rate, arcsec a year
    for a, b in zip(chain[:-2], chain[2:]):                         # same side of Earth's orbit, about a year apart
        years = max(((b["t0"] + b["t1"]) - (a["t0"] + a["t1"])) / 2.0 / 365.25, 0.25)
        if math.hypot(b["x"] - a["x"], b["y"] - a["y"]) * pix > allowed * years + 2.0 * NATIVE:
            return False
    return True


def _zigzag_closure(chain, pix) -> float:
    return sum(math.hypot(b["x"] - a["x"], b["y"] - a["y"]) for a, b in zip(chain[:-2], chain[2:])) * pix


def _find_zigzag(left, dets, visit, pix):
    """Sightings in three or more consecutive visits whose jumps alternate direction (parallax) and
    whose net drift is physically possible at the distance the jump implies."""
    by_visit: dict[int, list] = {}
    for c in left:
        by_visit.setdefault(int(visit[dets[c["members"][0]].f]), []).append(c)
    vs = sorted(by_visit)
    if len(vs) < 3:
        return None
    best, best_key = None, None

    def extend(chain, k):
        nonlocal best, best_key
        if len(chain) >= 3 and _zigzag_plausible(chain, pix):
            key = (len(chain), -_zigzag_closure(chain, pix))
            if best_key is None or key > best_key:
                best, best_key = list(chain), key
        if k >= len(vs) or vs[k] != vs[k - 1] + 1:
            return
        prev = chain[-1]
        for c in by_visit[vs[k]]:
            if not 0.4 < c["flux"] / max(prev["flux"], 1e-9) < 2.5:
                continue
            step = math.hypot(c["x"] - prev["x"], c["y"] - prev["y"])
            if len(chain) == 1:
                if step * pix <= 3 * NATIVE:
                    continue
            else:
                d1 = (prev["x"] - chain[-2]["x"], prev["y"] - chain[-2]["y"])
                n1 = math.hypot(*d1)
                if n1 <= 0 or step <= 0:
                    continue
                turn = (d1[0] * (c["x"] - prev["x"]) + d1[1] * (c["y"] - prev["y"])) / (n1 * step)
                if turn > -0.8 or not 0.6 < step / n1 < 1.67:
                    continue
            extend(chain + [c], k + 1)

    for s0 in range(len(vs) - 2):
        for a in by_visit[vs[s0]]:
            extend([a], s0 + 1)
    return best


def _zigzag_doodle(dets, chain, sight, pix) -> dict:
    pts = sight([k for c in chain for k in c["members"]])
    # one point per visit (mean of its bursts)
    per = []
    for v in sorted({p["visit"] for p in pts}):
        ps = [p for p in pts if p["visit"] == v]
        q = dict(ps[len(ps) // 2])
        for key in ("x", "y", "ra", "dec", "t"):
            q[key] = round(float(np.mean([p[key] for p in ps])), 6)
        q["spec"] = [sp for p in ps for sp in p.get("spec", [])]
        per.append(q)
    d = _base("zigzag", per)
    jumps = [math.hypot(b["x"] - a["x"], b["y"] - a["y"]) * pix for a, b in zip(per[:-1], per[1:])]
    # after removing the back-and-forth, what is left is the slow drift
    drift = _motion([per[0], per[-1]] if len(per) % 2 == 1 else [per[0], per[-2]], pix)
    jump = float(np.median(jumps))
    d["motion"] = {**drift, "jump_arcsec": round(jump, 1), "jump_spherex_px": round(jump / NATIVE, 1),
                   # two looks from opposite sides of Earth's orbit are 2 au apart: distance = 2 au / jump angle
                   "distance_au": round(2.0 / math.radians(jump / 3600.0), 0) if jump > 0 else None}
    d["confidence"] = round(min(0.9, 0.3 + 0.15 * (len(per) - 2)), 2)
    return d


DEEP_MIN_EXPOSURES = 5  # a visit needs this many exposures for its stack to be searched on its own


def _stack(frames: list[Frame], idx: list[int]) -> Frame:
    """The exposures of one visit added together: the median of each pixel (so cosmic rays and fast movers
    drop out), scaled so that the noise is 1 again. Its sources are found like those of any exposure."""
    cube = np.array([frames[i].img for i in idx], dtype=np.float32)
    cnt = np.isfinite(cube).sum(axis=0)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        med = np.nanmedian(cube, axis=0)
    img = np.where(cnt >= 3, med * np.sqrt(np.maximum(cnt, 1)) / 1.2533, np.nan)
    mid = frames[idx[len(idx) // 2]]
    gain = math.sqrt(len(idx)) / 1.2533
    fr = Frame(mid.id, float(np.mean([frames[i].mjd for i in idx])), mid.date, float(np.mean([frames[i].wl for i in idx])), img, mid.pix,
               float(np.median([frames[i].sigma for i in idx])) / gain)
    find_sources(fr)
    return fr


def _deep_drifts(frames, visit, pix, n, ra0, dec0, size_deg, taken, to_mjy) -> list[dict]:
    """Slow movers too faint for single exposures.

    Each visit's exposures are added together; the sources of every deep picture are matched from visit
    to visit; what is left of the misalignment is taken out with the stars themselves. A source whose
    position then shifts by half a SPHEREx pixel or more, and by six times the scatter of the ordinary
    stars, is reported as a slow drift. ``taken`` are places already explained by another doodle."""
    s = NATIVE / pix
    groups = [[i for i in range(len(frames)) if visit[i] == v] for v in sorted({int(v) for v in visit})]
    stacks = [(g, _stack(frames, g)) for g in groups if len(g) >= 3]
    deep = [k for k, (g, _) in enumerate(stacks) if len(g) >= DEEP_MIN_EXPOSURES]
    if len(deep) < 2 or stacks[deep[-1]][1].mjd - stacks[deep[0]][1].mjd < 60:
        return []
    ref = stacks[deep[0]][1]
    chains = []  # the same source in every deep picture
    for i in range(len(ref.x)):
        chain, prev, pi = [i], ref, i
        for k in deep[1:]:
            fr = stacks[k][1]
            if not len(fr.x):
                chain = None
                break
            j = int(np.argmin(np.hypot(fr.x - prev.x[pi], fr.y - prev.y[pi])))
            # each must be the other's nearest neighbour: of two close stars, one must not be taken for the other
            back = int(np.argmin(np.hypot(prev.x - fr.x[j], prev.y - fr.y[j])))
            if back != pi or math.hypot(fr.x[j] - prev.x[pi], fr.y[j] - prev.y[pi]) > 2.5 * s or not 0.6 < fr.flux[j] / max(prev.flux[pi], 1e-9) < 1.7:
                chain = None
                break
            chain.append(j)
            prev, pi = fr, j
        if chain:
            chains.append(chain)
    if len(chains) < 6:  # too few stars to tell a real shift from a misalignment
        return []
    X = np.array([[stacks[k][1].x[c[m]] for m, k in enumerate(deep)] for c in chains])  # [source, deep picture], grid px
    Y = np.array([[stacks[k][1].y[c[m]] for m, k in enumerate(deep)] for c in chains])
    off_x, off_y = np.median(X - X[:, :1], axis=0), np.median(Y - Y[:, :1], axis=0)  # what is left of the misalignment between visits
    X, Y = X - off_x, Y - off_y
    dx, dy = X[:, -1] - X[:, 0], Y[:, -1] - Y[:, 0]
    disp = np.hypot(dx, dy)
    scatter = max(1.4826 * float(np.median(np.abs(np.r_[dx, dy]))), 0.05 * s)  # how far ordinary stars seem to move, per axis
    t_deep = np.array([stacks[k][1].mjd for k in deep])
    out = []
    for c, chain in enumerate(chains):
        if disp[c] < 0.5 * s or disp[c] < 6.0 * scatter:
            continue
        frs = [stacks[k][1] for k in deep]
        peaks = [float(fr.peak[j]) for fr, j in zip(frs, chain)]
        # clear in the deep pictures, yet too faint to be followed in single exposures (those are searched above)
        if min(peaks) < 8.0 or max(peaks) > 45.0:
            continue
        edge = 4.0 * s
        if min(X[c].min(), Y[c].min()) < edge or max(X[c].max(), Y[c].max()) > n - 1 - edge:
            continue
        # a neighbour pulls the measured centre of a source around: a comparable one within four pixels, or a much brighter one a little farther
        def crowded(fr, j):
            r = np.hypot(fr.x - fr.x[j], fr.y - fr.y[j])
            r[j] = np.inf
            return bool(np.any((r < 4.0 * s) & (fr.peak > 0.4 * fr.peak[j])) or np.any((r < 7.0 * s) & (fr.peak > 20.0 * fr.peak[j])))

        if any(crowded(fr, j) for fr, j in zip(frs, chain)):
            continue
        if any(math.hypot(X[c, 0] - qx, Y[c, 0] - qy) < 2.5 * s for qx, qy in taken):
            continue
        vx, vy, rms = _fit_line(t_deep, X[c] * pix, Y[c] * pix)  # arcsec per day
        if len(deep) >= 3 and rms > max(0.25 * NATIVE, 0.15 * disp[c] * pix):  # three or more visits must fall on one straight line
            continue
        # one sighting per visit: the deep pictures as measured, shallower visits where the straight line says to look
        tm, xm, ym = float(t_deep.mean()), float(X[c].mean()), float(Y[c].mean())
        seen = []
        for k, (g, fr) in enumerate(stacks):
            if k in deep:
                m = deep.index(k)
                x, y, flux, peak = float(X[c, m]), float(Y[c, m]), float(fr.flux[chain[m]]), float(fr.peak[chain[m]])
            else:
                gx, gy = xm + vx * (fr.mjd - tm) / pix, ym + vy * (fr.mjd - tm) / pix
                cx, cy, fl, _, _ = _photometry(fr.img, np.array([[gx, gy]]), pix)
                yi, xi = int(round(float(cy[0]))), int(round(float(cx[0])))
                if not (1 <= xi < n - 1 and 1 <= yi < n - 1):
                    continue
                peak = float(np.nanmax(fr.img[yi - 1:yi + 2, xi - 1:xi + 2]))
                if not np.isfinite(peak) or peak < 3.0 or math.hypot(float(cx[0]) - gx, float(cy[0]) - gy) > s or fl[0] <= 0:
                    continue
                x, y, flux = float(cx[0]), float(cy[0]), float(fl[0]) * fr.sigma
            seen.append((k, g, fr, x, y, flux, peak))
        tt = np.array([q[2].mjd for q in seen])
        # how well each visit pins the position down: the stars' own scatter, plus the noise of a faint source (about 3"/signal-to-noise)
        sig = np.array([math.hypot(scatter * pix, 3.0 / max(q[6], 1.0)) for q in seen])
        vx, vy, rms, v_err = _fit_line_weighted(tt, np.array([q[3] for q in seen]) * pix, np.array([q[4] for q in seen]) * pix, sig)
        days = float(tt.max() - tt.min())
        dist = math.hypot(vx, vy) * days
        if dist < 0.5 * NATIVE:
            continue
        pts = []
        for k, g, fr, x, y, flux, peak in seen:
            ra, dec = pix_to_sky(x, y, ra0, dec0, size_deg, n)
            each = [forced_flux(frames[i], np.array([x]), np.array([y]))[0] for i in g]
            pts.append({
                "t": fr.mjd, "date": fr.date[:19], "frame": fr.id, "frames": [frames[i].id for i in g], "x": round(x, 2), "y": round(y, 2),
                "ra": round(float(ra), 6), "dec": round(float(dec), 6), "n": len(g), "flux": round(flux, 2), "peak_sigma": round(peak, 1),
                "wavelength_um": round(fr.wl, 4), "visit": int(visit[g[0]]),
                "spec": [[frames[i].wl, float(v) * to_mjy, frames[i].id] for i, v in zip(g, each) if np.isfinite(v)],
            })
        snr = float(disp[c] / scatter)
        pa = math.degrees(math.atan2(-vx, -vy)) % 360.0
        d = _base("arrow", pts)
        d["motion"] = {
            "dist_arcsec": round(dist, 2), "dist_spherex_px": round(dist / NATIVE, 2), "dist_grid_px": round(dist / pix, 2), "pa_deg": round(pa, 1),
            "direction": compass(pa), "days": round(days, 2), "rate_arcsec_per_year": round(dist / days * 365.25, 3),
            "rate_arcsec_per_hour": round(dist / days / 24.0, 6), "fit_rms_arcsec": round(rms, 2), "snr": round(snr, 1),
            "rate_err_arcsec_per_year": round(max(v_err, rms / max(days, 1.0)) * 365.25, 2),
        }
        d["confidence"] = round(min(0.9, 0.35 + 0.03 * snr), 2)
        d["deep"] = {"visits": len(pts), "exposures": sum(len(q[1]) for q in seen), "star_scatter_arcsec": round(scatter * pix, 2)}
        out.append(d)
    return out


def _drift(dets, ids, pix):
    """Slow, steady motion of a source that is otherwise always there (proper motion)."""
    t = np.array([dets[k].t for k in ids])
    if t.max() - t.min() < 60:
        return None
    x = np.array([dets[k].x for k in ids]) * pix
    y = np.array([dets[k].y for k in ids]) * pix
    vx, vy, rms = _fit_line(t, x, y)
    days = float(t.max() - t.min())
    dist = math.hypot(vx, vy) * days
    err = max(rms, 0.3) * math.sqrt(12.0 / len(ids))  # uncertainty of the end-to-end shift, arcsec
    snr = dist / err
    if dist < 0.5 * NATIVE or snr < 6.0:
        return None
    pa = math.degrees(math.atan2(-vx, -vy)) % 360.0
    return {
        "dist_arcsec": round(dist, 2), "dist_spherex_px": round(dist / NATIVE, 2), "dist_grid_px": round(dist / pix, 2), "pa_deg": round(pa, 1),
        "direction": compass(pa), "days": round(days, 2), "rate_arcsec_per_year": round(dist / days * 365.25, 3),
        "rate_arcsec_per_hour": round(dist / days / 24.0, 6), "fit_rms_arcsec": round(rms, 2), "snr": round(snr, 1),
        "rate_err_arcsec_per_year": round(err / days * 365.25, 2),
    }


def _variability(dets, ids, frames, visit):
    """Brightness that differs from visit to visit after allowing for the colour of each exposure."""
    vis = np.array([visit[dets[k].f] for k in ids])
    if len(set(vis.tolist())) < 2 or len(ids) < 6:
        return None
    flux = np.array([dets[k].flux for k in ids])
    wl = np.array([frames[dets[k].f].wl for k in ids])
    rel = flux / np.median(flux)
    # every exposure has its own infrared colour; take out this object's smooth colour trend first
    deg = 2 if len(ids) >= 14 and np.ptp(wl) > 0 else (1 if np.ptp(wl) > 0 else 0)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        trend = np.polyval(np.polyfit(wl - wl.mean(), rel, deg), wl - wl.mean()) if deg else np.ones_like(rel)
    res = rel / np.clip(trend, 0.2, None)
    levels, errs = [], []
    for v in sorted(set(vis.tolist())):
        r = res[vis == v]
        if len(r) < 2:
            continue
        levels.append(float(np.median(r)))
        errs.append(float(1.4826 * np.median(np.abs(r - np.median(r))) / math.sqrt(len(r))) + 0.02)
    if len(levels) < 2:
        return None
    hi, lo = int(np.argmax(levels)), int(np.argmin(levels))
    amp = levels[hi] / max(levels[lo], 1e-6)
    snr = (levels[hi] - levels[lo]) / math.hypot(errs[hi], errs[lo])
    if amp < 1.3 or snr < 6.0:
        return None
    mid = float(np.median(levels))
    change = "brightened" if levels[hi] / mid - 1.0 >= 1.0 - levels[lo] / mid else "dimmed"
    t = np.array([dets[k].t for k in ids])
    order = np.argsort(t)
    return {"change": change, "change_pct": round((amp - 1) * 100.0, 0), "levels": [round(v, 3) for v in levels], "snr": round(snr, 1),
            # every exposure: time (MJD), brightness relative to this object's own middle value after its colour trend is taken out, visit
            "curve": [[round(float(t[i]), 4), round(float(res[i]), 3), int(vis[i])] for i in order],
            "errors": [round(e, 3) for e in errs]}


# --------------------------------------------------------------------------- words


# Wavelengths (µm) where common gases glow, for the hint under the spectrum. A match is a hint, never proof.
SPECTRAL_FEATURES = [
    (1.083, "helium gas", ""), (1.282, "hydrogen gas", ""), (1.875, "hydrogen gas", ""), (2.166, "hydrogen gas", ""),
    (2.66, "water vapour", " Comets give off this gas when sunlight warms their ice."),
    (3.29, "sooty carbon molecules", ""), (4.05, "hydrogen gas", ""),
    (4.26, "carbon dioxide gas", " Comets give off this gas when sunlight warms their ice."),
    (4.67, "carbon monoxide gas", " Comets give off this gas when sunlight warms their ice."),
]


def _resolving_power(wl: float) -> float:
    """SPHEREx spectral resolving power: about 41 in bands 1-3, 35 in band 4, 110 in band 5, 130 in band 6."""
    return 41.0 if wl < 2.42 else 35.0 if wl < 3.82 else 110.0 if wl < 4.42 else 130.0


def _faint_spectrum(every: list, pts: list) -> dict:
    """An object too faint for single exposures: each measurement is mostly noise (some come out below zero), so the
    spectrum is read from the middle value of groups of neighbouring wavelengths."""
    out = {"unit": "mJy", "aperture_arcsec": round(1.5 * NATIVE, 1), "faint": True,
           "points": [{"wl": round(w, 4), "mjy": float(f"{f:.4g}"), "frame": i} for w, f, i in pts]}
    groups = np.array_split(np.arange(len(every)), min(5, len(every) // 6))
    wl = np.array([q[0] for q in every])
    fx = np.array([q[1] for q in every])
    mid = np.array([float(np.median(fx[g])) for g in groups])
    err = np.array([1.2533 * 1.4826 * float(np.median(np.abs(fx[g] - np.median(fx[g])))) / math.sqrt(len(g)) for g in groups])
    out["binned"] = [[round(float(np.mean(wl[g])), 4), float(f"{max(m, 0.0):.4g}"), float(f"{e:.3g}")] for g, m, e in zip(groups, mid, err)]
    per = len(every) // len(groups)
    lead = f"It is faint: every dot is one noisy exposure, so the line joins the middle value of each {per} neighbouring measurements. "
    blue, red, noise = float(mid[0]), float(mid[-1]), 3.0 * float(np.hypot(err[0], err[-1]))
    span = f"From {wl[0]:.2f} to {wl[-1]:.2f} µm"
    if blue > 0 and red > 1.3 * blue and red - blue > noise:
        out["hint"] = lead + f"{span} it gets brighter toward longer wavelengths, about {red / blue:.1f} times. Very cool objects do that."
    elif red > 0 and blue > 1.3 * red and blue - red > noise:
        out["hint"] = lead + f"{span} it fades toward longer wavelengths, about {blue / red:.1f} times."
    elif blue <= 0 < red and red > noise:
        out["hint"] = lead + f"It only shows at the long-wavelength end, near {wl[-1]:.2f} µm. Very cool objects do that."
    else:
        out["hint"] = lead + f"{span} no clear change of brightness stands out of the noise."
    return out


def _point_scatter(pts: list) -> float:
    """Robust scatter of the single measurements around a straight line through them."""
    w, f = np.array([q[0] for q in pts]), np.array([q[1] for q in pts])
    r = f - np.polyval(np.polyfit(w, f, 1), w) if len({round(float(v), 3) for v in w}) > 1 else f - np.median(f)
    return 1.4826 * float(np.median(np.abs(r - np.median(r))))


def spectrum(spec: list, kind: str = "", faint: bool = False) -> dict | None:
    """Brightness at every wavelength the object was measured at, with a careful plain-language reading.

    ``spec`` is a list of [wavelength in µm, flux in mJy, exposure id]. Each SPHEREx exposure sees a
    given spot of sky at one wavelength, so the exposures of one object add up to a piece of its spectrum.
    The flux is a small-aperture sum (radius 1.5 SPHEREx pixels) without aperture correction: approximate.
    """
    every = sorted(([float(w), float(f), str(i)] for w, f, i in spec if w and w > 0 and f is not None and math.isfinite(f)), key=lambda q: q[0])
    pts = [q for q in every if q[1] > 0]
    if not pts:
        return None
    if faint and len(every) >= 12:
        return _faint_spectrum(every, pts)
    out = {"unit": "mJy", "aperture_arcsec": round(1.5 * NATIVE, 1),
           "points": [{"wl": round(w, 4), "mjy": float(f"{f:.4g}"), "frame": i} for w, f, i in pts]}
    # one value per wavelength: repeat visits to the same wavelength are combined, so a change with time is not read as colour
    bins: list[list[list[float]]] = []
    for w, f, _ in pts:
        if bins and w - bins[-1][-1][0] < 0.25 * w / _resolving_power(w):
            bins[-1].append([w, f])
        else:
            bins.append([[w, f]])
    wl = np.array([float(np.mean([q[0] for q in g])) for g in bins])
    fx = np.array([float(np.median([q[1] for q in g])) for g in bins])
    if len(wl) < 4:
        out["hint"] = "These exposures cover too few different wavelengths to read a pattern. Another colour band shows a different piece of the spectrum."
        return out
    k = int(np.argmax(fx))
    rw, rf = np.delete(wl, k), np.delete(fx, k)
    base = float(np.median(rf))
    resid = rf - np.polyval(np.polyfit(rw, rf, 1), rw)
    mad = 1.4826 * float(np.median(np.abs(resid - np.median(resid))))
    when = " Each point is a separate exposure, taken at a different time."
    if kind == "pulse":
        when += " This object also changes with time, so colour and change are mixed here."
    raised = (fx > 1.5 * base) & (fx - base > 6.0 * mad)
    if base <= 0:
        return out
    if raised[k] and (raised.sum() >= 2 or mad / base <= 0.15):
        w = float(wl[k])
        near = min(SPECTRAL_FEATURES, key=lambda f: abs(f[0] - w))
        text = f"It is about {fx[k] / base:.0f} times brighter" if fx[k] / base >= 10 else f"It is about {fx[k] / base:.1f} times brighter"
        text += f" near {w:.2f} µm than at the other wavelengths measured here."
        if abs(near[0] - w) <= 0.6 * w / _resolving_power(w):
            text += f" {near[1].capitalize()} glows at {near[0]:.2f} µm, so that is one possible reason: a hint, not proof.{near[2]}"
        else:
            text += " One wavelength standing out like that can be glowing gas."
        if raised.sum() >= 2:
            text += " The wavelengths next to it are raised too, so this is not one bad measurement."
        elif kind in ("tail", "spark", "zigzag"):
            text += " It can also be a faint star behind the object in that one exposure, or one bad measurement."
        else:
            text += " It can also be a brief flare, or one bad measurement."
        out["hint"], out["peak_um"] = text, round(w, 3)
    elif max(mad, _point_scatter(pts)) / base > 0.15:
        out["hint"] = ("The measurements scatter too much to read a pattern. That happens when an object is so bright that it overloads the detector, "
                       "or when it is changing while SPHEREx watches." + when)
    else:
        third = max(1, len(fx) // 3)
        blue, red = float(np.median(fx[:third])), float(np.median(fx[-third:]))
        noise = 3.0 * mad / math.sqrt(third)
        span = f"From {float(wl[0]):.2f} to {float(wl[-1]):.2f} µm"
        if red > 1.2 * blue and red - blue > noise:
            out["hint"] = f"{span} it gets brighter toward longer wavelengths, by about {100 * (red / blue - 1):.0f}%. Cool or dusty objects do that."
        elif red < blue / 1.2 and blue - red > noise:
            out["hint"] = f"{span} it fades toward longer wavelengths, by about {100 * (1 - red / blue):.0f}%. Warm stars and reflected sunlight do that."
        else:
            out["hint"] = f"{span} it is about equally bright: no strong colour inside this band."
        out["hint"] += when
    return out


def explain(d: dict) -> None:
    """Plain-language text for the Object Card. Careful wording: candidates, never discoveries."""
    kind, m, pts = d["type"], d.get("motion") or {}, d["points"]
    known = d.get("known")
    who = f"This is {known['name']}, a known {known.get('kind', 'object')} ({known.get('source', 'catalogue')})." if known else ""
    if known and known.get("catalog_pm_arcsec_per_year") and m.get("rate_arcsec_per_year"):
        pm = f"{m['rate_arcsec_per_year']:.1f}" + (f" ± {m['rate_err_arcsec_per_year']:.1f}" if m.get("rate_err_arcsec_per_year") else "")
        who += f" The catalogue lists {known['catalog_pm_arcsec_per_year']:.2f} arcseconds a year; these images give {pm}."
    if kind in ("spark", "tail") and m:
        speed = m.get("rate_arcsec_per_hour", 0)
        what = "A fuzzy object with a glow around it" if kind == "tail" else "A point of light"
        text = (f"{what} that moved {m['dist_arcsec']:.0f} arcseconds ({m['dist_spherex_px']:.1f} SPHEREx pixels) toward the {m['direction']} "
                f"in {_span(m['days'])}, about {speed:.0f} arcseconds per hour, while the stars stayed put. "
                "Only bodies inside our Solar System cross the sky that fast: an asteroid, or a comet if it looks fuzzy.")
    elif kind in ("spark", "tail"):
        text = ("Something was here in one group of exposures and not in the others. It may be an asteroid or comet caught once, "
                "an object that shines in only one infrared colour, or a flaw in the image.")
    elif kind == "arrow":
        opening = ("Too faint to stand out in a single exposure, this one appears when each visit's exposures are added together. It slides steadily"
                   if d.get("deep") else "This one is always there but slides steadily")
        text = (f"{opening} toward the {m['direction']}: {m['dist_arcsec']:.1f} arcseconds "
                f"({m['dist_spherex_px']:.1f} SPHEREx pixels) in {_span(m['days'])}, about {m['rate_arcsec_per_year']:.1f} arcseconds a year. "
                "Steady drift like this is how a nearby star or brown dwarf looks from Earth."
                + (" (Something this close also wobbles with the seasons, by up to an arcsecond: over a year or so that wobble is part of the number.)"
                   if m.get("rate_arcsec_per_year", 0) >= 2.0 and m.get("days", 0) < 900 else ""))
    elif kind == "zigzag":
        text = (f"It appears to jump about {m['jump_arcsec']:.0f} arcseconds back and forth between visits six months apart. SPHEREx looks at each "
                "patch of sky from opposite sides of Earth's orbit, so a body far beyond Neptune would do exactly that. "
                + (f"If it is real, the size of the jump puts it roughly {m['distance_au']:.0f} times as far from the Sun as Earth is." if m.get("distance_au") else "")
                + (" Three sightings can also line up by chance, so this is a weak candidate until another visit repeats the pattern." if len(pts) <= 3 else ""))
    else:
        b = d.get("brightness") or {}
        if b.get("change_pct"):
            text = (f"It stays in the same place but {b['change']} by about {b['change_pct']:.0f}% between visits, after allowing for the different "
                    "infrared colour of each exposure. Stars that pulse, flare or get eclipsed do this.")
        else:
            text = "It was at this spot during one visit and gone in another: something that appeared, or faded away."
    if known:
        tail = f" {who}"
    elif d.get("status") == "unchecked":
        tail = " The catalogue services could not be reached just now, so we cannot say yet whether it is already known."
    else:
        where = " and ".join(d.get("checked") or ["the catalogues"])
        tail = f" It did not match anything in {where}, so it is only a candidate: it needs more images and an expert before anyone can say what it is."
    d["explain"] = text + tail


def _span(days: float) -> str:
    if days < 2.0 / 24:
        return f"{days * 1440:.0f} minutes"
    if days < 2:
        return f"{days * 24:.1f} hours"
    if days < 90:
        return f"{days:.0f} days"
    return f"{days / 30.44:.0f} months"
