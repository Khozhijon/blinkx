"""Is a flagged object already known? Cross-checks against public catalogues.

* Solar-system bodies: IMCCE SkyBoT (asteroids and comets inside the field at that moment), plus
  JPL Horizons positions when a saved example carries them.
* Stars: SIMBAD (CDS, with the CfA mirror as fallback) for proper motions and variable-star types.

A doodle that matches becomes ``status: "known"``. One that does not stays ``"candidate"``. If a
catalogue service could not be reached, the doodle says so instead of pretending it was checked.
"""
from __future__ import annotations

import math

import httpx

from . import cache, gaia, skybot

SIMBAD_TAP = (
    "https://simbad.cfa.harvard.edu/simbad/sim-tap/sync",
    "https://simbad.cds.unistra.fr/simbad/sim-tap/sync",
)
VARIABLE_TYPES = {
    "V*", "Mi*", "LP*", "RR*", "Ce*", "cC*", "dS*", "Pu*", "Er*", "BY*", "RS*", "TT*", "Or*", "Ir*", "EB*", "El*", "SB*",
    "No*", "SN*", "CV*", "s*r", "s*b", "s*y", "AB*", "C*", "S*", "OH*", "sg*", "WV*", "RV*", "bC*", "a2*", "Ro*", "HB*", "Y*O", "Em*", "Be*",
}
OTYPE_WORDS = {
    "Mi*": "Mira-type variable star", "LP*": "long-period variable star", "RR*": "RR Lyrae variable star", "Ce*": "Cepheid variable star",
    "BY*": "nearby star (also a spotted, slightly variable one)", "EB*": "eclipsing binary star", "Er*": "flare star", "PM*": "high proper-motion star",
    "BD*": "brown dwarf", "LM*": "low-mass star", "WD*": "white dwarf", "**": "double star", "SB*": "binary star", "V*": "variable star",
    "TT*": "young variable star", "No*": "nova", "SN*": "supernova", "CV*": "cataclysmic variable star", "AB*": "evolved giant star", "C*": "carbon star",
}


def _sep_arcsec(ra1, dec1, ra2, dec2) -> float:
    return 3600.0 * math.hypot((ra1 - ra2) * math.cos(math.radians(dec1)), dec1 - dec2)


def _simbad(adql: str) -> list[dict] | None:
    """Rows as dicts, or None when no SIMBAD server answered."""
    ck = "simbad/" + adql
    hit = cache.get_json(ck, max_age=30 * 86400)
    if hit is not None:
        return hit
    for base in SIMBAD_TAP:
        try:
            r = httpx.get(base, params={"request": "doQuery", "lang": "adql", "format": "json", "query": adql}, timeout=25, follow_redirects=True)
            if r.status_code != 200:
                continue
            j = r.json()
            cols = [m["name"] for m in j["metadata"]]
            rows = [dict(zip(cols, row)) for row in j["data"]]
            cache.put_json(ck, rows)
            return rows
        except Exception:  # noqa: BLE001 - try the mirror
            continue
    return None


def fast_stars(ra0: float, dec0: float, size_deg: float) -> list[dict] | None:
    """Catalogued stars near the field that move more than 0.1 arcsec a year."""
    rad = size_deg * 0.75 + 0.12  # the catalogue lists year-2000 positions; fast stars have wandered since
    rows = _simbad(
        "SELECT TOP 300 main_id, ra, dec, pmra, pmdec, otype FROM basic "
        f"WHERE CONTAINS(POINT('ICRS', ra, dec), CIRCLE('ICRS', {ra0:.5f}, {dec0:.5f}, {rad:.4f})) = 1 "
        "AND pmra IS NOT NULL AND pmdec IS NOT NULL AND (pmdec > 70 OR pmdec < -70 OR pmra > 70 OR pmra < -70)"
    )
    return rows


def star_at(ra: float, dec: float, radius_arcsec: float = 8.0) -> list[dict] | None:
    return _simbad(
        "SELECT TOP 5 main_id, ra, dec, pmra, pmdec, otype FROM basic "
        f"WHERE CONTAINS(POINT('ICRS', ra, dec), CIRCLE('ICRS', {ra:.5f}, {dec:.5f}, {radius_arcsec / 3600.0:.5f})) = 1"
    )


def _clean_name(main_id: str) -> str:
    name = " ".join(str(main_id).split())
    return name[5:] if name.startswith("NAME ") else name


