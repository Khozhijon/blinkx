"""Offline unit tests (no network): python -m pytest -q"""
import math

import numpy as np
import pytest
from astropy.io import fits

from backend import resolver, spherex as sx
from backend.main import _visits


def test_parse_position_decimal_and_sexagesimal():
    assert resolver.parse_position("269.4486 +4.7680") == (269.4486, 4.768)
    assert resolver.parse_position("269.4486, -4.7680") == (269.4486, -4.768)
    ra, dec = resolver.parse_position("17h57m48.5s +04d41m36s")
    assert ra == pytest.approx(269.45208, abs=1e-4) and dec == pytest.approx(4.69333, abs=1e-4)
    ra, dec = resolver.parse_position("17:57:48.5 +04:41:36")
    assert ra == pytest.approx(269.45208, abs=1e-4)
    assert resolver.parse_position("Barnard's star") is None
    assert resolver.parse_position("M 31") is None
    with pytest.raises(resolver.ResolveError):
        resolver.parse_position("400 10")


def test_wave_tab_lookup_is_bilinear():
    # 3 x 2 control grid over a 100 x 50 pixel detector: wavelength = 1 + x/100, bandwidth = 0.01 + y/1000
    xv, yv = np.array([1.0, 51.0, 101.0]), np.array([1.0, 51.0])
    values = np.zeros((2, 3, 2))
    for j, y in enumerate(yv):
        for i, x in enumerate(xv):
            values[j, i] = (1 + (x - 1) / 100, 0.01 + (y - 1) / 1000)
    hdr = fits.Header()
    wl, bw = sx.wavelength_at(hdr, (xv, yv, values), 25.0, 10.0)  # 0-based pixel
    assert wl == pytest.approx(1.25) and bw == pytest.approx(0.02)
    # outside the table: clamps to the edge instead of extrapolating
    wl, _ = sx.wavelength_at(hdr, (xv, yv, values), 500.0, 10.0)
    assert wl == pytest.approx(2.0)
    # a cutout shifts CRPIXnW; the lookup must follow it
    hdr["CRPIX1W"] = -9.0  # cutout starts 10 pixels into the full frame
    wl, _ = sx.wavelength_at(hdr, (xv, yv, values), 15.0, 10.0)
    assert wl == pytest.approx(1.25)


def test_parse_wave_table_from_file_tail():
    cols = [
        fits.Column(name="X", format="3J", array=np.array([[1, 51, 101]])),
        fits.Column(name="Y", format="2J", array=np.array([[1, 51]])),
        fits.Column(name="VALUES", format="12E", dim="(2,3,2)", array=np.arange(12, dtype="f4").reshape(1, 2, 3, 2)),
    ]
    hdu = fits.BinTableHDU.from_columns(cols, name="WCS-WAVE")
    import io

    buf = io.BytesIO()
    fits.HDUList([fits.PrimaryHDU(), fits.ImageHDU(np.zeros((4, 4), "f4")), hdu]).writeto(buf)
    raw = buf.getvalue()[-4 * sx.BLOCK :]
    x, y, values = sx._parse_wave_table(raw)
    assert x.tolist() == [1, 51, 101] and y.tolist() == [1, 51]
    assert values.shape == (2, 3, 2) and values[1, 2].tolist() == [10.0, 11.0]


def test_tangent_grid_is_north_up_east_left():
    ra0, dec0, size, n = 120.0, 35.0, 0.1, 128
    ra, dec = sx._tangent_grid(ra0, dec0, size, n)
    c = n // 2
    assert dec[0, c] > dec[-1, c]  # top row is north
    assert ra[c, 0] > ra[c, -1]  # left column is east (larger RA)
    assert abs(dec[0, c] - dec[-1, c] - size * (n - 1) / n) < 1e-6
    # the four central pixels straddle the target
    assert np.mean(ra[c - 1 : c + 1, c - 1 : c + 1]) == pytest.approx(ra0, abs=1e-7)
    assert np.mean(dec[c - 1 : c + 1, c - 1 : c + 1]) == pytest.approx(dec0, abs=1e-7)


