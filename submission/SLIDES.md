# Five-slide outline

## 1. Title — “Blink X: see what moved”
- One line: a blink comparator for NASA's SPHEREx all-sky survey, in your browser.
- Visual: the comet 3I/ATLAS example mid-blink (screenshot or a looping GIF).
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
- Four views: **Blink**, **Side by side**, **Difference** (orange = new, blue = gone),
  **Time-lapse**.
- Choose the infrared band and field size, adjust brightness, share a link to any view.
- Visual: three small screenshots — comet time-lapse, “spot the asteroid” with the label on,
  Barnard's Star difference image.

## 4. How it works, and why you can trust it
- NASA data only: IRSA image search → partial reads of SPHEREx Level-2 files from NASA's open
  copy on AWS (header, the needed pixel rows, bad-pixel flags, wavelength table). About half a
  second per exposure; no whole-file downloads.
- Checked against IRSA's own cutout service: dates, wavelengths, pixel values and flags match.
- Honest display: sky glow removed, flagged pixels repaired from neighbours and shown on request,
  wavelength of every frame stated.
- Known asteroids and comets labelled (IMCCE SkyBoT, JPL Horizons), so an unlabelled mover stands out.
- Robust for a live demo: the examples are saved real data, so they open even if the archive is busy.
- Small diagram: Browser ⇄ FastAPI ⇄ IRSA search / AWS files / CDS names / SkyBoT.

## 5. Impact and what comes next
- Anyone with a phone can watch a comet from another star cross the sky, or find an asteroid by eye.
- Classrooms: the Pluto discovery method, hands-on, with this year's NASA data.
- Researchers: a two-second visual check of any position across SPHEREx epochs.
- Next: follow a named asteroid or comet automatically; automatic mover detection between visits;
  a shared list where citizen scientists flag candidates for astronomers; each new SPHEREx release
  adds another epoch.
- Close with the URL and the repository link.
