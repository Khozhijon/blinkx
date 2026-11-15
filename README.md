# Blink X

**Watch the sky change in NASA's SPHEREx images.**
A public web tool for the NASA Space Apps Challenge 2026 — *Planet X and SPHEREx* — by team **KhoFra**.

**Created by Khozhiakbar Khakimov Furkatzhonovich and Francia Constanza Coyotl Cortes** (Team KhoFra, Boston).

Type a star or galaxy name (or RA/Dec), and Blink X finds every SPHEREx exposure of that spot,
lines them up, and lets you **blink** between dates, put them **side by side**, **subtract** one
from the other, or play them as a **time-lapse**. Things that moved — asteroids, comets, nearby
stars — pop out. It is the 1930 blink comparator that found Pluto, pointed at a 2025–26 all-sky
infrared survey, in a browser, on a phone.

- **Live demo:** <https://khozhijon.github.io/blinkx/> (the saved examples open instantly; live search
  of the whole archive runs on a small free server, <https://blinkx-khofra.onrender.com>, that needs about
  a minute to wake up when nobody has used it for a while)
- **Data:** real SPHEREx Level-2 spectral images from NASA/IPAC IRSA. Every date shown is the
  `DATE-OBS` keyword of the FITS file it came from. The one made-up demo field is labelled
  SIMULATED on screen.

## Tested on the challenge's five objects

The challenge asks every team to test its tool on five objects. Each is a one-click target on the
page (saved real pictures, so it opens at once) and can also be typed the way the challenge writes
it: `Barnard's Star`, `Epsilon Indi B`, `WISE 0855`, `RW Aurigae`, `R Draconis`, or
`Right Ascension 08h55m10.831s, declination -7d14m42.53s`. This is what Blink X finds by itself:

| Object | What the automatic search reports | Measured here | Catalogue |
|---|---|---|---|
| Barnard's Star | Arrow, sliding north; named from SIMBAD | 10.0 ± 1.2″ a year | 10.39″ a year |
| Epsilon Indi B | Arrow, sliding south-east; named from SIMBAD | 4.6 ± 0.4″ a year | 4.68″ a year |
| WISE 0855−0714 | Arrow found only after each visit's exposures are added together (it is too faint to follow in single exposures); named from SIMBAD | 8.2 ± 0.6″ a year; 0.24 mJy at 3.9 µm rising to 0.53 mJy at 4.3 µm | 8.15″ a year; about 0.45 mJy at 4.6 µm (WISE) |
| RW Aurigae | Pulse: brighter at every visit; named from SIMBAD as a young variable star | +59% from Sep 2025 to Sep 2026 at 0.75–1.1 µm | T Tauri variable |
| R Draconis | No doodle | changes of 10–20% between visits, on a star that overloads the detector | Mira variable, 245-day period |

Two honest notes. WISE 0855 is 7 light-years away, so its seasonal wobble (parallax, 0.45″) is
part of any measurement made over a single year: the same search in the 4.4–5.0 µm band, where the
visits are less evenly filled, gives 9.4 ± 0.9″ a year. The Object Card says so. And R Draconis is so bright that
SPHEREx's detector overloads on it: Blink X measures it against the stars around it, finds a change
too small to trust, and draws nothing rather than guess. Typing the challenge's printed coordinates
for WISE 0855 gives its 2010 position; the brown dwarf has since moved 2 arcminutes west, and the
deep search still finds it there in the 3.8–4.4 µm band.