def test_encode_decode_roundtrip_and_mask():
    rng = np.random.default_rng(1)
    img = rng.normal(0.3, 0.02, (128, 128)).astype(np.float32)
    img[60:63, 60:63] += 500.0  # a bright star
    img[:5, :5] = np.nan  # off the detector
    filled = np.zeros((128, 128), bool)
    filled[10, 20] = True
    meta = sx.encode_frame({"image": img, "filled": filled, "meta": {"n": 128}})
    back = sx.decode_frame(meta)
    assert np.isnan(back[:5, :5]).all() and np.isfinite(back[5:, 5:]).all()
    sky = img - meta["sky"]
    faint = np.abs(sky) < 5 * meta["sigma"]
    assert np.nanmax(np.abs(back - sky)[faint & np.isfinite(sky)]) < 0.02 * meta["sigma"]  # noise is kept exactly
    assert back[61, 61] == pytest.approx(sky[61, 61], rel=2e-3)  # bright pixels to 0.2 %
    assert meta["sigma"] == pytest.approx(0.02, rel=0.15)
    import base64

    bits = np.unpackbits(np.frombuffer(base64.b64decode(meta["filled"]), np.uint8))[: 128 * 128].reshape(128, 128)
    assert bits[10, 20] == 1 and bits.sum() == 1


def test_inpaint_fills_holes_from_neighbours():
    img = np.full((7, 7), 2.0, np.float32)
    img[3, 3] = 9999.0  # cosmic ray
    bad = np.zeros((7, 7), bool)
    bad[3, 3] = True
    out = sx._inpaint(img, bad, np.zeros((7, 7), bool))
    assert out[3, 3] == pytest.approx(2.0)
    # inside a saturated star the hole takes the brightest neighbour
    img2 = np.full((7, 7), 2.0, np.float32)
    img2[2, 3] = 800.0
    img2[3, 3] = np.nan
    bloom = np.zeros((7, 7), bool)
    bloom[3, 3] = True
    out2 = sx._inpaint(img2, np.isnan(img2), bloom)
    assert out2[3, 3] == pytest.approx(800.0)


def test_bilinear_matches_hand_value():
    src = np.array([[0.0, 10.0], [20.0, 30.0]], np.float32)
    out = sx._bilinear(src, np.array([[0.5]]), np.array([[0.5]]))
    assert out[0, 0] == pytest.approx(15.0)


def test_split_header_finds_data_offset():
    hdr = fits.Header()
    hdr["SIMPLE"] = True
    hdr["BITPIX"] = 8
    hdr["NAXIS"] = 0
    raw = hdr.tostring(endcard=True, padding=True).encode()
    parsed, end = sx._split_header(raw + b"\0" * 100, 0)
    assert end == sx.BLOCK and parsed["BITPIX"] == 8


def test_visits_group_by_gaps():
    exps = [{"mjd": 60900.0 + d, "detector": 2} for d in (0, 1, 2)] + [{"mjd": 61100.0, "detector": 3}]
    v = _visits(exps)
    assert [x["count"] for x in v] == [3, 1]
    assert v[0]["bands"] == [2] and v[1]["bands"] == [3]
    assert v[0]["start"].startswith("2025-08-13")


def test_grid_size_keeps_native_sampling():
    for size in (0.05, 0.1, 0.2, 0.4):
        assert size * 3600 / sx.grid_size(size) <= 6.15  # never coarser than a SPHEREx pixel
    assert math.isclose(sx.grid_size(0.1), 128)


