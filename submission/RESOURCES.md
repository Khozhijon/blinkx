# Data and resources used

## NASA data and resources

| Resource | How Blink X uses it | Link |
|---|---|---|
| SPHEREx Level-2 spectral images, Data Release 1 (`spherex_dr1`, `spherex_dr1_deep`) and Quick Release 3 (`spherex_qr3`, `spherex_qr3_deep`) | Every picture shown. Headers give the observation date, astrometry and wavelength; the IMAGE and FLAGS extensions give the pixels and bad-pixel mask. | https://irsa.ipac.caltech.edu/Missions/spherex.html |
| NASA/IPAC Infrared Science Archive (IRSA) Simple Image Access v2 service | Finds which SPHEREx images cover a sky position. | https://irsa.ipac.caltech.edu/SIA |
| IRSA SPHEREx archive documentation | Collections, file layout, cutout rules. | https://caltech-ipac.github.io/spherex-archive-documentation/spherex-data-access |
| IRSA tutorial "SPHEREx cutouts" | Extension layout and the spectral (wavelength) WCS recipe that our lookup was checked against. | https://caltech-ipac.github.io/irsa-tutorials/spherex-cutouts |
| IRSA image cutout service | Used during development to validate our own reader (dates, wavelengths, pixel values and flags match). | https://irsa.ipac.caltech.edu/ibe/cutouts.html |
| SPHEREx on AWS Open Data (`s3://nasa-irsa-spherex`, the `cloud_access` location given by IRSA) | Partial (HTTP range) reads of the image files. | https://registry.opendata.aws/ |
| SPHEREx DR1 all-sky data cube, HiPS map at IRSA (102 wavelengths) | The zoomable landing view of the whole infrared sky, with a wavelength slider. | https://irsa.ipac.caltech.edu/data/hips/SPHEREx/spherex_allsky_cube |
| JPL Horizons | Ephemerides used offline to find which SPHEREx exposures caught the example asteroids and comets. | https://ssd.jpl.nasa.gov/horizons/ |

## Other data and services

| Resource | Use | Link |
|---|---|---|
| CDS Sesame name resolver (SIMBAD, NED, VizieR), Strasbourg | Turns object names into coordinates and proper motions. | https://cds.unistra.fr/cgi-bin/Sesame |
| Aladin Lite v3, CDS Strasbourg (free, open source) | Draws the zoomable sky map on the landing page. | https://aladin.cds.unistra.fr/AladinLite/ |
| SIMBAD, CDS (CfA mirror) | Proper motions and variable-star types for the known/candidate check. | https://simbad.cds.unistra.fr/ |
| IMCCE SkyBoT, Paris Observatory | Known asteroids and comets inside a field at a given time. | https://ssp.imcce.fr/webservices/skybot/ |

## Software

Python 3.12, FastAPI, Uvicorn, Astropy, photutils, NumPy, SciPy, httpx, Pillow, pytest. The front end is plain
HTML, CSS and JavaScript with no framework or build step. Fonts: Instrument Serif, IBM Plex Sans and
IBM Plex Mono (Google Fonts). Icons: Lucide. Screenshots: Playwright. All free and open.
Hosting: Render (backend + page) and, optionally, GitHub Pages for the static page.

## Acknowledgement text

This work uses data from SPHEREx, a NASA mission managed by JPL/Caltech, obtained from the
NASA/IPAC Infrared Science Archive. It has made use of the SIMBAD database and the Sesame service
(CDS, Strasbourg, France) and of the SkyBoT service (IMCCE, Observatoire de Paris).
