"""SPHEREx data access for Blink X.

Everything here works on real archive data:

* ``search_exposures``  - IRSA SIA2 query: which Level-2 spectral images cover a position.
* ``read_exposure_meta`` - reads the FITS header of one image (dates, WCS, wavelength at the target).
* ``make_frame``         - reads only the pixel rows we need and resamples them onto a small
                           north-up grid centred on the target, so every epoch lines up.

Files are read with HTTP range requests from the public NASA/IRSA copy on AWS
(``s3://nasa-irsa-spherex``, listed in the SIA ``cloud_access`` column); the IRSA on-prem
URL is used as a fallback. Observation dates always come from the FITS header (DATE-OBS / DATE-AVG).
"""
from __future__ import annotations

import base64
import io
import json
import math
import re
import threading
import time
import warnings
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import httpx
import numpy as np
from astropy.io import fits
from astropy.io.votable import parse_single_table
from astropy.wcs import WCS, FITSFixedWarning

from . import cache

warnings.simplefilter("ignore", FITSFixedWarning)
warnings.filterwarnings("ignore", module="astropy.io.votable")

SIA_URL = "https://irsa.ipac.caltech.edu/SIA"
S3_BASE = "https://nasa-irsa-spherex.s3.amazonaws.com/"
IRSA_BASE = "https://irsa.ipac.caltech.edu/ibe/data/spherex/"
# Wide survey first (all-sky), then the deep fields near the ecliptic poles.
COLLECTIONS = ("spherex_dr1", "spherex_qr3", "spherex_dr1_deep", "spherex_qr3_deep")

BANDS = {
    1: {"name": "D1", "range_um": [0.75, 1.11], "label": "Band 1 · 0.75–1.11 µm"},
    2: {"name": "D2", "range_um": [1.10, 1.65], "label": "Band 2 · 1.10–1.65 µm"},
    3: {"name": "D3", "range_um": [1.63, 2.43], "label": "Band 3 · 1.63–2.43 µm"},
    4: {"name": "D4", "range_um": [2.40, 3.83], "label": "Band 4 · 2.40–3.83 µm"},
    5: {"name": "D5", "range_um": [3.81, 4.42], "label": "Band 5 · 3.81–4.42 µm"},
    6: {"name": "D6", "range_um": [4.41, 5.01], "label": "Band 6 · 4.41–5.01 µm"},
}

# FLAGS bit planes (names read from the MSKNnnnn cards of the FLAGS header).
FLAG_TRANSIENT = 1 << 0
FLAG_OVERFLOW = 1 << 1
FLAG_SUR_ERROR = 1 << 2
FLAG_NONFUNC = 1 << 6
FLAG_MISSING = 1 << 9
FLAG_HOT = 1 << 10
FLAG_COLD = 1 << 11
FLAG_SOURCE = 1 << 21
FLAG_BLOOM = 1 << 26
FLAG_SNOWBALL = 1 << 27
ALWAYS_BAD = FLAG_NONFUNC | FLAG_MISSING | FLAG_HOT | FLAG_COLD | FLAG_SNOWBALL

BLOCK = 2880
HEADER_GUESS = 14 * BLOCK  # primary (1 block) + IMAGE header (8 blocks) with room to spare

_client_lock = threading.Lock()
_client: httpx.Client | None = None


def client() -> httpx.Client:
    global _client
    with _client_lock:
        if _client is None:
            _client = httpx.Client(
                timeout=httpx.Timeout(40.0, connect=15.0),
                limits=httpx.Limits(max_connections=32, max_keepalive_connections=32),
                headers={"User-Agent": "BlinkX/1.0 (NASA Space Apps 2026 demo)"},
                follow_redirects=True,
            )
        return _client


class ArchiveError(RuntimeError):
    """The archive did not give us what we asked for."""


