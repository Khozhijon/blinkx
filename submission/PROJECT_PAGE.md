# Space Apps project page — texts ready to paste

Where: spaceappschallenge.org → profile icon → **My Team** → **Project** tab → **Edit**.
Press **Save Progress** often. When every field is filled: tick the two boxes, then
**Submit for Judging**. Deadline: **Sunday 15 November 2026, 11:59 PM Eastern** (Cambridge, MA
local event). You can edit and resubmit until then; only the last saved version is judged.
Everything on the page must be in English.

---

## Project Name

Blink X

## High-Level Project Summary

Blink X is a public web tool that lets anyone see how the sky changes in NASA's SPHEREx images.
Enter a name or sky coordinates (RA and Dec) and it finds every SPHEREx exposure of that patch,
lines the images up, and plays them like a little video: blink, swipe, side by side, difference
or time-lapse. It then finds what moved or changed by itself, draws each change as a "Sky Doodle",
measures its speed and direction, checks catalogues of known objects, and plots the object's
spectrum on the fly. Nothing is called a discovery: an unexplained change is labelled a candidate.

We tested it on the five objects the challenge names. Blink X finds Barnard's Star and Epsilon
Indi B moving at their catalogued speeds, sees RW Aurigae grow 59% brighter in a year, and finds
WISE 0855, the coldest brown dwarf known, which is too faint for a single exposure: it appears
only when the tool adds each visit's exposures together.

SPHEREx re-photographs the whole sky every six months in 102 infrared colours, far more than any
one person can check. Blink X turns that archive into something a student with a phone can search
in seconds, the same way Pluto was found in 1930.

## Link to Project Demo

(paste the public link to the 30-second video here)

## Link to Final Project

https://khozhijon.github.io/blinkx/

## Detailed Project Description

**What it does.** Blink X opens on the real SPHEREx all-sky map with a slider through all 102
wavelengths. Type a name (for example "Barnard's Star") or coordinates, or put them in the URL
(`?ra=269.446&dec=4.769`). Blink X shows every SPHEREx exposure of that spot with its real
observation date and wavelength, and five ways to compare them: Blink, Swipe, Side by side,
Difference (magenta = new or brighter, green = gone or dimmer) and Time-lapse. You choose the
detector band and the field of view (3 to 24 arcminutes). Pixels that NASA's pipeline flagged as
bad are repaired from their neighbours and can be shown on request.

**Adding exposures together.** One selector switches from single exposures to each visit's
exposures added up, or all of them. The middle value of every pixel is used, so cosmic-ray hits
drop out and the noise falls with the square root of the number of exposures. All five views then
work on the deep pictures. An overlay shows the stars of ESA's Gaia catalogue, each moved to
where Gaia's measured motion puts it on the date of the picture, with brightness, motion and
distance on hover.

**Sky Doodles.** The backend looks for changes on its own: it finds the sources in every
exposure, uses the stars to check the alignment, links moving detections into tracks, and tests
steady stars for drift and brightness changes. Each find is drawn as a doodle: arrow (a nearby
star drifting), spark (an asteroid), comet tail, pulse (a brightness change) and zigzag (the
back-and-forth parallax a very distant planet would show). An Object Card gives the measured
motion in arcseconds and SPHEREx pixels, a confidence score, the catalogue check (JPL Horizons,
IMCCE SkyBoT, SIMBAD) and a spectrum built from the object's own exposures. Known objects are
named; everything else is a candidate, with the reasons it might be nothing.

**Tested on the challenge's five objects.** Each is a one-click target, and can be typed as the
challenge writes it. What Blink X reports by itself:

- Barnard's Star: moving 10.0 ± 1.2 arcseconds a year (catalogue: 10.39).
- Epsilon Indi B: moving 4.6 ± 0.4 arcseconds a year (catalogue: 4.68).
- WISE 0855: found only in the added-up visits, moving 8.2 ± 0.6 arcseconds a year (catalogue:
  8.15). Its spectrum rises from 0.24 mJy at 3.9 micrometres to 0.53 mJy at 4.3, as a very cool
  object's should. ESA's Gaia catalogue does not list it at all.
- RW Aurigae: 59% brighter in September 2026 than in September 2025, with a brightness chart.
- R Draconis: no doodle. The star overloads the detector; Blink X measures changes of 10–20%
  that it cannot trust, and says so instead of guessing.

**Also checked on real data.** The detector finds, by itself, the interstellar comet 3I/ATLAS
moving 175 arcseconds per hour and the asteroids Vesta and Psyche at 37 and 36 arcseconds per
hour. The spectrum of 3I/ATLAS is about 65 times brighter at 4.25 micrometres than next to it,
which is where carbon dioxide gas glows. Nobody has found a zigzag in SPHEREx data, so that shape
is shown on a field that is clearly labelled as simulated. When a catalogue lists a fast-moving
object in the field that the search did not find, the page says that too. And an apparent drift
that no catalogue names is checked against NASA's WISE (2010) and ESA's Gaia (2016): if a source
already sat on that spot then, the doodle is dropped and the page says why.

**How it works.** The page is plain HTML, CSS and JavaScript. A small Python service (FastAPI,
Astropy, photutils, NumPy) asks NASA/IPAC's IRSA archive which SPHEREx Level-2 images cover the
position, then reads only the bytes it needs from NASA's open copy of the files on AWS: the
header, the pixel rows of the cutout, the bad-pixel flags and the wavelength table. It never
downloads a whole 62 MB file. Images are put on a common north-up grid and sent to the browser,
where all comparing is done. Because it queries the archive live, new SPHEREx releases appear
without any change to the tool.

