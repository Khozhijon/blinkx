"""Build seed/pointings.npz: where every SPHEREx pointing looked, read from NASA's open AWS bucket.

Why this exists. IRSA's image search (SIA) is the only service that says which exposures cover a
sky position, and it is sometimes down for hours. The image files themselves sit in an open AWS
bucket (s3://nasa-irsa-spherex) that is not. SPHEREx observes in "pointings": the telescope slews
to a field and takes up to four exposures, stepping 115 detector pixels between them. One header
per pointing (detector 2, the middle of the focal plane) therefore gives the direction and roll of
every exposure in it. With this index the backend can work out, without IRSA, which exposures
cover a position, and then confirm each one from its own header (backend/pointings.py).

Run:  python scripts/build_pointing_index.py            (resumes where it stopped)
      python scripts/build_pointing_index.py --check    (measure the focal-plane layout again)
Run it again after a new SPHEREx data release.
"""
from __future__ import annotations

import json
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

S3 = "https://nasa-irsa-spherex.s3.amazonaws.com/"
RELEASES = (("dr1", "spherex_dr1"), ("qr3", "spherex_qr3"))
OUT = ROOT / "seed" / "pointings.npz"
WORK = ROOT / "cache" / "pointing_index"  # scratch, git-ignored; lets the run resume
NAME = re.compile(r"level2_(\d{4}W\d{2}_\w+?)_(\d{4})_(\d)D2_spx_(.+)\.fits$")
CARDS = ("PC1_1", "PC1_2", "PC2_1", "PC2_2", "CRVAL1", "CRVAL2", "MJD-OBS")

_client = httpx.Client(timeout=40.0, limits=httpx.Limits(max_connections=80, max_keepalive_connections=80))


def get(params=None, key: str = "", headers=None, tries: int = 6) -> httpx.Response | None:
    """GET from the bucket; None for "no such file"."""
    for attempt in range(tries):
        try:
            r = _client.get(S3 + key, params=params, headers=headers)
            if r.status_code in (200, 206):
                return r
            if r.status_code in (403, 404, 416):
                return None
        except httpx.HTTPError:
            pass
        time.sleep(0.5 * (attempt + 1))
    raise RuntimeError(f"bucket did not answer for {key or params}")


def ls(prefix: str, folders: bool) -> list[str]:
    out, token = [], None
    while True:
        params = {"list-type": "2", "max-keys": "1000", "prefix": prefix}
        if folders:
            params["delimiter"] = "/"
        if token:
            params["continuation-token"] = token
        text = get(params).text
        out += re.findall(r"<CommonPrefixes><Prefix>([^<]+)</Prefix>" if folders else r"<Key>([^<]+)</Key>", text)
        m = re.search(r"<NextContinuationToken>([^<]+)</NextContinuationToken>", text)
        if not m:
            return out
        token = m.group(1)


def version_date(v: str) -> tuple[int, int]:
    m = re.search(r"(\d{4})-(\d{3})$", v)
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


def listing() -> dict:
    """{release: {week_plan: {pointing: {exposure: version}}}} for detector 2, the newest version of each."""
    path = WORK / "listing.json"
    if path.is_file():
        return json.loads(path.read_text())
    todo = []
    for rel, _ in RELEASES:
        for week in ls(f"{rel}/level2/", True):
            todo.append((rel, week))
    print(f"{len(todo)} week folders", flush=True)

    def one(item):
        rel, week = item
        keys = []
        for ver in ls(week, True):
            keys += ls(ver + "2/", False)
        return rel, keys

    tree: dict = {rel: {} for rel, _ in RELEASES}
    done = 0
    with ThreadPoolExecutor(12) as pool:
        for rel, keys in pool.map(one, todo):
            for key in keys:
                m = NAME.search(key)
                if not m:
                    continue
                wk, pt, k, ver = m.groups()
                slot = tree[rel].setdefault(wk, {}).setdefault(pt, {})
                if k not in slot or version_date(ver) > version_date(slot[k]):
                    slot[k] = ver
            done += 1
            if done % 20 == 0:
                print(f"  listed {done}/{len(todo)} folders", flush=True)
    WORK.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(tree, separators=(",", ":")))
    return tree