def _get(url: str, *, params=None, headers=None, tries: int = 4) -> httpx.Response:
    last: Exception | None = None
    for attempt in range(tries):
        try:
            r = client().get(url, params=params, headers=headers)
            # IRSA answers "Server busy, retry later." with a non-FITS body when overloaded.
            if r.status_code in (200, 206) and not r.content.startswith(b"Server busy"):
                return r
            last = ArchiveError(f"HTTP {r.status_code} from {url.split('?')[0]}: {r.text[:120]!r}")
            if r.status_code in (400, 403, 404, 416):
                break
        except httpx.HTTPError as exc:  # timeouts, resets
            last = ArchiveError(f"{type(exc).__name__} from {url.split('?')[0]}")
        time.sleep(0.6 * (attempt + 1))
    raise last or ArchiveError("request failed")


def _get_range(key: str, start: int, end: int) -> bytes:
    """Bytes [start, end) of an archive file; AWS first, IRSA on-prem as fallback."""
    hdr = {"Range": f"bytes={start}-{end - 1}"}
    try:
        return _get(S3_BASE + key, headers=hdr, tries=2).content
    except ArchiveError:
        return _get(IRSA_BASE + key, headers=hdr).content


# --------------------------------------------------------------------------- search


def _sia_one(collection: str, ra: float, dec: float) -> list[dict]:
    r = _get(
        SIA_URL,
        params={
            "COLLECTION": collection,
            "POS": f"circle {ra:.6f} {dec:.6f} 0.0003",
            "RESPONSEFORMAT": "votable",
        },
    )
    table = parse_single_table(io.BytesIO(r.content)).to_table(use_names_over_ids=True)
    out = []
    for row in table:
        url = str(row["access_url"])
        if "/ibe/data/spherex/" not in url:
            continue
        key = url.split("/ibe/data/spherex/", 1)[1]
        m = re.search(r"SPHEREx-D(\d)", str(row["energy_bandpassname"]))
        if not m:
            continue
        det = int(m.group(1))
        out.append(
            {
                "id": f"{row['obs_id']}D{det}",
                "obs_id": str(row["obs_id"]),
                "detector": det,
                "collection": collection,
                "key": key,
                "mjd": float(row["t_min"]),
                "exptime": float(row["t_exptime"]),
            }
        )
    return out


def search_exposures(ra: float, dec: float) -> list[dict]:
    """All SPHEREx Level-2 spectral images whose footprint contains (ra, dec), oldest first."""
    ck = f"sia/{ra:.5f}_{dec:.5f}"
    hit = cache.get_json(ck, max_age=6 * 3600)
    if hit is not None:
        return hit
    with ThreadPoolExecutor(len(COLLECTIONS)) as pool:
        parts = list(pool.map(lambda c: _safe_sia(c, ra, dec), COLLECTIONS))
    errors = [p for p in parts if isinstance(p, Exception)]
    if len(errors) == len(parts):
        raise ArchiveError(f"IRSA image search failed: {errors[0]}")
    seen, rows = set(), []
    for part in parts:
        if isinstance(part, Exception):
            continue
        for row in part:
            if row["id"] not in seen:
                seen.add(row["id"])
                rows.append(row)
    rows.sort(key=lambda r: r["mjd"])
    if not errors:
        cache.put_json(ck, rows)
    return rows


def _safe_sia(collection, ra, dec):
    try:
        return _sia_one(collection, ra, dec)
    except Exception as exc:  # noqa: BLE001 - one collection failing must not sink the search
        return exc


# --------------------------------------------------------------------------- headers


def _split_header(raw: bytes, offset: int) -> tuple[fits.Header, int]:
    """Parse the FITS header starting at ``offset``; returns (header, offset just past it)."""
    pos = offset
    while pos + BLOCK <= len(raw):
        block = raw[pos : pos + BLOCK]
        pos += BLOCK
        if any(block[i : i + 8] == b"END     " for i in range(0, BLOCK, 80)):
            return fits.Header.fromstring(raw[offset:pos].decode("ascii", "replace")), pos
    raise ArchiveError("FITS header longer than expected")


@dataclass
class ExposureHeader:
    key: str
    header: fits.Header
    data_offset: int  # byte offset of the IMAGE pixel array
    nx: int
    ny: int
    version: str = ""

    @property
    def flags_header_offset(self) -> int:
        nbytes = self.nx * self.ny * 4
        return self.data_offset + math.ceil(nbytes / BLOCK) * BLOCK


