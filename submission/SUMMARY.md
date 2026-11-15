# Blink X — project summary

**Problem.** NASA's SPHEREx telescope re-photographs the whole sky about every six months in 102
infrared colours. Hidden in those repeat images are things that move: asteroids, comets, nearby
stars, perhaps a planet nobody has seen. But each image is a 62 MB science file that only a
specialist can open, and no two exposures share the same orientation or colour.

**Solution.** Blink X is a free web tool that turns the archive into a blink comparator, the
device that found Pluto in 1930. Type a name or coordinates. Blink X finds every SPHEREx exposure of
that spot, lines them up north-up, and lets anyone blink between dates, see them side by side,
subtract them (new things glow orange, things that left turn blue) or play a time-lapse. Brightness,
colour band and field size are adjustable, and it works on a phone.

**How it uses NASA data.** Blink X asks NASA/IPAC's IRSA archive which SPHEREx Level-2 images
(DR1 and QR3) cover the position, then reads only the bytes it needs from NASA's open copy on AWS:
the header (the real observation date and astrometry), the pixel rows of the cutout, the pipeline's
bad-pixel flags and the per-pixel wavelength table. Our reader was checked against IRSA's own cutout
service. Known asteroids are labelled from a public catalogue service, so an unlabelled mover stands
out.

**Benefits.** Students and the public can watch real motion in space within seconds. Researchers
get a quick visual check of any position. Saved examples keep the demo working when the archive is
busy.

**Future work.** Follow a named asteroid or comet across the sky, automatic detection of movers
between visits, and a shared citizen-science list of candidates for astronomers to review.