def _year(mjd: float) -> float:
    return 2000.0 + (mjd - 51544.5) / 365.25


def already_there(d: dict) -> dict | None:
    """Was a source sitting on this very spot years ago? Then it is not the fast mover it seems to be.

    A doodle that claims a drift of an arcsecond a year or more is checked against two earlier all-sky
    surveys: NASA's WISE (AllWISE, positions from 2010) and ESA's Gaia DR3 (2016.0). A source within
    2.5 arcseconds of where the doodle starts means nothing travelled there from far away.
    Returns what was found, or None (also None when the catalogue service did not answer)."""
    m = d.get("motion") or {}
    rate = m.get("rate_arcsec_per_year") or 0.0
    if d["type"] != "arrow" or rate < 1.0:
        return None
    p = d["points"][0]
    year = _year(p["t"])
    for source, cols, epoch, name in (("II/328/allwise", "RAJ2000,DEJ2000,W1mag,W2mag", 2010.5, "WISE"), ("I/355/gaiadr3", "RA_ICRS,DE_ICRS,Gmag,pmRA,pmDE", 2016.0, "Gaia")):
        if rate * (year - epoch) < 8.0:  # it would not have travelled far enough since then for this test to mean anything
            continue
        rows = gaia.vizier_near(source, cols, p["ra"], p["dec"], 2.5)
        for row in rows or []:
            pm = math.hypot(row.get("pmRA") or 0.0, row.get("pmDE") or 0.0) / 1000.0 if name == "Gaia" else 0.0
            if pm > 0.3 * rate:
                continue  # Gaia itself says this star moves about that fast
            return {"survey": name, "year": int(epoch), "sep_arcsec": round(float(row["_r"]), 1), "claimed_rate": round(rate, 1),
                    "ra": p["ra"], "dec": p["dec"], "id": d["id"]}
    return None


def expected_movers(doodles: list[dict], ra0: float, dec0: float, size_deg: float, mjd: float, min_pm: float = 1.0) -> list[dict]:
    """Catalogued fast movers that should be inside the field now but that no doodle explains.

    Being honest cuts both ways: when SIMBAD lists a star or brown dwarf moving an arcsecond a year or more
    here and the search did not flag it (too faint or too red in this band, or too little time between
    visits), the page says so instead of staying silent."""
    stars = fast_stars(ra0, dec0, size_deg)
    if not stars:
        return []
    named = {d["known"]["name"] for d in doodles if d.get("known")}
    dt = _year(mjd) - 2000.0
    half = size_deg / 2.0 * 0.94
    best: dict[tuple, dict] = {}
    for srow in stars:
        if str(srow.get("otype", "")).startswith("Pl"):
            continue
        pm = math.hypot(srow["pmra"], srow["pmdec"]) / 1000.0
        name = _clean_name(srow["main_id"])
        if pm < min_pm or name in named:
            continue
        dec_now = srow["dec"] + srow["pmdec"] * dt / 3.6e6
        ra_now = srow["ra"] + srow["pmra"] * dt / 3.6e6 / max(math.cos(math.radians(srow["dec"])), 1e-6)
        dx = (ra_now - ra0) * math.cos(math.radians(dec0))
        if abs(dx) > half or abs(dec_now - dec0) > half:
            continue
        if any(_sep_arcsec(ra_now, dec_now, q["ra"], q["dec"]) < 15.0 for d in doodles for q in d["points"][-1:]):
            continue  # a doodle sits on it (the catalogue check simply did not name it)
        row = {"name": name, "kind": OTYPE_WORDS.get(srow.get("otype"), "fast-moving star"), "pm_arcsec_per_year": round(pm, 2),
               "ra": round(ra_now, 5), "dec": round(dec_now, 5), "source": "SIMBAD"}
        key = (round(ra_now * 400), round(dec_now * 400))  # components of one system share a spot: keep the first
        best.setdefault(key, row)
    return sorted(best.values(), key=lambda r: -r["pm_arcsec_per_year"])[:4]