def read_header(key: str) -> ExposureHeader:
    ck = "hdr/" + key.rsplit("/", 1)[-1]
    raw = cache.get_bytes(ck)
    if raw is None:
        raw = _get_range(key, 0, HEADER_GUESS)
        cache.put_bytes(ck, raw)
    primary, pos = _split_header(raw, 0)
    hdr, data_offset = _split_header(raw, pos)
    if hdr.get("EXTNAME", "").strip() != "IMAGE" or hdr.get("BITPIX") != -32:
        raise ArchiveError(f"unexpected FITS layout in {key}")
    return ExposureHeader(
        key, hdr, data_offset, int(hdr["NAXIS1"]), int(hdr["NAXIS2"]), str(primary.get("VERSION", "")).strip()
    )


# --------------------------------------------------------------------------- wavelength

_wave_tables: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
_wave_lock = threading.Lock()


def _wave_table(eh: ExposureHeader):
    """The WCS-WAVE lookup table (last HDU of every image); one per detector + calibration."""
    calib = ""
    for line in eh.header.get("HISTORY", []):
        m = re.search(r"\[CALIB\] spectral_wcs (\S+)", str(line))
        if m:
            calib = m.group(1)
    tkey = f"D{eh.header['DETECTOR']}_{calib or eh.key.rsplit('/', 1)[-1]}"
    with _wave_lock:
        if tkey in _wave_tables:
            return _wave_tables[tkey]
    ck = f"wave/{tkey}"
    raw = cache.get_bytes(ck)
    if raw is None:
        # WCS-WAVE is tiny (one header block + one data block) and is the last HDU of the file.
        raw = _get_suffix(eh.key, 4 * BLOCK)
        cache.put_bytes(ck, raw)
    table = _parse_wave_table(raw)
    with _wave_lock:
        _wave_tables[tkey] = table
    return table


def _get_suffix(key: str, nbytes: int) -> bytes:
    hdr = {"Range": f"bytes=-{nbytes}"}
    try:
        return _get(S3_BASE + key, headers=hdr, tries=2).content
    except ArchiveError:
        return _get(IRSA_BASE + key, headers=hdr).content


def _parse_wave_table(raw: bytes):
    """Decode the WCS-WAVE binary table (columns X, Y, VALUES) from the tail of a file."""
    start = -1
    for off in range(len(raw) - BLOCK, -1, -BLOCK):
        if raw[off : off + 8] == b"XTENSION":
            start = off
            break
    if start < 0:
        raise ArchiveError("could not locate the WCS-WAVE table")
    th, data_off = _split_header(raw, start)
    if th.get("EXTNAME", "").strip() != "WCS-WAVE":
        raise ArchiveError("last HDU is not WCS-WAVE")
    cols = {th[f"TTYPE{i}"].strip(): (i, th[f"TFORM{i}"].strip()) for i in range(1, th["TFIELDS"] + 1)}
    nxv, nyv = int(cols["X"][1][:-1]), int(cols["Y"][1][:-1])
    if (cols["X"][0], cols["Y"][0], cols["VALUES"][0]) != (1, 2, 3):
        raise ArchiveError("unexpected WCS-WAVE column order")
    row = raw[data_off : data_off + th["NAXIS1"]]
    x = np.frombuffer(row, ">i4", nxv, 0).astype(float)
    y = np.frombuffer(row, ">i4", nyv, 4 * nxv).astype(float)
    # TDIM (2, nx, ny) in FITS order == numpy shape (ny, nx, 2): [..., 0] wavelength, [..., 1] bandwidth
    values = np.frombuffer(row, ">f4", 2 * nxv * nyv, 4 * (nxv + nyv)).astype(float).reshape(nyv, nxv, 2)
    return x, y, values


def _tab_index(vec: np.ndarray, psi: float) -> float:
    """FITS -TAB index lookup: fractional 0-based position of psi inside the index vector."""
    if psi <= vec[0]:
        return 0.0
    if psi >= vec[-1]:
        return float(len(vec) - 1)
    k = int(np.searchsorted(vec, psi) - 1)
    return k + (psi - vec[k]) / (vec[k + 1] - vec[k])


