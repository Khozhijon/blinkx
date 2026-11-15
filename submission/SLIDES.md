# Five-slide outline

## 1. Title — “Blink X: the sky moves. Catch it.”
- One line: a blink comparator for NASA's SPHEREx all-sky survey, in your browser.
- Visual: the landing page (the real SPHEREx Milky Way under the headline), or
  `submission/screens/after-desktop-1-landing.jpg`.
- Team KhoFra: Khozhiakbar Khakimov Furkatzhonovich and Francia Constanza Coyotl Cortes · NASA Space Apps 2026, Cambridge, MA · Challenge:
  *Planet X and SPHEREx* · public URL.

## 2. The problem
- SPHEREx re-images the whole sky about every six months, in 102 infrared colours: more than a
  billion objects.
- The interesting things are the ones that **change position**: asteroids, comets, nearby stars,
  brown dwarfs, maybe an undiscovered planet.
- Today that takes 62 MB science files, astronomy software and know-how. Each exposure has its own
  orientation and its own colour. The public cannot simply look.

## 3. The solution (demo slide)
- Type a name or coordinates → every SPHEREx exposure of that spot, aligned north-up, each with its
  real observation date.
- Five views: **Blink**, **Swipe**, **Side by side**, **Difference** (magenta = new,
  green = gone), **Time-lapse**.
- **Sky Doodles**: the app finds what changed and draws it — arrow (asteroid), tail (comet),
  zigzag (the wobble of a distant planet), spark (appeared or vanished), pulse (changed
  brightness). Each has an Object Card: measured speed, direction, catalogue check, a spectrum
  (comet 3I/ATLAS is 65 times brighter at 4.25 µm, where carbon dioxide glows), and the word
  “candidate” for anything unexplained.
- **Add exposures together** (per visit or all of them) to reach objects too faint for one
  exposure; lay **ESA Gaia** stars over the picture, each moved to the picture's date.
- **Spectra on the fly**: one click measures the full 0.75–5 µm spectrum of any spot from about a
  hundred exposures (Epsilon Indi B shows a brown dwarf's water and methane dips), with a CSV download.
- Choose the infrared band and field size, share any view with one **Sky Code**, **embed** it in
  any website with one line (`embed=1`), export JSON, CSV, SVG or PNG.
- Visual: three screenshots from `submission/screens/` — comet with its doodle
  (`after-desktop-2-viewer`), Object Card (`after-desktop-4-card`), all five doodles on the
  simulated field (`after-desktop-6-simulated`, labelled simulated).

## 4. How it works, and why you can trust it
- NASA data only: IRSA image search → partial reads of SPHEREx Level-2 files from NASA's open
  copy on AWS (header, the needed pixel rows, bad-pixel flags, wavelength table). About half a
  second per exposure; no whole-file downloads.
- Checked against IRSA's own cutout service: dates, wavelengths, pixel values and flags match.
- Honest display: sky glow removed, flagged pixels repaired from neighbours and shown on request,
  wavelength of every frame stated.
- **Tested on the challenge's five objects:** Barnard's Star 10.0 ± 1.2″ a year (catalogue 10.39),
  Epsilon Indi B 4.6 ± 0.4 (4.68), WISE 0855 found only in added-up visits at 8.2 ± 0.6 (8.15),
  RW Aurigae 59% brighter in a year, R Draconis: overloads the detector, so no claim.
- Also on real data: comet 3I/ATLAS 175″ per hour with carbon dioxide in its spectrum, Vesta 37″
  per hour. Never called a discovery.
- Keeps working when NASA's archive search is down: a record of all 101,101 SPHEREx pointings,
  built from NASA's open AWS copy, finds 99.9% of the exposures the archive lists.
- Known objects labelled (JPL Horizons, IMCCE SkyBoT, SIMBAD), so an unlabelled mover stands out.
- Robust for a live demo: the examples are saved real data, so they open even if the archive is busy.
- Small diagram: Browser ⇄ FastAPI ⇄ IRSA search / AWS files / CDS names / SkyBoT.

## 5. Impact and what comes next
- Anyone with a phone can watch a comet from another star cross the sky, or find an asteroid by eye.
- Classrooms: the Pluto discovery method, hands-on, with this year's NASA data.
- Researchers: a two-second visual check of any position across SPHEREx epochs.
- Next: a shared list where citizen scientists flag candidates for astronomers; calibrated
  spectra; a WISE overlay; each new SPHEREx release adds another epoch.
- Close with the URL and the repository link.