def key_for(rel: str, wk: str, pt: str, k: str | int, det: int, ver: str) -> str:
    return f"{rel}/level2/{wk}/{ver}/{det}/level2_{wk}_{pt}_{k}D{det}_spx_{ver}.fits"


def parse_cards(raw: bytes) -> dict | None:
    out = {}
    for card in CARDS:
        m = re.search(card.encode() + rb"\s*=\s*([-+0-9.eE]+)", raw)
        if not m:
            return None
        out[card] = float(m.group(1))
    return out


def pointing_header(key: str) -> dict | None:
    """The WCS and time cards of one exposure: a 6 kB slice where they normally sit, else the whole header."""
    r = get(key=key, headers={"Range": "bytes=14300-20479"})
    if r is None:
        return None
    cards = parse_cards(r.content)
    if cards is None:
        r = get(key=key, headers={"Range": "bytes=0-43199"})
        cards = parse_cards(r.content) if r is not None else None
    return cards


def crawl(tree: dict) -> dict:
    rows_path = WORK / "rows.jsonl"
    rows: dict[str, dict] = {}
    if rows_path.is_file():
        for line in rows_path.read_text().splitlines():
            try:
                row = json.loads(line)
                rows[row["p"]] = row
            except Exception:  # noqa: BLE001 - a torn last line after an interrupted run
                pass
    todo = [(rel, wk, pt, exps) for rel, weeks in tree.items() for wk, pts in weeks.items() for pt, exps in pts.items() if f"{rel}/{wk}/{pt}" not in rows]
    total = len(todo) + len(rows)
    print(f"{total} pointings, {len(rows)} already read, {len(todo)} to go", flush=True)
    lock = threading.Lock()
    t0 = time.time()
    fh = rows_path.open("a")

    def one(item):
        rel, wk, pt, exps = item
        row = {"p": f"{rel}/{wk}/{pt}"}
        for k in sorted(exps):  # the first exposure that can be read anchors the pointing
            try:
                cards = pointing_header(key_for(rel, wk, pt, k, 2, exps[k]))
            except RuntimeError:
                return None  # leave it for the next run
            if cards:
                row.update(k0=int(k), c=[cards[c] for c in CARDS])
                break
        with lock:
            rows[row["p"]] = row
            fh.write(json.dumps(row, separators=(",", ":")) + "\n")
            n = len(rows)
            if n % 2000 == 0:
                fh.flush()
                rate = (n - (total - len(todo))) / max(1e-6, time.time() - t0)
                print(f"  {n}/{total} pointings  {rate:.0f}/s  about {max(0, total - n) / max(rate, 1e-6) / 60:.1f} min left", flush=True)
        return row

    with ThreadPoolExecutor(48) as pool:
        list(pool.map(one, todo))
    fh.close()
    return rows


def save(tree: dict, rows: dict) -> None:
    weeks = sorted({(rel, wk) for rel, w in tree.items() for wk in w})
    week_id = {w: i for i, w in enumerate(weeks)}
    versions = sorted({v for w in tree.values() for pts in w.values() for exps in pts.values() for v in exps.values()})
    ver_id = {v: i for i, v in enumerate(versions)}
    cols: dict[str, list] = {k: [] for k in ("week", "pt", "k0", "mjd", "ra", "dec", "pc", "ver")}
    skipped = 0
    for rel, w in tree.items():
        for wk, pts in w.items():
            for pt, exps in pts.items():
                row = rows.get(f"{rel}/{wk}/{pt}")
                if not row or "c" not in row:
                    skipped += 1
                    continue
                c = row["c"]
                cols["week"].append(week_id[(rel, wk)])
                cols["pt"].append(int(pt))
                cols["k0"].append(row["k0"])
                cols["mjd"].append(c[6])
                cols["ra"].append(c[4])
                cols["dec"].append(c[5])
                cols["pc"].append(c[:4])
                cols["ver"].append([ver_id[exps[str(k)]] if str(k) in exps else -1 for k in (1, 2, 3, 4)])
    order = np.argsort(np.array(cols["mjd"]))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        OUT,
        week=np.array(cols["week"], np.uint16)[order], pt=np.array(cols["pt"], np.uint16)[order], k0=np.array(cols["k0"], np.uint8)[order],
        mjd=np.array(cols["mjd"], np.float64)[order], ra=np.array(cols["ra"], np.float64)[order], dec=np.array(cols["dec"], np.float64)[order],
        pc=np.array(cols["pc"], np.float64)[order], ver=np.array(cols["ver"], np.int16)[order],
        weeks=np.array([f"{rel}/{wk}" for rel, wk in weeks]), versions=np.array(versions), built=np.array(int(time.time())),
    )
    n = len(order)
    exposures = int((np.array(cols["ver"]) >= 0).sum())
    print(f"saved {OUT.relative_to(ROOT)}: {n} pointings, {exposures} exposures per detector, {skipped} unreadable, {OUT.stat().st_size / 1e6:.1f} MB", flush=True)