def test_sia_votable_light_parser():
    xml = b"""<VOTABLE><RESOURCE type="results"><TABLE>
      <FIELD name="s_ra" datatype="double"/><FIELD name="energy_bandpassname" datatype="char" arraysize="*"><DESCRIPTION>x</DESCRIPTION></FIELD>
      <FIELD name="obs_id" datatype="char"/><FIELD name="access_url" datatype="char"/><FIELD name="t_exptime" datatype="double"/>
      <FIELD name="t_min" datatype="double" ID="c5"/><FIELD name="obs_collection" datatype="char"/>
      <DATA><TABLEDATA>
        <TR><TD>1.5</TD><TD>SPHEREx-D3</TD><TD>2026W33_2A_0594_4</TD><TD>https://x/ibe/data/spherex/qr3/a&amp;b.fits</TD><TD>113.5</TD><TD>61268.63</TD><TD>spherex_qr3</TD></TR>
        <TR><TD>2.5</TD><TD>SPHEREx-D6</TD><TD>2026W33_2A_0594_5</TD><TD>https://x/ibe/data/spherex/qr3/c.fits</TD><TD>113.5</TD><TD>61269.5</TD><TD/></TR>
      </TABLEDATA></DATA></TABLE></RESOURCE></VOTABLE>"""
    rows = sx.parse_sia_votable(xml)
    assert len(rows) == 2
    assert rows[0]["obs_id"] == "2026W33_2A_0594_4" and rows[0]["t_min"] == "61268.63"
    assert rows[0]["access_url"].endswith("a&b.fits") and rows[1]["energy_bandpassname"] == "SPHEREx-D6"
    assert rows[0]["obs_collection"] == "spherex_qr3" and rows[1]["obs_collection"] == ""
    with pytest.raises(sx.ArchiveError):
        sx.parse_sia_votable(b'<VOTABLE><INFO name="QUERY_STATUS" value="ERROR">bad</INFO></VOTABLE>')


def test_search_falls_back_to_saved_result_when_irsa_is_down(tmp_path, monkeypatch):
    from backend import cache

    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(cache, "SEED_DIR", tmp_path / "seed")
    rows = [{"id": "aD2", "obs_id": "a", "detector": 2, "collection": "spherex_dr1", "key": "dr1/a.fits", "mjd": 60900.0, "exptime": 113.6}]
    cache.put_seed("sia3/10.00000_20.00000", {"exposures": rows, "truncated": False})

    def down(*args, **kwargs):
        raise sx.ArchiveError("simulated outage")

    monkeypatch.setattr(sx, "_sia_all", down)
    monkeypatch.setattr(sx, "_irsa_down_until", 0.0)
    res = sx.search(10.0, 20.0)
    assert res["stale"] is True and res["exposures"] == rows
    assert sx.band_exposures(10.0, 20.0, 2)["stale"] is True
    # nothing saved for this spot: the list is worked out from the pointing index instead, and is not cached as if IRSA had said it
    from backend import pointings

    worked_out = {"exposures": [dict(rows[0], id="bD2", approx=True)], "truncated": False, "from_index": True}
    monkeypatch.setattr(pointings, "covering", lambda ra, dec, **kw: worked_out)
    assert sx.search(11.0, 20.0)["from_index"] is True and cache.get_json("sia3/11.00000_20.00000") is None
    assert sx.band_exposures(11.0, 20.0, 2)["from_index"] is True
    # without the index either, the error must surface
    monkeypatch.setattr(pointings, "covering", lambda ra, dec, **kw: None)
    monkeypatch.setattr(sx, "_irsa_down_until", 0.0)
    with pytest.raises(sx.ArchiveError):
        sx.search(11.0, 20.0)

    # when IRSA answers, the fresh result is used and cached
    monkeypatch.setattr(sx, "_irsa_down_until", 0.0)
    monkeypatch.setattr(sx, "_sia_all", lambda ra, dec, detector=None: {"exposures": rows * 1, "truncated": False})
    res = sx.search(11.0, 20.0)
    assert "stale" not in res and cache.get_json("sia3/11.00000_20.00000") is not None


def test_warm_up_never_raises(monkeypatch):
    class Boom:
        def head(self, *a, **k):
            raise RuntimeError("no network in tests")

    monkeypatch.setattr(sx, "client", lambda: Boom())
    monkeypatch.setattr(sx, "WARM", False)
    sx.warm_up()
    assert sx.WARM is True