![Barnard's Star, 13 months apart, and the difference image](spike/out/spike_barnard.png)

## What it does

| | |
|---|---|
| Search | Object name (CDS Sesame: SIMBAD → NED → VizieR, plus everyday names such as `WISE 0855` or `Epsilon Indi B`) or coordinates in degrees or sexagesimal, with or without the words "Right Ascension" and "declination". Coordinates also work in the URL (`?ra=…&dec=…`). Nearby stars are shifted from their year-2000 catalogue position to where they are now, using their catalogued proper motion. |
| Epochs | All Level-2 spectral images covering the position (IRSA SIA2, collections `spherex_dr1`, `spherex_qr3` and the two `_deep` ones), grouped into visits. SPHEREx returns to most of the sky about every six months. |
| Cutouts | 3′, 6′, 12′ or 24′ fields, resampled onto one north-up grid so every date lines up pixel for pixel. |
| Compare | Blink (A ↔ B) with a speed slider, swipe, side by side with a linked cursor, difference (B − A: magenta = new or brighter, green = gone or dimmer), time-lapse with a slider. |
| Colour band | Any of SPHEREx's six detector bands (0.75–5.0 µm). The exact wavelength of each exposure *at your position* is shown, because SPHEREx's filters vary across the detector. |
| Display | Brightness, black level, three colour maps, optional brightness matching between dates, smooth or raw pixels. |
| Add exposures together | "Exposures": one at a time, added up per visit, or all added up. The middle value of each pixel is used, so cosmic rays and passing asteroids drop out and the noise falls roughly with the square root of the number of exposures. Every view (blink, swipe, difference, time-lapse) then works on the deep pictures. |
| Gaia overlay | Stars of ESA's Gaia DR3 catalogue, each drawn where its measured motion puts it on the date of the picture on screen. Fast stars get a line to where they will be in ten years. Pointing at a ring gives the star's brightness, motion and distance. |
| Spectrum and light curve | Every found object gets its brightness at each wavelength (a spectrum made on the fly from its own exposures), and brightness changers get their brightness at each visit. |
| Works when NASA's search is down | A record of where all 101,101 SPHEREx pointings looked, built from NASA's open AWS bucket, lets Blink X work out which exposures cover a position without IRSA's search service. Each exposure is still confirmed from its own FITS header. |
| Examples | Ten targets saved as static files (the challenge's five test objects among them), so the demo still works if the archive is slow or down. |
| Extras | Labels for known asteroids and comets in the field at that moment (IMCCE SkyBoT); mark suspected movers and copy their coordinates; every view has a shareable link. |

## Design: "Infrared Observatory"

The page is meant to feel like a precision instrument crossed with an astronomy poster, and the
real sky is the hero.

- **Landing**: a full-screen, zoomable map of the whole sky drawn by Aladin Lite from the
  SPHEREx DR1 all-sky cube that IRSA publishes as a HiPS. A slider scrubs through its 102
  wavelengths; the saved targets are pinned on the real sky; "Hunt the patch in view" starts a
  search wherever the map is pointing. If the map cannot load, a real SPHEREx exposure from the
  saved examples is shown instead.
- **Palette**: true black `#050506`, warm off-white `#EFE9DD`, and one accent, infrared orange
  `#FF5A1F`. Magenta/green (difference view) and the five doodle colours are data colours only,
  all colour-blind-safe.
- **Type**: Instrument Serif for headings (it reads like the title page of an observatory atlas
  and contrasts sharply with data), IBM Plex Mono for every coordinate, date and label, IBM Plex
  Sans for body text. All three are free Google Fonts.
- **Instrument details**: hairlines, sharp corners, a coordinate grid with RA/Dec tick labels and
  a reticle over every picture, small all-caps labels, timestamps written like a telescope readout.
- **Motion with a purpose**: a short crossfade on blink, an eased divider when swipe opens,
  doodles that draw themselves in, a slow drift of the landing sky. All of it is switched off
  under `prefers-reduced-motion`.
- **Tokens**: every colour, font and spacing step is a CSS variable at the top of
  `frontend/style.css`. Icons are Lucide, inlined as an SVG sprite (no icon library is loaded).
- **Phone**: the picture runs edge to edge, the mode bar scrolls sideways, and the Object Card
  becomes a full-screen sheet.

Before/after screenshots are in `submission/screens/`.

## Sky Doodles: automatic change detection

Blink X does not only show the pictures; it looks for the changes itself (`backend/detect.py`,
astropy + photutils) and turns each one into a small drawing that is easy to remember and share.

| Doodle | Meaning | How it is recognised |
|---|---|---|
| **Spark** | an asteroid passing through | a point of light on a straight, constant-speed track during one visit only |
| **Comet tail** | a comet | the same, but its light is spread wider than the stars' in the same exposures |
| **Arrow** | a nearby star or brown dwarf | always present, drifting steadily from visit to visit (proper motion) |
| **Pulse** | a variable star or transient | stays put; brightness differs between visits after removing each exposure's colour trend |
| **Zigzag** | a very distant solar-system body (a Planet X candidate) | jumps back and forth between visits six months apart (parallax), which also gives its distance |

Length = speed, angle = direction, colour = type (colour-blind-safe palette), line thickness =
brightness. Every doodle has a short ID (for example `SPK-589`) and a nickname.

How it works, in order: find sources in every exposure → group detections that fall on the same
spot of sky → stars present all the time become anchors that check the alignment (a star-pattern
shift on top of the WCS, reported in the page) and set a common brightness scale → detections
that exist only part of the time are linked into straight tracks → anchors are tested for slow
drift and for brightness changes. Faint detections inside the glare of a very bright object, and
anything seen in a single exposure only, are dropped: those are halos, reflections and cosmic rays.

**Spectrum in the Object Card.** Every SPHEREx exposure sees a spot of sky in one infrared colour,
so the exposures of one object add up to a piece of its spectrum. The card plots the object's
brightness (approximate millijanskys, 9.2″ aperture, no aperture correction) against wavelength,
marks where common gases glow, and reads the shape in plain words, with the reasons it might be
wrong. On the saved CO₂-band field the interstellar comet 3I/ATLAS comes out about 65 times
brighter at 4.25 µm than next to it: carbon dioxide gas glows at 4.26 µm. Repeat visits to the
same wavelength are combined first, so a change with time is not read as colour
(`backend/detect.py: spectrum`, tested in `tests/test_detect.py`).

Flagged objects are then checked against catalogues (`backend/catalogs.py`): IMCCE SkyBoT and
JPL Horizons for asteroids and comets, SIMBAD for fast-moving and variable stars. A match is
labelled **known**. No match is labelled **candidate**, with the reasons it might be nothing.
Blink X never claims a discovery.

Checked on real data: on the saved fields the detector finds, on its own, comet 3I/ATLAS at
175″/h, Vesta at 37.1″/h, Psyche at 36.1″/h and Barnard's Star at 10.0″/yr (catalogue: 10.39″/yr),
one doodle per field and nothing else. Nobody has found a zigzag in SPHEREx data, so that shape is
shown on a **simulated** field, clearly labelled as simulated; the same detection code runs on it,
and the tests check that it recovers the simulated planet's distance (`tests/test_detect.py`).

A zigzag has to be physically possible before it is drawn: the size of the jump gives a distance,
and at that distance Kepler's third law allows only a small drift from one year to the next. Three
blips that merely line up fail that test. A zigzag seen in only three visits is still worded as a
weak candidate.

**Deep search.** Slow movers that are too faint to follow in single exposures are looked for in
the visit stacks: each visit's exposures are added together, the sources of every deep picture are
matched from visit to visit, what is left of the misalignment is removed using the stars
themselves, and a source that then shifts by half a SPHEREx pixel or more, and by six times the
scatter of the ordinary stars, is reported as an arrow. Crowded sources and sources next to a much
brighter one are left out, because their measured centres wander. This is how WISE 0855 is found.
The test suite checks it on a made-up field: a source at 4.5 times the noise per exposure is found
when it moves and not reported when it does not.

**Steady, or not at all.** A deep find must be seen in at least three visits, and every sighting in
between must sit where a straight, even-paced path from the first to the last puts it. With only
two visits the shift has to be a full SPHEREx pixel and ten times the stars' scatter. Sources at
the edge of a detector, where not every exposure covers them, are left out.

**Set aside by an older survey.** A drift of an arcsecond a year or more that no catalogue names is
checked against NASA's WISE (2010) and ESA's Gaia (2016): if a source already sat on that very
spot then, nothing travelled there, and the doodle is dropped. The panel says what was dropped and
why. On one test field this removed an apparent 4.2″-a-year drift that had passed every other test.

**Catalogued but not found.** When SIMBAD lists a star or brown dwarf moving an arcsecond a year or
more inside the field and no doodle explains it, the panel says so, gives its position and suggests
what to try (another band, adding the exposures up). Staying silent would be the easier lie.

**Uncertainties.** Arrows carry the uncertainty of their speed, and the Object Card shows it next
to the catalogue value. Pictures are put on a common brightness scale using the stars they share
(one vote per star), so a target that really changed is not scaled back to look unchanged.

Views: Blink, **Swipe** (drag a divider), Side by side, **Difference** (magenta = new or brighter,
green = gone or dimmer), Time-lapse. Shortcuts: `B` `S` `D` `T`, `←`/`→` change the later epoch,
space pauses. Because the wavelength varies across every SPHEREx exposure, Blink X reads the exact
wavelength at your position from each file, pairs the closest ones and warns when two pictures
differ in colour.

## Sharing and science tools

- **Sky Code**: one string (for example `SKY2.ZZBNaxtB…`, 200–400 characters) that stores the
  field, its size, the colour band, the two pictures compared and every doodle. Paste it into the
  page or open `…/?sky=<code>`; the same view opens, the search runs again, and the page says
  whether it still finds the doodles the code lists.
- **Exports**: the doodle map as PNG or SVG (picture + doodles + key), all data as JSON, and a CSV
  with one row per doodle per epoch (id, type, x/y and RA/Dec, displacement in arcsec and SPHEREx
  pixels, direction, rate, brightness change, confidence, known/candidate).
- **Tracking Board**: every doodle in the field, filterable by type and by visit.
- **Scientist view**: one switch that adds the raw numbers: a table of every exposure (DATE-OBS,
  MJD, wavelength and bandwidth at the target, detector pixel, exposure, PSF, sky, noise, repaired
  pixels, star-pattern shift), the doodle table and the export buttons.
- **Keyboard**: `B` blink, `S` swipe, `D` difference, `T` time-lapse, `←`/`→` change the later epoch.

## The saved examples

| Example | What you see | SPHEREx data |
|---|---|---|
| Interstellar comet 3I/ATLAS | A comet from another star crosses a 12′ field in 3 h 20 min | 12 exposures, 14 Dec 2025, band 2 |
| Asteroid Vesta on the move | The brightest asteroid moves 6′ in ten hours | 11 exposures, 16–17 Jul 2026, band 2 |
| Spot the asteroid | (16) Psyche looks like a star until you blink | 8 exposures, 9 Sep 2025, band 3 |
| Barnard's Star | The fastest star in the sky shifts 11″ in 13 months | 20 exposures, Aug 2025 – Sep 2026, band 2 |
| Epsilon Indi B | A pair of brown dwarfs 12 light-years away slides 6.6″ in 17 months | 40 exposures, Apr 2025 – Oct 2026, band 2 |
| WISE 0855 | The coldest brown dwarf known appears when each visit's exposures are added up, and steps west | 48 exposures, May 2025 – May 2026, band 5, added up per visit |
| RW Aurigae | A young star about 60% brighter a year later | 40 exposures, Sep 2025 – Sep 2026, band 1 |
| R Draconis | A pulsing red giant that overloads the detector; no doodle, and why | 16 exposures, Jun 2025 – Jun 2026, band 2 |
| A comet's hidden gas | 3I/ATLAS swells into a cloud at 4.26 µm, where CO₂ glows | 12 exposures, 14 Dec 2025, band 5 |
| All five doodles (simulated) | A made-up field with a pretend Planet X at 500 au, to show the zigzag | **Simulated, not NASA data** |

The moving objects were found by `scripts/find_movers.py`: it takes an ephemeris from JPL Horizons,
asks IRSA which exposures cover the object's position at that time, and confirms on the real
image that there is a source on the predicted spot and nothing there in the other frames
(`scripts/mover_candidates.json`). Not every search succeeds: comet C/2025 R2 (SWAN), for example,
had no SPHEREx exposure in its 21–26 October 2025 window.

## Run it locally (one command)

```bash
./run.sh
```

Then open <http://localhost:8000>. The script uses [`uv`](https://docs.astral.sh/uv/) if you have
it (recommended: it picks Python 3.12 for you), otherwise it makes a `.venv` with `python3 -m venv`
(Python 3.11–3.13).

Tests (offline, a second or so):

```bash
pip install -r requirements-dev.txt && python -m pytest -q
```

Rebuild the saved examples from the live archive:

```bash
python scripts/build_examples.py
```

## How it works

```
browser (plain HTML/JS, canvas)
   │  /api/resolve   name → RA/Dec                      CDS Sesame
   │  /api/search    which exposures cover this spot    IRSA SIA2
   │  /api/frames    date + wavelength of each one      FITS headers  ┐ HTTP range requests on the
   │  /api/frame     one aligned cutout, as numbers     pixel rows    ┘ NASA copy on AWS (S3)
   │  /api/known-objects  catalogued asteroids/comets   IMCCE SkyBoT
   ▼
FastAPI backend (backend/) with an on-disk cache
```

A SPHEREx Level-2 image is a 62 MB multi-extension FITS file. Blink X never downloads a whole
one. For each exposure it reads:

1. the first ~40 kB: the header with `DATE-OBS`, the WCS (TAN + SIP distortion) and the keys of the
   spectral WCS;
2. only the detector rows that the cutout touches (a few hundred kB) from the `IMAGE` extension;
3. the same rows of the `FLAGS` extension, which is Rice-compressed one row per tile, so single rows
   can be decompressed on their own;
4. once per detector, the tiny `WCS-WAVE` lookup table at the end of the file, to get the wavelength
   at the target pixel.

The files are fetched from the public `nasa-irsa-spherex` bucket that IRSA lists in the SIA
`cloud_access` column, with IRSA's on-premises URL as fallback. Reading this way takes about half
a second per exposure and puts no cutout load on IRSA.

Each cutout is then resampled (bilinear) onto a north-up tangent-plane grid centred on the target.
Pixels the SPHEREx pipeline flagged as unusable (cosmic-ray hits, dead/hot pixels, missing data) are
filled from their good neighbours; the UI can show exactly which ones. The sky level (median) and
noise (MAD) are measured per frame, and the pixels travel to the browser as numbers rather than
pictures, so stretching, blinking and subtracting happen instantly on the device.

Checks made against the archive (see `spike/`): the wavelength lookup, observation date and pixel
values agree exactly with a cutout made by IRSA's own cutout service for the same file, and the
FLAGS decoder matches it bit for bit.

### Honest limits

- Every SPHEREx exposure sees one narrow infrared colour that changes across the detector, so two
  dates are never taken at exactly the same wavelength. Blink X picks the closest pair by default and
  can match star brightness between frames, but a star can still differ for that reason alone.
- SPHEREx pixels are 6.15″. Motions smaller than a few arcseconds between dates are not visible.
- Known-object positions are geocentric; SPHEREx is in low Earth orbit, a difference well under a
  pixel for main-belt asteroids.
- Names of asteroids and comets cannot be typed into the search box: they have no fixed position.
  Use the examples, or a position and date range you already know.
- IRSA's query service is the first choice for saying which exposures cover a position. When it is
  slow or down, Blink X reuses an earlier answer if it has one (and says so), uses its saved lists
  for well-known targets (`seed/sia3/`), and otherwise works the list out from its record of where
  SPHEREx pointed (`seed/pointings.npz`). On 38 positions that record proposed 99.9% of the 14,635
  exposures IRSA had listed. It is complete up to the day it was built (`scripts/build_pointing_index.py`
  rebuilds it after a new data release); the saved examples need no archive at all.
- The deep search needs at least two visits with five or more exposures each, two months or more
  apart, and six or more stars in common. It finds slow drifts, not objects that appear once.
- Very bright stars overload the detector. Their positions and brightness are less reliable, and
  Blink X then says so instead of drawing a doodle.
- The Gaia overlay is read from the VizieR catalogue service; the saved examples carry their own copy.
- In SPHEREx's two deep fields (near the ecliptic poles) a spot has tens of thousands of exposures;
  Blink X shows an even sample in time.
- "Mark a mover" keeps marks on your own device; there is no shared list yet.

## Deploy

One free service runs everything (API + page): see `render.yaml`.

1. Push this repository to GitHub.
2. On <https://render.com>: **New → Blueprint**, choose the repository, **Apply**.
3. Open the `https://<name>.onrender.com` address Render shows.

Free Render services sleep after 15 minutes without visitors and take about a minute to wake.
To give visitors an instant first page, also publish `frontend/` as a static site (GitHub Pages,
Netlify or Vercel) and set the backend address in `frontend/config.js`; the saved examples then load
with no backend at all, and live search wakes up in the background.

## Repository layout

```
backend/     FastAPI app: spherex.py (archive access + image maths), pointings.py (which exposures cover a position,
             without IRSA), detect.py (change detection, deep search, spectra), catalogs.py (known-object checks),
             gaia.py (Gaia DR3 stars), simulate.py (the simulated demo), resolver.py, skybot.py, cache.py, main.py
frontend/    index.html, style.css (design tokens + components), app.js (viewer), doodles.js (Sky Doodles),
             tools.js (Sky Code, exports, scientist view), landing.js (the sky map), config.js, examples/
scripts/     build_examples.py, build_seed.py, build_pointing_index.py (reads every pointing from NASA's open bucket),
             find_movers.py (finds asteroids/comets that SPHEREx imaged)
seed/        pointings.npz (where every SPHEREx pointing looked) and saved search results for well-known targets
spike/       the first data experiments and validation scripts
tests/       offline unit tests
submission/  project summary, resources list, AI-use note, video script, slide outline
```

## Data and services used

- **NASA SPHEREx** Level-2 spectral images, Data Release 1 and Quick Release 3 — NASA/IPAC
  Infrared Science Archive (IRSA): <https://irsa.ipac.caltech.edu/Missions/spherex.html>
- IRSA Simple Image Access v2: <https://irsa.ipac.caltech.edu/SIA>
- SPHEREx DR1 all-sky data cube as a HiPS map (the landing view): <https://irsa.ipac.caltech.edu/data/hips/SPHEREx/spherex_allsky_cube>
- IRSA SPHEREx archive documentation and cutout tutorial:
  <https://caltech-ipac.github.io/spherex-archive-documentation/> ·
  <https://caltech-ipac.github.io/irsa-tutorials/spherex-cutouts>
- SPHEREx on the AWS Registry of Open Data (`s3://nasa-irsa-spherex`): the image files, and the
  listing from which the pointing index is built
- **ESA Gaia** Data Release 3 (positions, proper motions, parallaxes, G magnitudes), read from the
  VizieR catalogue service (CDS, Strasbourg; CfA mirror), catalogue I/355/gaiadr3:
  <https://www.cosmos.esa.int/web/gaia/dr3> · <https://vizier.cds.unistra.fr/>
- CDS Sesame name resolver (SIMBAD, NED, VizieR): <https://cds.unistra.fr/cgi-bin/Sesame>
- IMCCE SkyBoT: <https://ssp.imcce.fr/webservices/skybot/>
- JPL Horizons (used offline to find which exposures caught the example asteroids/comets):
  <https://ssd.jpl.nasa.gov/horizons/>
- SIMBAD (CDS; CfA mirror) for proper motions and variable-star types: <https://simbad.cds.unistra.fr/>
- **NASA WISE** AllWISE source catalogue (positions from 2010), read from VizieR (II/328/allwise), for the
  "was a source already there?" check: <https://irsa.ipac.caltech.edu/Missions/wise.html>
- Aladin Lite v3 (CDS, free sky viewer, loaded from jsDelivr): <https://aladin.cds.unistra.fr/AladinLite/>
- Fonts: Instrument Serif, IBM Plex Sans, IBM Plex Mono (Google Fonts). Icons: Lucide.
- Software: Python, FastAPI, Astropy, photutils, NumPy, SciPy, httpx, Pillow.

## Credits and licence

Created by Khozhiakbar Khakimov Furkatzhonovich and Francia Constanza Coyotl Cortes (team KhoFra) at the Cambridge, MA local event, November 2026. Code is released under the MIT
licence (see `LICENSE`). SPHEREx data are public NASA data; please credit NASA/JPL-Caltech/IPAC.
This project is not affiliated with or endorsed by NASA.

AI assistance: see `submission/AI_USE.md`.
