"""Turn what a person types ("Barnard's star", "269.45 +4.77", "17h57m48s +04d46m") into RA/Dec."""
from __future__ import annotations

import math
import re
import urllib.parse
import xml.etree.ElementTree as ET

import httpx
from astropy import units as u
from astropy.coordinates import SkyCoord

from . import cache

# CDS Sesame (SIMBAD -> NED -> VizieR) and its CfA mirror.
SESAME = (
    "https://cds.unistra.fr/cgi-bin/nph-sesame/-oxp/SNV?",
    "https://vizier.cfa.harvard.edu/viz-bin/nph-sesame/-oxp/SNV?",
)
# SPHEREx has been surveying since May 2025; nearby stars have moved since J2000, so we shift
# catalogue positions to roughly the middle of the survey so far before cutting images.
SURVEY_EPOCH = 2026.2

_NUM = r"[+-]?\d+(?:\.\d*)?"


class ResolveError(ValueError):
    pass


def parse_position(text: str) -> tuple[float, float] | None:
    """RA/Dec in degrees if ``text`` looks like coordinates, else None."""
    t = text.strip().replace(",", " ").replace("−", "-").replace("–", "-")
    # words people (and the challenge text) put around the numbers: "Right Ascension 08h55m10.831s, declination -7d14m42.53s"
    t = re.sub(r"(?i)\b(right\s+ascension|declination|ra|dec|j2000|icrs|and)\b\s*[:=]?", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    m = re.fullmatch(rf"({_NUM})\s+({_NUM})", t)
    if m:
        ra, dec = float(m.group(1)), float(m.group(2))
        if 0 <= ra <= 360 and -90 <= dec <= 90:
            return ra % 360.0, dec
        raise ResolveError("RA must be 0–360° and Dec −90…+90°.")
    if re.search(r"\d", t) and re.fullmatch(r"[\d\s:.+\-hmsd°'\"′″]+", t, flags=re.I):
        t2 = t.replace("°", "d").replace("′", "m").replace("″", "s").replace("'", "m").replace('"', "s")
        try:
            c = SkyCoord(t2, unit=(u.hourangle, u.deg), frame="icrs")
            return float(c.ra.deg), float(c.dec.deg)
        except Exception:  # noqa: BLE001
            return None
    return None


def _sesame(name: str) -> dict | None:
    last: Exception | None = None
    for base in SESAME:
        try:
            r = httpx.get(base + urllib.parse.quote(name), timeout=20, follow_redirects=True)
            r.raise_for_status()
            root = ET.fromstring(r.text.split("<!---")[0])
        except Exception as exc:  # noqa: BLE001
            last = exc
            continue
        for res in root.iter("Resolver"):
            ra, dec = res.findtext("jradeg"), res.findtext("jdedeg")
            if ra is None or dec is None:
                continue
            out = {
                "ra_j2000": float(ra),
                "dec_j2000": float(dec),
                "name": (res.findtext("oname") or name).replace("NAME ", "").strip(),
                "otype": (res.findtext("otype") or "").strip(),
                "resolver": (res.get("name") or "").split("=")[-1].split(",")[0].split("(")[0].strip(),
            }
            pm = res.find("pm")
            if pm is not None and pm.findtext("pmRA") and pm.findtext("pmDE"):
                out["pm_ra_mas_yr"] = float(pm.findtext("pmRA"))
                out["pm_dec_mas_yr"] = float(pm.findtext("pmDE"))
            return out
        return None  # the service answered: nothing by that name
    raise ResolveError(f"The name service (CDS Sesame) is not reachable right now ({type(last).__name__}).")


# Everyday names the name service does not know, starting with the objects the challenge text asks to test.
ALIASES = {
    "wise 0855": "WISE J085510.83-071442.5", "wise 0855-0714": "WISE J085510.83-071442.5", "wise0855": "WISE J085510.83-071442.5",
    "w0855": "WISE J085510.83-071442.5", "wise j0855-0714": "WISE J085510.83-071442.5", "wise 0855−0714": "WISE J085510.83-071442.5",
    "epsilon indi b": "eps Ind B", "eps indi b": "eps Ind B", "epsilon ind b": "eps Ind B", "epsilon indi ba": "eps Ind B", "epsilon indi bb": "eps Ind B",
    "epsilon indi": "eps Ind", "rw aurigae": "RW Aur", "r draconis": "R Dra", "barnards star": "Barnard's star", "barnard star": "Barnard's star",
    "luhman 16": "Luhman 16", "proxima": "Proxima Centauri",
}


def canonical_name(q: str) -> str:
    """The spelling to ask the name service for: straight apostrophes, and the aliases above."""
    q = re.sub(r"[’‘`´]", "'", q)
    key = q.lower().strip()
    return ALIASES.get(key) or ALIASES.get(key.replace("'", "")) or q


def resolve(query: str) -> dict:
    """Resolve coordinates or an object name. Raises ResolveError with a human message."""
    q = " ".join(query.split())
    if not q:
        raise ResolveError("Type an object name or coordinates.")
    pos = parse_position(q)
    if pos:
        return {"query": q, "kind": "coordinates", "name": None, "ra": round(pos[0], 6), "dec": round(pos[1], 6)}

    asked = canonical_name(q)
    ck = "resolve/" + asked.lower()
    hit = cache.get_json(ck, max_age=30 * 86400)
    if hit is None:
        hit = _sesame(asked) or {}
        if hit:  # "not found" is not remembered: the name service may simply have been down
            cache.put_json(ck, hit)
    if not hit:
        raise ResolveError(
            f"Couldn't find “{q}”. Try another spelling, or coordinates like “269.4486 +4.7680”. "
            "Planets, asteroids and comets move, so they have no fixed position — see the examples."
        )
    out = {"query": q, "kind": "name", **hit}
    ra, dec = hit["ra_j2000"], hit["dec_j2000"]
    if "pm_ra_mas_yr" in hit:
        dt = SURVEY_EPOCH - 2000.0
        dec2 = dec + hit["pm_dec_mas_yr"] * dt / 3.6e6
        ra2 = ra + hit["pm_ra_mas_yr"] * dt / 3.6e6 / max(math.cos(math.radians(dec)), 1e-6)
        shift = math.hypot(hit["pm_ra_mas_yr"], hit["pm_dec_mas_yr"]) * dt / 1000.0
        out["pm_total_arcsec_yr"] = round(math.hypot(hit["pm_ra_mas_yr"], hit["pm_dec_mas_yr"]) / 1000.0, 3)
        if shift > 1.0:  # more than an arcsecond since J2000: centre on where it is now
            ra, dec = ra2 % 360.0, dec2
            out["moved_arcsec_since_2000"] = round(shift, 1)
            out["epoch"] = SURVEY_EPOCH
    out["ra"], out["dec"] = round(ra, 6), round(dec, 6)
    return out