def annotate(doodles: list[dict], ra0: float, dec0: float, size_deg: float, predicted: dict | None = None, label: str | None = None, kind: str | None = None) -> dict:
    """Fill ``status`` / ``known`` on each doodle. Returns which catalogues answered.

    ``predicted`` maps frame id -> [ra, dec] of a body whose JPL Horizons track is known for this
    field (the saved examples); ``label``/``kind`` describe it.
    """
    from .detect import explain

    checked = {"skybot": None, "simbad": None, "horizons": bool(predicted)}
    stars = None
    for d in doodles:
        d["known"], d["status"], d["checked"] = None, "candidate", []
        pts = d["points"]
        if d["type"] in ("spark", "tail", "zigzag"):
            # 1) a track we already know from JPL Horizons
            if predicted:
                seps = [_sep_arcsec(p["ra"], p["dec"], *predicted[p["frame"]]) for p in pts if p["frame"] in predicted]
                if seps:
                    d["checked"].append("JPL Horizons")
                    if sorted(seps)[len(seps) // 2] < 15.0:
                        d["known"] = {"name": label, "kind": kind or "solar-system body", "source": "JPL Horizons", "sep_arcsec": round(sorted(seps)[len(seps) // 2], 1)}
            # 2) anything else catalogued that was in the field at that moment
            if not d["known"]:
                p = pts[len(pts) // 2]
                try:
                    objs = skybot.cone(ra0, dec0, size_deg, p["t"], max_vmag=None)
                    checked["skybot"] = True
                    d["checked"].append("IMCCE SkyBoT")
                    best = min(objs, key=lambda o: _sep_arcsec(p["ra"], p["dec"], o["ra"], o["dec"]), default=None)
                    if best is not None:
                        sep = _sep_arcsec(p["ra"], p["dec"], best["ra"], best["dec"])
                        comet = "comet" in str(best.get("class", "")).lower()
                        if sep < (90.0 if comet else 20.0):
                            name = f"({best['number']}) {best['name']}" if best.get("number") else best["name"]
                            d["known"] = {"name": name, "kind": "comet" if comet else "asteroid", "source": "IMCCE SkyBoT", "sep_arcsec": round(sep, 1), "vmag": best.get("vmag"), "class": best.get("class")}
                except skybot.SkybotError:
                    checked["skybot"] = False
        else:
            p = pts[-1]
            epoch = _year(p["t"])
            if d["type"] == "arrow":
                if stars is None:
                    stars = fast_stars(ra0, dec0, size_deg)
                    checked["simbad"] = stars is not None
                if stars is not None:
                    d["checked"].append("SIMBAD")
                best, best_sep = None, 12.0
                for srow in stars or []:
                    if str(srow.get("otype", "")).startswith("Pl"):
                        continue  # a planet of the star shares its position; we want the star itself
                    dt = epoch - 2000.0
                    dec_now = srow["dec"] + srow["pmdec"] * dt / 3.6e6
                    ra_now = srow["ra"] + srow["pmra"] * dt / 3.6e6 / max(math.cos(math.radians(srow["dec"])), 1e-6)
                    sep = _sep_arcsec(p["ra"], p["dec"], ra_now, dec_now)
                    if sep < best_sep:
                        best, best_sep = srow, sep
                if best:
                    pm = math.hypot(best["pmra"], best["pmdec"]) / 1000.0
                    pa = math.degrees(math.atan2(best["pmra"], best["pmdec"])) % 360.0
                    d["known"] = {
                        "name": _clean_name(best["main_id"]), "kind": OTYPE_WORDS.get(best.get("otype"), "nearby star"), "source": "SIMBAD",
                        "sep_arcsec": round(best_sep, 1), "catalog_pm_arcsec_per_year": round(pm, 3), "catalog_pm_pa_deg": round(pa, 1),
                    }
            else:  # pulse
                rows = star_at(p["ra"], p["dec"])
                checked["simbad"] = rows is not None if checked["simbad"] is None else checked["simbad"]
                if rows is not None:
                    d["checked"].append("SIMBAD")
                for srow in rows or []:
                    if srow.get("otype") in VARIABLE_TYPES:
                        d["known"] = {"name": _clean_name(srow["main_id"]), "kind": OTYPE_WORDS.get(srow["otype"], "variable star"), "source": "SIMBAD",
                                      "sep_arcsec": round(_sep_arcsec(p["ra"], p["dec"], srow["ra"], srow["dec"]), 1)}
                        break
        if d["known"]:
            d["status"] = "known"
        elif d["type"] == "arrow" and (there := already_there(d)):
            d["dismissed"] = there  # the caller drops it and reports why
        elif not d["checked"]:
            d["status"] = "unchecked"  # no catalogue could be reached: say so rather than call it new
        explain(d)
    return checked
