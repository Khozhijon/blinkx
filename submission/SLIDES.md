# Five-slide outline

## 1. Title — “Blink X: the sky moves. Catch it.”
- One line: a blink comparator for NASA's SPHEREx all-sky survey, in your browser.
- Visual: the landing page (the real SPHEREx Milky Way under the headline), or
  `submission/screens/after-desktop-1-landing.jpg`.
- Team KhoFra · NASA Space Apps 2026, Boston · Challenge: *Planet X and SPHEREx* · public URL.

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
  brightness). Each has an Object Card: measured speed, direction, catalogue check, and the word
  “candidate” for anything unexplained.
- Choose the infrared band and field size, share any view with one **Sky Code**, export JSON,
  CSV, SVG or PNG.
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
- Detection measured on real data: comet 3I/ATLAS 175″ per hour, Vesta 37″ per hour, Barnard's
  Star about 10.0″ per year (catalogue: 10.4). Never called a discovery.
- Known objects labelled (JPL Horizons, IMCCE SkyBoT, SIMBAD), so an unlabelled mover stands out.
- Robust for a live demo: the examples are saved real data, so they open even if the archive is busy.
- Small diagram: Browser ⇄ FastAPI ⇄ IRSA search / AWS files / CDS names / SkyBoT.

## 5. Impact and what comes next
- Anyone with a phone can watch a comet from another star cross the sky, or find an asteroid by eye.
- Classrooms: the Pluto discovery method, hands-on, with this year's NASA data.
- Researchers: a two-second visual check of any position across SPHEREx epochs.
- Next: a shared list where citizen scientists flag candidates for astronomers; a “Hunt for
  Planet X” game; a spectrum for every object; each new SPHEREx release adds another epoch.
- Close with the URL and the repository link.
