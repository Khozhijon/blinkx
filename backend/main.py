"""Blink X API: SPHEREx time-domain cutouts for the browser.

Run locally:  uvicorn backend.main:app --reload   (or ./run.sh)
"""
from __future__ import annotations

import os
import re
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

from astropy.time import Time
from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import resolver, skybot, spherex as sx

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
MAX_SIZE_DEG = 0.4
VISIT_GAP_DAYS = 20.0

@asynccontextmanager
async def lifespan(_app: FastAPI):
    threading.Thread(target=sx.warm_up, daemon=True).start()  # do not block start-up or the health check
    yield


app = FastAPI(title="Blink X", description="How the SPHEREx sky changes over time", version="1.0", lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("BLINKX_CORS", "*").split(","),
    allow_methods=["GET"],
    allow_headers=["*"],
)

RA = Query(..., ge=0, le=360, description="Right ascension, degrees (ICRS)")
DEC = Query(..., ge=-90, le=90, description="Declination, degrees (ICRS)")


def _archive(fn, *args):
    try:
        return fn(*args)
    except sx.ArchiveError as exc:
        raise HTTPException(
            502,
            "NASA's SPHEREx archive (IRSA) is not answering right now. Please try again in a minute — "
            f"the saved examples still work. (Detail: {str(exc)[:160]})",
        ) from exc


def _iso(mjd: float) -> str:
    return Time(mjd, format="mjd").isot[:19]


def _visits(exposures: list[dict]) -> list[dict]:
    """Group exposures into visits: SPHEREx returns to a patch of sky roughly every six months."""
    visits: list[dict] = []
    for e in exposures:
        if not visits or e["mjd"] - visits[-1]["_last"] > VISIT_GAP_DAYS:
            visits.append({"start": _iso(e["mjd"]), "count": 0, "bands": set(), "_last": e["mjd"]})
        v = visits[-1]
        v["count"] += 1
        v["bands"].add(e["detector"])
        v["end"] = _iso(e["mjd"])
        v["_last"] = e["mjd"]
    return [{"start": v["start"], "end": v["end"], "count": v["count"], "bands": sorted(v["bands"])} for v in visits]


@app.get("/api/health")
def health():
    return {"ok": True, "warm": sx.WARM, "time": time.time()}


@app.get("/api/resolve")
def api_resolve(q: str = Query(..., min_length=1, max_length=120)):
    try:
        return resolver.resolve(q)
    except resolver.ResolveError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.get("/api/search")
def api_search(ra: float = RA, dec: float = DEC):
    """Which SPHEREx images cover this position, per band and per visit (dates from archive metadata)."""
    ra, dec = round(ra, 5), round(dec, 5)
    res = _archive(sx.search, ra, dec)
    exposures, deep = res["exposures"], res["truncated"]
    bands = []
    for det, info in sx.BANDS.items():
        mine = [e for e in exposures if e["detector"] == det]
        # In a deep field the overview is only a sample, so per-band numbers are not known here.
        bands.append({"detector": det, **info, "count": None if deep else len(mine), "visits": None if deep else len(_visits(mine))})
    return {
        "ra": ra,
        "dec": dec,
        "total": len(exposures),
        "deep": deep,
        "bands": bands,
        "visits": [] if deep else _visits(exposures),
        "collections": list(sx.COLLECTIONS),
        "stale": bool(res.get("stale")),
    }


@app.get("/api/frames")
def api_frames(ra: float = RA, dec: float = DEC, band: int = Query(2, ge=1, le=6)):
    """Exposures of one band that contain the position: FITS-header date and wavelength there."""
    ra, dec = round(ra, 5), round(dec, 5)
    res = _archive(sx.band_exposures, ra, dec, band)
    frames = _archive(sx.list_frames, ra, dec, band, res["exposures"])
    return {
        "ra": ra,
        "dec": dec,
        "band": band,
        "total_in_band": len(res["exposures"]),
        "deep": res["deep"],
        "stale": bool(res.get("stale")),
        "frames": frames,
    }


def _find_exposure(ra: float, dec: float, frame_id: str) -> dict:
    m = re.fullmatch(r"[A-Za-z0-9_]{6,36}D([1-6])", frame_id)
    if m:
        for e in _archive(sx.band_exposures, ra, dec, int(m.group(1)))["exposures"]:
            if e["id"] == frame_id:
                return e
    raise HTTPException(404, "That exposure does not cover this position.")


def _size(size: float) -> float:
    return round(min(max(size, 0.02), MAX_SIZE_DEG), 4)


@app.get("/api/frame")
def api_frame(ra: float = RA, dec: float = DEC, id: str = Query(..., max_length=40), size: float = 0.1):
    """One exposure resampled onto the north-up grid, pixels packed for the browser."""
    ra, dec = round(ra, 5), round(dec, 5)
    exp = _find_exposure(ra, dec, id)
    frame = _archive(sx.get_frame, exp, ra, dec, _size(size))
    return JSONResponse(frame, headers={"Cache-Control": "public, max-age=86400"})


@app.get("/api/frame.png")
def api_frame_png(
    ra: float = RA, dec: float = DEC, id: str = Query(..., max_length=40), size: float = 0.1, lo: float = -2.0, hi: float = 60.0
):
    """The same frame as a greyscale PNG (handy for sharing or embedding)."""
    ra, dec = round(ra, 5), round(dec, 5)
    exp = _find_exposure(ra, dec, id)
    frame = _archive(sx.get_frame, exp, ra, dec, _size(size))
    return Response(sx.frame_to_png(frame, lo, hi), media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})


@app.get("/api/known-objects")
def api_known_objects(ra: float = RA, dec: float = DEC, mjd: float = Query(..., ge=60000, le=70000), size: float = 0.1):
    """Known asteroids and comets inside the field at that moment (IMCCE SkyBoT)."""
    try:
        return {"objects": skybot.cone(round(ra, 5), round(dec, 5), _size(size), mjd)}
    except skybot.SkybotError as exc:
        raise HTTPException(502, str(exc)) from exc


if FRONTEND.is_dir():

    @app.get("/")
    def index():
        return FileResponse(FRONTEND / "index.html")

    app.mount("/", StaticFiles(directory=FRONTEND), name="frontend")