def check_layout(tree: dict, samples: int = 24) -> None:
    """Measure where the six detectors sit, and how far the telescope steps between exposures."""
    rng = np.random.default_rng(3)
    cands = [(rel, wk, pt, exps) for rel, w in tree.items() for wk, pts in w.items() for pt, exps in pts.items() if len(exps) == 4]
    picks = [cands[i] for i in rng.choice(len(cands), size=min(samples, len(cands)), replace=False)]

    def to_pix(ref, ra, dec):
        a0, d0, a, d = map(np.radians, (ref["CRVAL1"], ref["CRVAL2"], ra, dec))
        cosc = np.sin(d) * np.sin(d0) + np.cos(d) * np.cos(d0) * np.cos(a - a0)
        xi = np.degrees(np.cos(d) * np.sin(a - a0) / cosc)
        eta = np.degrees((np.sin(d) * np.cos(d0) - np.cos(d) * np.sin(d0) * np.cos(a - a0)) / cosc)
        pc = np.array([[ref["PC1_1"], ref["PC1_2"]], [ref["PC2_1"], ref["PC2_2"]]])
        return np.linalg.solve(pc, np.array([xi, eta]))

    offs: dict[int, list] = {d: [] for d in range(1, 7)}
    steps, dts = [], []
    for rel, wk, pt, exps in picks:
        ref = pointing_header(key_for(rel, wk, pt, 1, 2, exps["1"]))
        if not ref:
            continue
        for d in range(1, 7):
            h = pointing_header(key_for(rel, wk, pt, 1, d, exps["1"]))
            if h:
                offs[d].append(to_pix(ref, h["CRVAL1"], h["CRVAL2"]))
        for k in (2, 3, 4):
            h = pointing_header(key_for(rel, wk, pt, k, 2, exps[str(k)]))
            if h:
                steps.append(to_pix(ref, h["CRVAL1"], h["CRVAL2"]) / (k - 1))
                dts.append((h["MJD-OBS"] - ref["MJD-OBS"]) * 86400 / (k - 1))
    for d in range(1, 7):
        a = np.array(offs[d])
        print(f"D{d}: centre at ({a[:, 0].mean():8.1f}, {a[:, 1].mean():7.1f}) px in detector-2 pixels, scatter ({a[:, 0].std():.1f}, {a[:, 1].std():.1f}), n={len(a)}")
    s = np.array(steps)
    print(f"step per exposure: ({s[:, 0].mean():.1f}, {s[:, 1].mean():.1f}) px, scatter ({s[:, 0].std():.1f}, {s[:, 1].std():.1f}), every {np.mean(dts):.1f} s (scatter {np.std(dts):.1f}), n={len(s)}")


def main() -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    tree = listing()
    n_pt = sum(len(p) for w in tree.values() for p in w.values())
    n_exp = sum(len(e) for w in tree.values() for p in w.values() for e in p.values())
    print(f"bucket lists {n_pt} pointings and {n_exp} detector-2 exposures in {sum(len(w) for w in tree.values())} week folders", flush=True)
    if "--check" in sys.argv:
        check_layout(tree)
        return
    rows = crawl(tree)
    save(tree, rows)
    print("POINTING_INDEX_DONE", flush=True)


if __name__ == "__main__":
    main()
