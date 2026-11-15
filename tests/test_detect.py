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
