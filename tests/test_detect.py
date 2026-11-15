"""Change detection on a simulated field where the right answer is known (no network)."""
import math

import numpy as np
import pytest

from backend import detect, simulate, spherex as sx


@pytest.fixture(scope="module")
def found():
    sim = simulate.planet_x_field()
    frames = detect.frames_from_encoded(sim["frames"], sx.decode_frame)
    res = detect.detect(frames, 150.0, 2.0, sim["size_deg"])
    return res, sim["truth"]


def by_type(res, kind):
    return [d for d in res["doodles"] if d["type"] == kind]


def test_one_doodle_of_each_kind_and_nothing_else(found):
    res, _ = found
    assert sorted(d["type"] for d in res["doodles"]) == ["arrow", "pulse", "spark", "tail", "zigzag"]


def test_zigzag_gives_the_distance_of_the_planet(found):
    res, truth = found
    (z,) = by_type(res, "zigzag")
    assert z["epochs"] == 4
    assert z["motion"]["jump_arcsec"] == pytest.approx(truth["planet_jump_arcsec"], rel=0.12)
    assert z["motion"]["distance_au"] == pytest.approx(truth["planet_distance_au"], rel=0.15)


def test_arrow_measures_the_proper_motion(found):
    res, truth = found
    (a,) = by_type(res, "arrow")
    assert a["motion"]["rate_arcsec_per_year"] == pytest.approx(truth["star_pm_arcsec_per_year"], rel=0.1)
    assert a["motion"]["direction"] == "north-east"


def test_spark_and_tail_speeds(found):
    res, truth = found
    (s,) = by_type(res, "spark")
    (c,) = by_type(res, "tail")
    assert s["motion"]["rate_arcsec_per_hour"] == pytest.approx(truth["asteroid_arcsec_per_hour"], rel=0.08)
    assert c["motion"]["rate_arcsec_per_hour"] == pytest.approx(truth["comet_arcsec_per_hour"], rel=0.08)
    assert s["epochs"] == 1 and c["epochs"] == 1 and c["fuzzy"] is True


def test_pulse_brightened(found):
    res, truth = found
    (p,) = by_type(res, "pulse")
    assert p["brightness"]["change"] == "brightened"
    assert p["brightness"]["change_pct"] == pytest.approx(truth["variable_change_pct"], abs=20)


def test_words_never_claim_a_discovery(found):
    res, _ = found
    for d in res["doodles"]:
        text = d["explain"].lower()
        assert "candidate" in text and "discover" not in text.replace("not a discovery", "")
        assert d["status"] == "candidate" and d["known"] is None
        assert d["id"].split("-")[0] == detect.PREFIX[d["type"]] and len(d["nickname"].split()) >= 2


def test_alignment_is_reported_for_every_frame(found):
    res, _ = found
    assert len(res["align"]) == res["stats"]["frames"]
    assert all(a["offset_arcsec"] < 1.0 and a["method"].startswith("wcs") for a in res["align"].values())


def test_star_pattern_shift_is_found_and_reported():
    """If one exposure's coordinates are off, the stars give the shift back."""
    import numpy as np

    sim = simulate.planet_x_field(seed=3)
    frames = detect.frames_from_encoded(sim["frames"], sx.decode_frame)
    bad = frames[5]
    bad.img = np.roll(bad.img, (3, -4), axis=(0, 1))  # 3 px down, 4 px left
    res = detect.detect(frames, 150.0, 2.0, sim["size_deg"])
    a = res["align"][bad.id]
    assert a["method"] == "wcs+stars"
    assert a["shift_px"][0] == pytest.approx(-4, abs=0.4) and a["shift_px"][1] == pytest.approx(3, abs=0.4)
    assert math.hypot(a["dx_arcsec"], a["dy_arcsec"]) == pytest.approx(5 * frames[0].pix, rel=0.1)


def test_sky_pixel_round_trip():
    x, y = detect.sky_to_pix(*detect.pix_to_sky(40.0, 90.0, 201.3, -43.0, 0.2, 192), 201.3, -43.0, 0.2, 192)
    assert float(x) == pytest.approx(40.0, abs=1e-6) and float(y) == pytest.approx(90.0, abs=1e-6)


def test_small_demo_version_still_finds_all_five():
    """The saved offline demo uses a coarser grid and fewer exposures."""
    sim = simulate.planet_x_field(n=192, per_group=2)
    res = detect.detect(detect.frames_from_encoded(sim["frames"], sx.decode_frame), 150.0, 2.0, sim["size_deg"])
    assert sorted(d["type"] for d in res["doodles"]) == ["arrow", "pulse", "spark", "tail", "zigzag"]


