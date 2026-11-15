# Use of AI tools

Blink X was built with the help of an AI coding assistant, Claude (Anthropic), used through
Claude Code.

**What the AI did**

- Wrote the Python backend, the HTML/CSS/JavaScript front end, the unit tests and the scripts in
  this repository, working from the team's written requirements.
- Ran the first data experiments against the live IRSA archive (which collections return results,
  FITS layout, how to read dates and wavelengths) and checked its own image reader against IRSA's
  cutout service.
- Searched the archive for exposures that caught known asteroids and comets, for the examples.
- Drafted the README, the project summary, the project-page texts, the video script, and built
  the seven-slide deck (`frontend/slides/`). Every picture in the deck is a real screenshot of the
  tool showing NASA data.
- In the final stage it also proposed additions, which the team accepted: adding exposures
  together, the search on the added-up pictures, the Gaia overlay, the record of SPHEREx
  pointings, the full spectrum on the fly and the embed mode.

**What the AI did not do**

- It did not generate, alter or invent any image or measurement. Every pixel and every date in the
  tool comes from NASA SPHEREx files; the AI wrote the code that reads them.
- There is no AI model inside the product. Blink X uses ordinary arithmetic and classical image
  analysis (alignment, stretch, subtraction, adding exposures together, source finding with
  photutils); what you see is the data.

**Human role**

The team chose the challenge and the idea (a blink comparator for SPHEREx that finds changes by
itself and draws them as "Sky Doodles"), set the requirements and the rules the tool must keep
(real data only, dates from the files, never claim a discovery), decided what went in, reviewed
the result and is responsible for this submission. Commits written with the assistant are marked
`Co-Authored-By: Claude` in the git history, and the page itself says so in its footer and in a
`<meta name="ai-assistance">` tag.