def wavelength_at(header: fits.Header, table, x0: float, y0: float) -> tuple[float, float]:
    """(central wavelength, bandwidth) in microns at 0-based pixel (x0, y0).

    Implements the 2-D ``WAVE-TAB`` alternate WCS ("W") by hand: bilinear interpolation of the
    9 x 14 control grid stored in the WCS-WAVE extension.
    """
    xv, yv, values = table
    psi1 = header.get("CRVAL1W", 1.0) + header.get("CDELT1W", 1.0) * ((x0 + 1.0) - header.get("CRPIX1W", 1.0))
    psi2 = header.get("CRVAL2W", 1.0) + header.get("CDELT2W", 1.0) * ((y0 + 1.0) - header.get("CRPIX2W", 1.0))
    fi, fj = _tab_index(xv, psi1), _tab_index(yv, psi2)
    i0, j0 = min(int(fi), len(xv) - 2), min(int(fj), len(yv) - 2)
    di, dj = fi - i0, fj - j0
    v = (
        values[j0, i0] * (1 - di) * (1 - dj)
        + values[j0, i0 + 1] * di * (1 - dj)
        + values[j0 + 1, i0] * (1 - di) * dj
        + values[j0 + 1, i0 + 1] * di * dj
    )
    return float(v[0]), float(v[1])


# --------------------------------------------------------------------------- per-exposure metadata


def read_exposure_meta(exp: dict, ra: float, dec: float) -> dict:
    """Header-derived facts about one exposure at the target position (no pixels downloaded)."""
    eh = read_header(exp["key"])
    h = eh.header
    wcs = WCS(h)
    x, y = (float(v) for v in wcs.all_world2pix([[ra, dec]], 0, quiet=True)[0])
    on_detector = -0.5 <= x <= eh.nx - 0.5 and -0.5 <= y <= eh.ny - 0.5
    wl = bw = None
    if on_detector:
        try:
            wl, bw = wavelength_at(h, _wave_table(eh), x, y)
        except Exception:  # noqa: BLE001 - wavelength is nice-to-have; never drop the frame for it
            wl = bw = None
    return {
        **{k: exp[k] for k in ("id", "obs_id", "detector", "collection")},
        "band": f"D{exp['detector']}",
        "date_obs": str(h.get("DATE-OBS", "")),  # start of exposure, UTC, from the FITS header
        "date_avg": str(h.get("DATE-AVG", "")),  # midpoint
        "mjd": float(h.get("MJD-AVG", exp["mjd"])),
        "exptime": float(h.get("XPOSURE", exp.get("exptime") or 0.0)),
        "wavelength_um": wl,
        "bandwidth_um": bw,
        "pixel": [round(x, 2), round(y, 2)],
        "on_detector": bool(on_detector),
        "psf_fwhm_arcsec": float(h["PSF_FWHM"]) if "PSF_FWHM" in h else None,
        "quality": str(h.get("L2DQAFLG", "")).strip(),
        "pipeline_version": eh.version,
        "file": exp["key"].rsplit("/", 1)[-1],
        "irsa_url": IRSA_BASE + exp["key"],
    }


def list_frames(ra: float, dec: float, detector: int, exposures: list[dict] | None = None) -> list[dict]:
    """Metadata for every exposure of one detector that really contains the target pixel."""
    ck = f"frames/{ra:.5f}_{dec:.5f}_D{detector}"
    hit = cache.get_json(ck, max_age=6 * 3600)
    if hit is not None:
        return hit
    exposures = exposures if exposures is not None else search_exposures(ra, dec)
    todo = [e for e in exposures if e["detector"] == detector]

    def one(exp):
        try:
            return read_exposure_meta(exp, ra, dec)
        except Exception as exc:  # noqa: BLE001
            return {"id": exp["id"], "error": str(exc)}

    with ThreadPoolExecutor(16) as pool:
        metas = list(pool.map(one, todo))
    failed = [m for m in metas if "error" in m]
    frames = [m for m in metas if "error" not in m and m["on_detector"]]
    frames.sort(key=lambda m: m["mjd"])
    if not failed:
        cache.put_json(ck, frames)
    return frames


# --------------------------------------------------------------------------- pixels


def grid_size(size_deg: float) -> int:
    """Output grid: at least ~SPHEREx native sampling (6.15"/px), 2x oversampled for small fields."""
    if size_deg <= 0.1:
        return 128
    if size_deg <= 0.2:
        return 192
    return 256