def test_saved_index_is_used_first_while_it_is_recent(tmp_path, monkeypatch):
    import time as _time

    from backend import cache

    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(cache, "SEED_DIR", tmp_path / "seed")
    monkeypatch.setattr(sx, "_irsa_down_until", 0.0)
    rows = [{"id": "aD2", "obs_id": "a", "detector": 2, "collection": "spherex_dr1", "key": "dr1/a.fits", "mjd": 60900.0, "exptime": 113.6}]
    calls = []
    monkeypatch.setattr(sx, "_refresh_in_background", lambda ck, ra, dec: calls.append(ck))

    def must_not_wait(*args, **kwargs):
        raise AssertionError("a recent saved list must be returned without waiting for IRSA")

    monkeypatch.setattr(sx, "_sia_all", must_not_wait)
    cache.put_seed("sia3/10.00000_20.00000", {"exposures": rows, "truncated": False, "saved_at": int(_time.time()) - 3600})
    res = sx.search(10.0, 20.0)
    assert res["saved"] is True and res["exposures"] == rows and "stale" not in res
    assert calls == ["sia3/10.00000_20.00000"]  # a fresh list is requested behind the scenes

    # an old saved list is not trusted first: IRSA is asked
    fresh = [dict(rows[0], id="bD2")]
    monkeypatch.setattr(sx, "_sia_all", lambda ra, dec, detector=None: {"exposures": fresh, "truncated": False})
    cache.put_seed("sia3/12.00000_20.00000", {"exposures": rows, "truncated": False, "saved_at": int(_time.time()) - 60 * 86400})
    res = sx.search(12.0, 20.0)
    assert res["exposures"] == fresh and "saved" not in res


def test_pointing_index_finds_what_irsa_listed():
    """The record of where SPHEREx pointed proposes (almost) every exposure IRSA listed for Barnard's Star, and few others."""
    import glob
    import json

    from backend import pointings

    if not pointings.available():
        pytest.skip("seed/pointings.npz has not been built")
    path = glob.glob(str(sx.cache.SEED_DIR / "sia3" / "269.44622_4.76878*.json"))
    if not path:
        pytest.skip("no saved IRSA list for Barnard's Star")
    listed = {e["id"] for e in json.load(open(path[0]))["exposures"]}
    proposed = pointings.covering(269.44622, 4.76878)
    ids = {e["id"] for e in proposed["exposures"]}
    assert proposed["from_index"] and len(listed & ids) >= 0.995 * len(listed)
    assert len(ids) <= 1.4 * len(listed)  # candidates just outside a detector are allowed: the headers decide
    one = proposed["exposures"][0]
    assert one["key"].endswith(f"_{one['id']}_spx_{one['key'].split('/')[3]}.fits") and one["approx"] is True
    assert pointings.covering(269.44622, 4.76878, margin=90.0)["exposures"] == sorted(proposed["exposures"], key=lambda r: (r["mjd"], r["detector"]))


def test_pointing_geometry_on_a_made_up_pointing(monkeypatch):
    """One pointing looking at RA 100, Dec 0 with north up: which detectors see a target depends on where it falls."""
    import numpy as np

    from backend import pointings

    scale = 6.15 / 3600.0
    idx = {
        "week": np.array([0], np.uint16), "pt": np.array([7], np.uint16), "k0": np.array([1], np.uint8), "mjd": np.array([60900.0]),
        "ra": np.array([100.0]), "dec": np.array([0.0]), "pc": np.array([[-scale, 0.0, 0.0, scale]]), "ver": np.array([[0, 0, -1, -1]], np.int16),
        "weeks": ["dr1/2025W33_2C"], "versions": ["l2b-v27-2026-228"], "built": np.array(1), "week_versions": {0: {0}},
        "a0": np.radians(np.array([100.0])), "sin_d0": np.array([0.0]), "cos_d0": np.array([1.0]),
    }
    monkeypatch.setattr(pointings, "_index", idx)
    centre = pointings.covering(100.0, 0.0)["exposures"]
    assert {(e["obs_id"][-1], e["detector"]) for e in centre} == {("1", 2), ("1", 5), ("2", 2), ("2", 5)}  # exposures 3 and 4 were never taken
    assert centre[0]["key"] == "dr1/level2/2025W33_2C/l2b-v27-2026-228/2/level2_2025W33_2C_0007_1D2_spx_l2b-v27-2026-228.fits"
    assert centre[2]["mjd"] == pytest.approx(60900.0 + 128.9 / 86400.0, abs=1e-5)
    # 2275 pixels along +x (east is -x here, so that is to the west) lies on detectors 3 and 6
    side = pointings.covering(100.0 - 2275 * scale, 0.0)["exposures"]
    assert {e["detector"] for e in side} == {3, 6}
    # ten degrees away: nothing
    assert pointings.covering(110.0, 0.0)["exposures"] == []


