"""Gaia DR3 stars in a field, for the catalogue overlay.

Gaia is the European Space Agency's star-mapping mission. Its third data release gives the position
(at epoch 2016.0), proper motion, parallax and G magnitude of nearly two billion stars. The table is
read from the VizieR catalogue service (CDS, Strasbourg; the CfA mirror is tried first because it has
been the more dependable one), catalogue I/355/gaiadr3.
"""
from __future__ import annotations

import httpx

from . import cache

MIRRORS = (
    "https://vizier.cfa.harvard.edu/viz-bin/asu-tsv",
    "https://vizier.cds.unistra.fr/viz-bin/asu-tsv",
    "https://vizier.nao.ac.jp/viz-bin/asu-tsv",
)
EPOCH = 2016.0
EPOCH_MJD = 57388.0
MAX_GMAG = 19.0
LIMIT = 300


class GaiaError(RuntimeError):
    pass


def _num(text: str) -> float | None:
    text = text.strip()
    try:
        return float(text) if text else None
    except ValueError:
        return None


def parse_tsv(body: str) -> list[dict]:
    """Rows of a VizieR tab-separated answer: Source, RA_ICRS, DE_ICRS, Gmag, pmRA, pmDE, Plx."""
    rows, cols = [], None
    for line in body.splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        cells = line.split("\t")
        if cols is None:
            cols = [c.strip() for c in cells]
            continue
        if set(line.strip()) <= set("-\t ") or len(cells) < len(cols) or cells[cols.index("RA_ICRS")].strip() in ("deg", ""):
            continue  # the units line and the dashes line
        rec = dict(zip(cols, cells))
        ra, dec, g = _num(rec.get("RA_ICRS", "")), _num(rec.get("DE_ICRS", "")), _num(rec.get("Gmag", ""))
        if ra is None or dec is None:
            continue
        rows.append({"id": rec.get("Source", "").strip(), "ra": ra, "dec": dec, "g": g,
                     "pmra": _num(rec.get("pmRA", "")), "pmdec": _num(rec.get("pmDE", "")), "plx": _num(rec.get("Plx", ""))})
    return rows


def cone(ra: float, dec: float, size_deg: float) -> list[dict]:
    """The brightest Gaia DR3 stars inside the field (a circle that covers the square), brightest first.

    Positions are for epoch 2016.0; ``pmra``/``pmdec`` are in milliarcseconds per year (pmra already
    includes cos(dec)), ``plx`` in milliarcseconds. Any of the three can be None."""
    ck = f"gaia1/{ra:.4f}_{dec:.4f}_{size_deg:.3f}"
    hit = cache.get_json(ck, max_age=30 * 86400)
    if hit is not None:
        return hit
    params = {
        "-source": "I/355/gaiadr3", "-c": f"{ra:.6f} {dec:+.6f}", "-c.rs": f"{size_deg * 0.75 * 3600:.1f}",
        "-out": "Source,RA_ICRS,DE_ICRS,Gmag,pmRA,pmDE,Plx", "-out.max": str(LIMIT), "-sort": "Gmag", "Gmag": f"<{MAX_GMAG}",
    }
    last: Exception | None = None
    for url in MIRRORS:
        try:
            r = httpx.get(url, params=params, timeout=25, follow_redirects=True)
            if r.status_code != 200 or "RA_ICRS" not in r.text:
                last = GaiaError(f"HTTP {r.status_code} from {url}")
                continue
            rows = parse_tsv(r.text)
            cache.put_json(ck, rows)
            return rows
        except httpx.HTTPError as exc:
            last = GaiaError(f"{type(exc).__name__} from {url}")
    raise GaiaError(str(last or "no catalogue mirror answered"))