def test_zigzag_must_close_like_a_real_orbit():
    """Three blips that line up by chance are not a planet: the yearly drift has to fit the distance the jump implies."""
    pix = 6.15

    def chain(jump_arcsec, drift_arcsec):
        a = {"x": 100.0, "y": 100.0, "t0": 0.0, "t1": 0.1}
        b = {"x": 100.0 + jump_arcsec / pix, "y": 100.0, "t0": 183.0, "t1": 183.1}
        c = {"x": 100.0, "y": 100.0 + drift_arcsec / pix, "t0": 366.0, "t1": 366.1}
        return [a, b, c]

    assert detect._zigzag_plausible(chain(825.0, 118.0), pix)       # 500 au: drifts about 116" a year
    assert not detect._zigzag_plausible(chain(245.0, 84.0), pix)    # 1700 au could drift only about 19" a year


def test_spectrum_reads_a_gas_line_but_not_a_change_with_time():
    # a comet-like spectrum: flat, with carbon dioxide glowing at 4.26 µm over two neighbouring channels
    wl = [3.96, 4.00, 4.03, 4.07, 4.10, 4.14, 4.18, 4.21, 4.25, 4.28, 4.32, 4.36]
    fx = [3.4, 3.1, 3.2, 3.7, 3.3, 3.6, 3.9, 4.0, 240.0, 150.0, 4.1, 3.8]
    sp = detect.spectrum([[w, f, f"E{i}"] for i, (w, f) in enumerate(zip(wl, fx))], "tail")
    assert len(sp["points"]) == 12 and sp["peak_um"] == pytest.approx(4.25)
    assert "Carbon dioxide gas" in sp["hint"] and "not proof" in sp["hint"]
    # a star that doubled in one visit, measured at the same four wavelengths every visit: that is time, not colour
    spec = [[w, 28.0 if visit == 2 else 14.0, f"V{visit}W{w}"] for visit in range(4) for w in (1.45, 1.47, 1.49, 1.51)]
    sp = detect.spectrum(spec, "pulse")
    assert "peak_um" not in sp and "changes with time" in sp["hint"]
    # too few wavelengths: no reading at all
    assert "too few" in detect.spectrum([[1.45, 5.0, "a"], [1.47, 5.1, "b"]], "spark")["hint"]


def _made_up_visits(mover_peak: float, shift_px: float, seed: int = 5):
    """Two visits of 12 exposures of a made-up star field with one faint source that moves between them."""
    rng = np.random.default_rng(seed)
    n, pix = 128, 2.8125
    yy, xx = np.mgrid[0:n, 0:n]
    blob = lambda x, y, peak: peak * np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (2 * 1.1**2))  # noqa: E731
    stars = [(rng.uniform(12, 116), rng.uniform(12, 116), rng.uniform(15, 120)) for _ in range(22)]
    stars = [s for s in stars if abs(s[0] - 64) > 14 or abs(s[1] - 64) > 14]  # keep the middle clear for the mover
    frames = []
    for v, mjd0 in enumerate((60900.0, 61080.0)):
        for k in range(12):
            img = rng.normal(0.0, 1.0, (n, n))
            for x, y, p in stars:
                img += blob(x, y, p)
            img += blob(64.0 + shift_px * v, 64.0, mover_peak)
            frames.append(detect.Frame(f"V{v}E{k}", mjd0 + 0.05 * k, f"2025-01-0{v + 1}T00:00:{k:02d}", 4.5 + 0.03 * k, img, pix, 0.02))
    return frames, pix


def test_deep_search_finds_a_mover_too_faint_for_single_exposures():
    # 4.5 times the noise in one exposure (below the 6-sigma detection limit); 3.2 grid pixels = 9 arcsec in six months
    frames, pix = _made_up_visits(mover_peak=4.5, shift_px=3.2)
    res = detect.detect(frames, 133.76, -7.24, 0.1)
    deep = [d for d in res["doodles"] if d.get("deep")]
    assert len(deep) == 1 and deep[0]["type"] == "arrow"
    m = deep[0]["motion"]
    assert m["dist_arcsec"] == pytest.approx(3.2 * pix, abs=1.5) and m["direction"] == "west"
    assert deep[0]["deep"]["exposures"] == 24 and "added together" in deep[0]["explain"]
    assert deep[0]["spectrum"]["faint"] is True and len(deep[0]["spectrum"]["binned"]) >= 2
    # the same field with nothing moving: no deep find
    still, _ = _made_up_visits(mover_peak=4.5, shift_px=0.0)
    assert not [d for d in detect.detect(still, 133.76, -7.24, 0.1)["doodles"] if d.get("deep")]


