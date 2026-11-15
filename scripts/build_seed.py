"""Save IRSA search results for well-known targets into seed/ (committed with the code).

Live search needs IRSA's query service to say which exposures cover a position; the pixels then
come from AWS. When IRSA is not answering, the backend falls back to these saved lists, so popular
targets keep working. Run again any time to refresh:  python scripts/build_seed.py [--refresh]
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend import cache, resolver, spherex as sx  # noqa: E402

TARGETS = [
    "Barnard's star", "Proxima Centauri", "Wolf 359", "Kapteyn's star", "Teegarden's star", "61 Cyg", "Luhman 16",
    "TRAPPIST-1", "Sirius", "Vega", "Betelgeuse", "Polaris", "Altair", "Arcturus",
    "M31", "M33", "M51", "M81", "M82", "M87", "M101", "M104", "NGC 253", "Centaurus A",
    "M1", "M42", "M45", "M57", "M27", "M8", "M16", "M17", "Eta Carinae", "Horsehead Nebula", "Sgr A*",
    "Omega Centauri", "M13", "47 Tuc",
]


def main() -> None:
    names = [a for a in sys.argv[1:] if not a.startswith("--")] or TARGETS
    ok = 0
    for name in names:
        try:
            pos = resolver.resolve(name)
            ra, dec = round(pos["ra"], 5), round(pos["dec"], 5)
            if "--refresh" not in sys.argv and cache._path(f"sia3/{ra:.5f}_{dec:.5f}", "json", cache.SEED_DIR).is_file():
                ok += 1
                print(f"{name:20s} already seeded", flush=True)
                continue
            res = None
            for attempt in range(6):  # IRSA can be flaky; be patient here, nobody is waiting
                try:
                    res = sx._sia_all(ra, dec)
                    break
                except sx.ArchiveError:
                    time.sleep(5 + 5 * attempt)
            if res is None:
                print(f"{name:20s} IRSA did not answer, skipped")
                continue
            if res["truncated"]:
                print(f"{name:20s} deep field, not seeded")
                continue
            cache.put_seed(f"sia3/{ra:.5f}_{dec:.5f}", res)
            cache.put_json(f"sia3/{ra:.5f}_{dec:.5f}", res)
            ok += 1
            print(f"{name:20s} RA {ra:9.5f} Dec {dec:+9.5f}  {len(res['exposures']):4d} exposures", flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"{name:20s} failed: {exc}")
    print(f"seeded {ok} of {len(names)} targets into {cache.SEED_DIR}")


if __name__ == "__main__":
    main()
