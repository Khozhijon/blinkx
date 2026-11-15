"""Known solar-system objects in a field at a given moment, from IMCCE's SkyBoT service.

Lets people tell a catalogued asteroid from something nobody has named yet.
Positions are geocentric (IAU code 500); SPHEREx flies in low Earth orbit, so for main-belt
asteroids the difference is a few arcseconds at most (less than one SPHEREx pixel).
"""
from __future__ import annotations

import httpx

from . import cache

URL = "https://ssp.imcce.fr/webservices/skybot/api/conesearch.php"


class SkybotError(RuntimeError):
    pass


def _sexa(text: str, hours: bool) -> float:
    parts = text.replace(":", " ").split()
    sign = -1.0 if parts[0].startswith("-") else 1.0
    a, b, c = (abs(float(p)) for p in (parts + ["0", "0"])[:3])
    val = a + b / 60.0 + c / 3600.0
    return val * 15.0 if hours else sign * val


def cone(ra: float, dec: float, size_deg: float, mjd: float) -> list[dict]:
    ck = f"skybot/{ra:.4f}_{dec:.4f}_{size_deg:.3f}_{mjd:.4f}"
    hit = cache.get_json(ck, max_age=30 * 86400)
    if hit is not None:
        return hit
    params = {
        "-ep": f"{mjd + 2400000.5:.6f}",
        "-ra": f"{ra:.6f}",
        "-dec": f"{dec:.6f}",
        "-rd": f"{size_deg * 0.75:.5f}",  # circle that covers the corners of the square field
        "-mime": "json",
        "-output": "object",
        "-loc": "500",
        "-filter": "120",
        "-objFilter": "111",
        "-from": "BlinkX",
    }
    try:
        r = httpx.get(URL, params=params, timeout=40, follow_redirects=True)
        r.raise_for_status()
        # SkyBoT answers "204 No Content" when no known object is in the field.
        rows = [] if r.status_code == 204 or not r.content.strip() else r.json()
    except Exception as exc:  # noqa: BLE001
        raise SkybotError(f"SkyBoT (IMCCE) did not answer: {type(exc).__name__}") from exc
    out = []
    if isinstance(rows, list):
        for row in rows:
            try:
                out.append(
                    {
                        "name": str(row.get("Name", "")).strip(),
                        "number": row.get("Num") or None,
                        "class": str(row.get("Class", "")).strip(),
                        "vmag": row.get("VMag (mag)"),
                        "ra": round(_sexa(row["RA (hms)"], True), 6),
                        "dec": round(_sexa(row["DEC (dms)"], False), 6),
                        "err_arcsec": row.get("Err (arcsec)"),
                    }
                )
            except (KeyError, ValueError, IndexError):
                continue
    out.sort(key=lambda o: (o["vmag"] is None, o["vmag"] or 99))
    cache.put_json(ck, out)
    return out