def test_full_spectrum_reading_is_careful():
    from backend import spectra

    def sp(points, bands, neighbour=None):
        out = {"points": points, "bands": bands, "neighbour_arcsec": neighbour, "visit": {"first": "2025-10-01", "last": "2025-10-14", "exposures": len(points)}}
        out["line"] = spectra._line(points)
        return out

    wl = [0.8 + 0.05 * i for i in range(84)]  # 0.8 ... 4.95
    band = lambda w: 1 if w < 1.1 else 2 if w < 1.65 else 3 if w < 2.42 else 4 if w < 3.82 else 5 if w < 4.42 else 6  # noqa: E731
    allbands = [{"band": b, "range_um": r, "exposures": 14, "on_spot": True} for b, r in zip(range(1, 7), ([0.75, 1.1], [1.1, 1.65], [1.65, 2.42], [2.42, 3.82], [3.82, 4.42], [4.42, 5.0]))]
    # a cool object: bright peaks, deep dips where water (1.4, 1.9) and methane (3.3) absorb
    cool = lambda w: 3.0 if 1.36 <= w <= 1.45 or 1.8 <= w <= 1.98 or 3.15 <= w <= 3.45 else 20.0  # noqa: E731
    text = spectra._read(sp([{"wl": w, "mjy": cool(w), "err": 0.2, "band": band(w), "frame": str(i), "ours": True} for i, w in enumerate(wl)], allbands))
    assert "water vapour absorbs" in text and "methane absorbs" in text and "one visit" in text
    # an object seen in the two longest bands only, with a neighbour 8 arcsec away: say so, and claim nothing below 3.8 microns
    faint = [{"wl": w, "mjy": 0.5 if w >= 3.82 else 0.4, "err": 0.1, "band": band(w), "frame": str(i), "ours": w >= 3.82} for i, w in enumerate(wl)]
    bands = [dict(b, on_spot=b["band"] >= 5) for b in allbands]
    text = spectra._read(sp(faint, bands, neighbour=7.6))
    assert "only from 3.8 to 5.0" in text and "neighbour 8″ away" in text and "absorbs" not in text
    assert all(p[0] >= 3.82 for p in spectra._line(faint))
    # a star far too bright: no reading of the wiggles
    text = spectra._read(sp([{"wl": w, "mjy": 9000.0 if i % 3 else 4000.0, "err": 5.0, "band": band(w), "frame": str(i), "ours": True} for i, w in enumerate(wl)], allbands))
    assert "overload" in text and "absorbs" not in text
    # nothing on the spot at all
    text = spectra._read(sp([dict(p, ours=False) for p in faint], [dict(b, on_spot=False) for b in allbands]))
    assert "Nothing sits on this exact spot" in text


def test_full_spectrum_choices():
    from backend import spectra

    # a field SPHEREx watches without a break: take the month that covers every colour band, not the whole year
    long_visit = [{"mjd": 61000.0 + 0.5 * i, "detector": 1 + (i % 6 if 200 <= i < 260 else i % 3)} for i in range(400)]
    month = spectra._best_month(long_visit)
    assert month[-1]["mjd"] - month[0]["mjd"] <= spectra.MAX_SPAN_DAYS and len({f["detector"] for f in month}) == 6
    short = [{"mjd": 61000.0 + i, "detector": 1 + i % 6} for i in range(12)]
    assert spectra._best_month(short) is short
    # an arrow is followed along its drift (east and north, arcseconds a year); a pulse stays put; movers and made-up objects get none
    arrow = {"type": "arrow", "motion": {"rate_arcsec_per_year": 10.0, "pa_deg": 90.0}, "points": [{"ra": 10.0, "dec": 5.0, "t": 61000.0}, {"ra": 10.003, "dec": 5.0, "t": 61365.25}]}
    assert spectra.doodle_args(arrow) == (10.003, 5.0, 10.0, 0.0, 61365.25)
    assert spectra.doodle_args(dict(arrow, type="pulse")) == (10.0, 5.0, 0.0, 0.0, None)
    assert spectra.doodle_args(dict(arrow, type="spark")) is None and spectra.doodle_args(dict(arrow, simulated=True)) is None
    assert spectra._where(10.0, 0.0, 3.6, -3.6, 61000.0, 61365.25) == (10.001, -0.001)
    # seen in bands 1, 3, 5 and 6 only: name the stretches, do not claim the gaps
    bands = [{"band": b, "range_um": r, "exposures": 14, "on_spot": b in (1, 3, 5, 6)} for b, r in zip(range(1, 7), ([0.75, 1.1], [1.1, 1.65], [1.65, 2.42], [2.42, 3.82], [3.82, 4.42], [4.42, 5.0]))]
    pts = [{"wl": 0.8 + 0.05 * i, "mjy": 5.0, "err": 0.1, "band": next(b["band"] for b in bands if b["range_um"][0] <= 0.8 + 0.05 * i <= b["range_um"][1] + 0.05), "frame": str(i), "ours": True} for i in range(84)]
    for p in pts:
        p["ours"] = p["band"] in (1, 3, 5, 6)
    sp = {"points": pts, "bands": bands, "neighbour_arcsec": None, "snapped_arcsec": 4.4, "visit": {"first": "2026-01-01", "last": "2026-01-20", "exposures": 84}}
    sp["line"] = spectra._line(pts)
    text = spectra._read(sp)
    assert "only at 0.8–1.1, 1.6–2.4 and 3.8–5.0 µm" in text or "only at 0.8–1.1, 1.7–2.4 and 3.8–5.0 µm" in text, text
    assert text.startswith("Measured on the source 4″ from the spot you chose.")