**It keeps working when the archive's search is down.** IRSA's search service was unreachable
for hours during the hackathon. We therefore read where every one of SPHEREx's 101,101 pointings
looked straight from NASA's open bucket (one small header read each) and taught the tool the
layout of the six detectors. With that record it works out which exposures cover any position
without the search service, then confirms each one from its own file. On 38 positions it
proposed 99.9% of the 14,635 exposures the archive had listed.

**Sharing and science tools.** One short "Sky Code" or link reproduces any view. Results export
as JSON, CSV, SVG or PNG. A Scientist view shows coordinates, wavelengths and signal-to-noise.

**Benefits.** Students and the public can watch real motion in space within seconds, on a phone.
Teachers get the Pluto discovery method with this year's NASA data. Researchers get a quick
visual check of any position across SPHEREx epochs, with measurements they can export.

**What we hope to achieve.** A shared list where volunteers flag candidates for astronomers to
review, the full 102-colour spectrum of every object, and a WISE overlay next to the Gaia one.

**Tools.** Python 3.12, FastAPI, Astropy, photutils, NumPy, SciPy, httpx, Pillow, pytest (32
tests); HTML, CSS, JavaScript; Aladin Lite; hosted free on GitHub Pages and Render.
Code: https://github.com/Khozhijon/blinkx

**Team KhoFra.** Khozhiakbar Khakimov Furkatzhonovich and Francia Constanza Coyotl Cortes.

## Use of Super Intelligence (SI)

Yes. We used Claude (Anthropic), through Claude Code, as an AI coding assistant. Working from our
written requirements, it wrote the Python backend, the HTML/CSS/JavaScript front end, the tests
and the scripts, ran data experiments against the IRSA archive, and drafted the documentation.
We chose the challenge, defined what the tool must do and how it should work, reviewed the
results and are responsible for the submission.

No image, measurement or date shown in Blink X is AI-generated: every pixel comes from NASA
SPHEREx files. There is no AI model inside the product; change detection and the adding-up of
exposures are classical image analysis (Astropy, photutils, NumPy). The one made-up field in the tool is a numerical simulation,
labelled "simulated" on screen. AI-assisted commits are marked "Co-Authored-By: Claude" in the
git history, and the repository states the AI assistance in README.md and submission/AI_USE.md.

## NASA Data

- SPHEREx Level-2 spectral images, Data Release 1 and Quick Release 3 (NASA / JPL-Caltech /
  IPAC): every picture, date, wavelength and bad-pixel flag shown.
  https://irsa.ipac.caltech.edu/Missions/spherex.html
- NASA/IPAC Infrared Science Archive (IRSA) Simple Image Access service: finds which SPHEREx
  images cover a position. https://irsa.ipac.caltech.edu/SIA
- SPHEREx on AWS Open Data (`nasa-irsa-spherex`): partial reads of the image files, and the
  record of where every pointing looked (built from the headers of 101,101 files).
- SPHEREx DR1 all-sky data cube (HiPS, 102 wavelengths) at IRSA: the zoomable landing map.
  https://irsa.ipac.caltech.edu/data/hips/SPHEREx/spherex_allsky_cube
- IRSA SPHEREx archive documentation and the "SPHEREx cutouts" tutorial; the IRSA cutout
  service, used to check our own image reader.
  https://caltech-ipac.github.io/spherex-archive-documentation/spherex-data-access
- JPL Horizons: positions of known asteroids and comets. https://ssd.jpl.nasa.gov/horizons/
- NASA WISE, AllWISE source catalogue (positions from 2010), read from VizieR: used to check
  whether a source was already on the spot of an apparent mover.
  https://irsa.ipac.caltech.edu/Missions/wise.html

## Space Agency Partner Data and Other References

- **ESA (European Space Agency): Gaia Data Release 3.** Positions, proper motions, parallaxes
  and G magnitudes of the stars in the field, for the Gaia overlay; read from the VizieR
  catalogue service (catalogue I/355/gaiadr3). https://www.cosmos.esa.int/web/gaia/dr3

- CDS Strasbourg: Sesame name resolver and SIMBAD (names, proper motions, variable-star types),
  https://cds.unistra.fr/cgi-bin/Sesame ; VizieR (serves the Gaia catalogue),
  https://vizier.cds.unistra.fr/ ; Aladin Lite v3 (the sky map viewer),
  https://aladin.cds.unistra.fr/AladinLite/
- IMCCE SkyBoT, Paris Observatory: known asteroids and comets in a field.
  https://ssp.imcce.fr/webservices/skybot/
- Software: Python, FastAPI, Uvicorn, Astropy, photutils, NumPy, SciPy, httpx, Pillow, pytest,
  Playwright (screenshots).
- Fonts: Instrument Serif, IBM Plex Sans, IBM Plex Mono (Google Fonts, open licences). Icons:
  Lucide (open source).
- AI coding assistant: Claude (Anthropic), see "Use of Super Intelligence".
- All code is our own repository, MIT licence: https://github.com/Khozhijon/blinkx

---

## Before you press "Submit for Judging"

1. Both teammates appear on the team's **Members** tab, and both are registered for the same
   local event (**Cambridge, MA**, not waitlisted). Teams that do not meet this are not eligible
   for global judging.
2. The demo is **30 seconds or less**. A longer video makes the project ineligible.
3. Open the video link and the project link in a private (incognito) window: no login asked.
4. All text is in English. A video in another language needs English subtitles.
5. Nobody under 18 appears in the video.
6. The name on your certificate is the "Full Name" in your profile; change it there if you want.