def test_coordinates_and_names_as_the_challenge_writes_them():
    from backend import resolver

    ra, dec = resolver.parse_position("Right Ascension 08h55m10.831s, declination -7d14m42.53s")
    assert ra == pytest.approx(133.795129, abs=1e-5) and dec == pytest.approx(-7.245147, abs=1e-5)
    assert resolver.parse_position("RA 133.79513, Dec −7.24515") == pytest.approx((133.79513, -7.24515))
    assert resolver.parse_position("R Dra") is None and resolver.parse_position("RW Aurigae") is None
    assert resolver.canonical_name("Barnard’s Star") == "Barnard's star" and resolver.canonical_name("Vega’s twin") == "Vega's twin"
    assert resolver.canonical_name("WISE 0855") == "WISE J085510.83-071442.5"
    assert resolver.canonical_name("Epsilon Indi B") == "eps Ind B" and resolver.canonical_name("R Draconis") == "R Dra"


def test_gaia_table_is_parsed():
    from backend import gaia

    body = "\n".join([
        "#RESOURCE=yCat_1355", "#Name: I/355/gaiadr3", "", "Source\tRA_ICRS\tDE_ICRS\tGmag\tpmRA\tpmDE\tPlx",
        " \tdeg\tdeg\tmag\tmas/yr\tmas/yr\tmas", "-------------------\t---------------\t---------------\t---------\t---------\t---------\t---------",
        "4472832130942575872\t269.44850252544\t+04.73942005111\t 8.193974\t -801.551\t10362.394\t 546.9759",
        "4472836292758713216\t269.44387161153\t+04.79629141602\t11.862574\t         \t         \t         ", "",
    ])
    rows = gaia.parse_tsv(body)
    assert len(rows) == 2 and rows[0]["id"] == "4472832130942575872"
    assert rows[0]["pmdec"] == pytest.approx(10362.394) and rows[0]["plx"] == pytest.approx(546.9759) and rows[0]["g"] == pytest.approx(8.193974)
    assert rows[1]["pmra"] is None and rows[1]["plx"] is None and rows[1]["dec"] == pytest.approx(4.79629141602)


def test_a_drift_is_set_aside_when_an_older_survey_saw_a_source_on_the_spot(monkeypatch):
    from backend import catalogs, gaia

    doodle = {"id": "ARW-001", "type": "arrow", "motion": {"rate_arcsec_per_year": 4.2}, "points": [{"ra": 10.0909, "dec": 20.0779, "t": 61000.0}]}
    asked = []

    def fake(source, columns, ra, dec, radius):
        asked.append(source)
        return [{"_r": 0.5, "W1mag": 15.3}] if "allwise" in source else []

    monkeypatch.setattr(gaia, "vizier_near", fake)
    there = catalogs.already_there(doodle)
    assert there["survey"] == "WISE" and there["year"] == 2010 and there["sep_arcsec"] == 0.5
    # nothing on the spot in either survey: the drift stands
    monkeypatch.setattr(gaia, "vizier_near", lambda *a: [])
    assert catalogs.already_there(doodle) is None
    # a Gaia star that itself moves that fast is the object, not a contradiction
    monkeypatch.setattr(gaia, "vizier_near", lambda source, *a: [] if "allwise" in source else [{"_r": 1.0, "pmRA": -800.0, "pmDE": 10360.0}])
    fast = dict(doodle, motion={"rate_arcsec_per_year": 10.0})
    assert catalogs.already_there(fast) is None
    # the catalogue service is down: no verdict, the doodle is kept as a candidate
    monkeypatch.setattr(gaia, "vizier_near", lambda *a: None)
    assert catalogs.already_there(doodle) is None
