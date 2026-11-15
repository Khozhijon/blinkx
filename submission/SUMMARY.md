# Blink X — project summary

**Problem.** NASA's SPHEREx telescope re-photographs the whole sky every six months in 102
infrared colours. Hidden in those repeat images are things that move or change: asteroids, comets,
nearby stars, perhaps a planet nobody has seen. But each image is a 62 MB science file only a
specialist can open, and no two exposures share an orientation or colour.

**Solution.** Blink X is a free web tool that turns the archive into a blink comparator, the
device that found Pluto. It opens on the real SPHEREx sky. Type a name or coordinates; Blink X
finds every exposure of that spot, lines them up north-up, and lets anyone blink, swipe, subtract
(magenta = new, green = gone) or play a time-lapse. It then finds the changes itself and draws
each as a “Sky Doodle”: an arrow for an asteroid, a tail for a comet, a spark, a pulse, a zigzag
for the wobble a distant planet would show. Every doodle has an Object Card with measured speed,
direction and a catalogue check. Nothing is called a discovery: anything unexplained is a
“candidate”. One Sky Code shares any view.

**NASA data.** Blink X asks NASA/IPAC's IRSA archive which SPHEREx Level-2 images cover the
position, then reads only the bytes it needs from NASA's open copy on AWS: observation date,
astrometry, pixels, bad-pixel flags, wavelengths. The reader was checked against IRSA's own cutout
service. JPL Horizons, SkyBoT and SIMBAD label known objects.

**Benefits.** Students watch real motion in space within seconds. Researchers get a quick visual
check and exportable measurements. Saved examples keep the demo working when the archive is busy.

**Future work.** A shared candidate list for astronomers to review, a “Hunt for Planet X” game,
and a spectrum for every object.