def _tangent_grid(ra0: float, dec0: float, size_deg: float, n: int):
    """RA/Dec of every pixel of a north-up, east-left gnomonic grid centred on (ra0, dec0)."""
    step = math.radians(size_deg / n)
    c = (n - 1) / 2.0
    jj, ii = np.mgrid[0:n, 0:n]
    xi = -(ii - c) * step  # east is to the left
    eta = (c - jj) * step  # north is up
    a0, d0 = math.radians(ra0), math.radians(dec0)
    den = math.cos(d0) - eta * math.sin(d0)
    ra = a0 + np.arctan2(xi, den)
    dec = np.arctan2((math.sin(d0) + eta * math.cos(d0)) * np.cos(ra - a0), den)
    return np.degrees(ra) % 360.0, np.degrees(dec)


def _read_rows(key: str, data_offset: int, nx: int, y0: int, y1: int, dtype: str) -> np.ndarray:
    raw = _get_range(key, data_offset + y0 * nx * 4, data_offset + y1 * nx * 4)
    return np.frombuffer(raw, dtype=dtype).reshape(y1 - y0, nx)


def _read_flag_rows(eh: ExposureHeader, y0: int, y1: int) -> np.ndarray:
    """Rows [y0, y1) of the FLAGS extension.

    In the archive files FLAGS is a tile-compressed image (RICE_1, one tile per image row), stored
    as a binary table of (length, heap offset) descriptors followed by the heap. We fetch the
    descriptors, then only the compressed bytes of the rows we need.
    """
    from astropy.io.fits.hdu.compressed._codecs import Rice1

    off = eh.flags_header_offset
    ck = "flaghdr/" + eh.key.rsplit("/", 1)[-1]
    raw = cache.get_bytes(ck)
    if raw is None:
        raw = _get_range(eh.key, off, off + 16 * BLOCK)  # header + the whole descriptor table
        cache.put_bytes(ck, raw)
    fh, rel = _split_header(raw, 0)
    ok = (
        fh.get("EXTNAME", "").strip() == "FLAGS"
        and fh.get("ZCMPTYPE", "").strip() == "RICE_1"
        and fh.get("ZBITPIX") == 32
        and fh.get("ZTILE1") == eh.nx
        and fh.get("ZTILE2") == 1
        and fh.get("NAXIS1") == 8
    )
    if not ok:
        raise ArchiveError("unexpected FLAGS layout")
    nrows = int(fh["NAXIS2"])
    if len(raw) < rel + nrows * 8:
        raw = raw + _get_range(eh.key, off + len(raw), off + rel + nrows * 8)
    desc = np.frombuffer(raw, ">i4", nrows * 2, rel).reshape(nrows, 2)[y0:y1]
    heap = off + rel + int(fh.get("THEAP", nrows * 8))
    lo = int(desc[:, 1].min())
    hi = int((desc[:, 1] + desc[:, 0]).max())
    blob = _get_range(eh.key, heap + lo, heap + hi)
    params = {fh[f"ZNAME{i}"].strip(): fh[f"ZVAL{i}"] for i in (1, 2) if f"ZNAME{i}" in fh}
    codec = Rice1(blocksize=int(params.get("BLOCKSIZE", 32)), bytepix=int(params.get("BYTEPIX", 4)), tilesize=eh.nx)
    out = np.empty((y1 - y0, eh.nx), dtype=np.int32)
    for i, (nbytes, start) in enumerate(desc):
        out[i] = codec.decode(np.frombuffer(blob, np.uint8, int(nbytes), int(start) - lo))
    return out


def _bilinear(src: np.ndarray, yy: np.ndarray, xx: np.ndarray) -> np.ndarray:
    """Sample ``src`` at fractional pixel positions (edges are clamped; callers mask the outside)."""
    h, w = src.shape
    x0 = np.floor(xx).astype(int)
    y0 = np.floor(yy).astype(int)
    fx = (xx - x0).astype(np.float32)
    fy = (yy - y0).astype(np.float32)
    xa, xb = np.clip(x0, 0, w - 1), np.clip(x0 + 1, 0, w - 1)
    ya, yb = np.clip(y0, 0, h - 1), np.clip(y0 + 1, 0, h - 1)
    top = src[ya, xa] * (1 - fx) + src[ya, xb] * fx
    bottom = src[yb, xa] * (1 - fx) + src[yb, xb] * fx
    return top * (1 - fy) + bottom * fy


