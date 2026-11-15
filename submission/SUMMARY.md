# Blink X — project summary

Team KhoFra: Khozhiakbar Khakimov Furkatzhonovich and Francia Constanza Coyotl Cortes.

**Problem.** NASA's SPHEREx telescope re-photographs the whole sky every six months in 102
infrared colours. Hidden in those repeat images are things that move or change: asteroids, comets,
nearby stars, perhaps a planet nobody has seen. But each image is a 62 MB science file only a
specialist can open.

**Solution.** Blink X is a free web tool that turns the archive into a blink comparator, the
device that found Pluto. Type a name or coordinates; it finds every exposure of that spot, lines
them up, and lets anyone blink, swipe, subtract or play them as a time-lapse. It then finds the
changes itself and draws each as a “Sky Doodle”, with an Object Card: measured speed, a catalogue
check, a spectrum and a brightness chart. Exposures can be added together to reach fainter
objects, and ESA's Gaia stars can be laid over the picture. Nothing is called a discovery;
anything unexplained is a “candidate”.

**Tested on the challenge's five objects.** Blink X measures Barnard's Star at 10.0 and Epsilon
Indi B at 4.6 arcseconds a year (catalogue: 10.39 and 4.68), sees RW Aurigae brighten by 59%, and
finds WISE 0855, the coldest brown dwarf known, only by adding each visit's exposures together
(8.2 ± 0.6 arcseconds a year; catalogue 8.15).
For R Draconis, which overloads the detector, it says it cannot tell.

**NASA data.** SPHEREx Level-2 images from NASA/IPAC's IRSA archive, read byte-range by byte-range
from NASA's open copy on AWS. A record of all 101,101 SPHEREx pointings, built from that copy,
keeps the search working when the archive's own search is down.

**Benefits.** Students watch real motion in space within seconds. Researchers get a quick visual
check with exportable measurements.

**Future work.** A shared candidate list for astronomers, the full 102-colour spectrum of every
object, and a WISE overlay.