def _inpaint(img: np.ndarray, bad: np.ndarray, bloom: np.ndarray) -> np.ndarray:
    """Replace pipeline-flagged pixels with their good neighbours (never with invented structure).

    Ordinary bad pixels take the median of the surrounding good pixels; holes inside a saturated
    star take the brightest neighbour so the star stays a star.
    """
    out = np.where(bad, np.nan, img).astype(np.float32)
    h, w = out.shape
    for _ in range(6):
        holes = np.isnan(out)
        if not holes.any():
            break
        pad = np.pad(out, 1, constant_values=np.nan)
        stack = np.stack([pad[1 + dy : 1 + dy + h, 1 + dx : 1 + dx + w] for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dy or dx])
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            med = np.nanmedian(stack, axis=0)
            mx = np.nanmax(stack, axis=0)
        fill = np.where(bloom, mx, med)
        ok = holes & np.isfinite(fill)
        out[ok] = fill[ok]
    rest = np.isnan(out)
    if rest.any():
        good = out[~rest]
        out[rest] = float(np.median(good)) if good.size else 0.0
    return out


def make_frame(exp: dict, ra: float, dec: float, size_deg: float, n: int | None = None) -> dict:
    """Resample one exposure onto the common north-up grid. Returns metadata + float image."""
    n = n or grid_size(size_deg)
    eh = read_header(exp["key"])
    h = eh.header
    wcs = WCS(h)
    gra, gdec = _tangent_grid(ra, dec, size_deg, n)
    px, py = wcs.all_world2pix(gra.ravel(), gdec.ravel(), 0, quiet=True)
    px, py = px.reshape(n, n), py.reshape(n, n)
    inside = (px >= -0.5) & (px <= eh.nx - 0.5) & (py >= -0.5) & (py <= eh.ny - 0.5)
    meta = read_exposure_meta(exp, ra, dec)
    meta.update({"n": n, "size_deg": size_deg, "pixscale_arcsec": round(size_deg * 3600 / n, 4)})
    if not inside.any():
        meta["coverage"] = 0.0
        return {"meta": meta, "image": np.full((n, n), np.nan, dtype=np.float32), "filled": np.zeros((n, n), bool)}

    y0 = max(0, int(math.floor(np.nanmin(py[inside]))) - 2)
    y1 = min(eh.ny, int(math.ceil(np.nanmax(py[inside]))) + 3)
    x0 = max(0, int(math.floor(np.nanmin(px[inside]))) - 2)
    x1 = min(eh.nx, int(math.ceil(np.nanmax(px[inside]))) + 3)

    with ThreadPoolExecutor(2) as pool:
        f_img = pool.submit(_read_rows, eh.key, eh.data_offset, eh.nx, y0, y1, ">f4")
        f_flags = pool.submit(_read_flag_rows, eh, y0, y1)
        img = f_img.result()[:, x0:x1].astype(np.float32)
        try:
            flags = f_flags.result()[:, x0:x1]
        except Exception:  # noqa: BLE001 - show the image even if the mask cannot be read
            flags = None
    bad = ~np.isfinite(img)
    bloom = np.zeros_like(bad)
    if flags is not None:
        bloom = (flags & FLAG_BLOOM) != 0  # saturated cores of bright stars: real, just unreliable
        bad |= (flags & ALWAYS_BAD) != 0
        # Cosmic-ray hits during the exposure. Saturated star cores trip the same flags, keep those.
        bad |= ((flags & (FLAG_TRANSIENT | FLAG_SUR_ERROR)) != 0) & ~bloom
    meta["flags_used"] = flags is not None
    meta["masked_fraction"] = round(float(bad.mean()), 4)

    src = _inpaint(img, bad, bloom)
    out = _bilinear(src, py - y0, px - x0)
    bh, bw = bad.shape
    filled = bad[np.clip(np.rint(py - y0).astype(int), 0, bh - 1), np.clip(np.rint(px - x0).astype(int), 0, bw - 1)]
    out[~inside] = np.nan
    filled = filled & inside

    meta["coverage"] = round(float(np.isfinite(out).mean()), 4)
    meta["unit"] = str(h.get("BUNIT", "MJy / sr"))
    return {"meta": meta, "image": out.astype(np.float32), "filled": filled}


# --------------------------------------------------------------------------- encoding for the browser


def robust_stats(img: np.ndarray) -> tuple[float, float]:
    """Sky level and noise of an image, ignoring stars (iterated median / MAD)."""
    v = img[np.isfinite(img)]
    if v.size < 16:
        return 0.0, 1.0
    med = float(np.median(v))
    sig = float(1.4826 * np.median(np.abs(v - med))) or 1e-6
    for _ in range(3):
        keep = v[np.abs(v - med) < 3 * sig]
        if keep.size < 16:
            break
        med = float(np.median(keep))
        sig = float(1.4826 * np.median(np.abs(keep - med))) or sig
    return med, max(sig, 1e-9)


def encode_frame(frame: dict) -> dict:
    """JSON-safe frame: sky-subtracted pixels packed as asinh-scaled uint16 (0 = no data)."""
    img = frame["image"]
    meta = dict(frame["meta"])
    bg, sigma = robust_stats(img)
    soft = 3.0 * sigma
    u = np.arcsinh((img - bg) / soft)
    finite = np.isfinite(u)
    umin = float(u[finite].min()) if finite.any() else 0.0
    umax = float(u[finite].max()) if finite.any() else 1.0
    span = (umax - umin) or 1.0
    q = np.zeros(img.shape, dtype="<u2")
    q[finite] = np.round((u[finite] - umin) / span * 65534.0).astype("<u2") + 1
    meta.update(
        {
            "sky": round(bg, 6),
            "sigma": float(f"{sigma:.6g}"),
            "enc": {"soft": float(f"{soft:.8g}"), "umin": umin, "umax": umax},
            "data": base64.b64encode(q.tobytes()).decode("ascii"),
            # 1 bit per pixel, row-major, MSB first: pixels the pipeline flagged and we filled in
            "filled": base64.b64encode(np.packbits(frame["filled"].astype(np.uint8)).tobytes()).decode("ascii"),
        }
    )
    return meta


def decode_frame(meta: dict) -> np.ndarray:
    """Inverse of ``encode_frame`` (sky-subtracted image, NaN where there is no data)."""
    n = meta["n"]
    q = np.frombuffer(base64.b64decode(meta["data"]), dtype="<u2").reshape(n, n).astype(np.float64)
    enc = meta["enc"]
    u = enc["umin"] + (q - 1) / 65534.0 * (enc["umax"] - enc["umin"])
    img = enc["soft"] * np.sinh(u)
    img[q == 0] = np.nan
    return img.astype(np.float32)


def get_frame(exp: dict, ra: float, dec: float, size_deg: float) -> dict:
    """Cached, browser-ready frame."""
    n = grid_size(size_deg)
    ck = f"frame/{exp['id']}_{ra:.5f}_{dec:.5f}_{size_deg:.4f}_{n}"
    hit = cache.get_json(ck)
    if hit is not None:
        return hit
    enc = encode_frame(make_frame(exp, ra, dec, size_deg, n))
    cache.put_json(ck, enc)
    return enc


def frame_to_png(meta: dict, lo: float = -2.0, hi: float = 60.0) -> bytes:
    """Greyscale PNG of a frame (asinh stretch between lo and hi sigma)."""
    from PIL import Image

    img = decode_frame(meta) / meta["sigma"]
    soft = 3.0
    t = (np.arcsinh((img - lo) / soft)) / math.asinh((hi - lo) / soft)
    t = np.clip(np.nan_to_num(t, nan=0.0), 0, 1)
    buf = io.BytesIO()
    Image.fromarray((t * 255).astype(np.uint8), "L").save(buf, "PNG", optimize=True)
    return buf.getvalue()


def json_dumps(obj) -> str:
    return json.dumps(obj, separators=(",", ":"), allow_nan=False)
