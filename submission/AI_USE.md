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
- Drafted the README, the project summary, the video script and the slide outline.

**What the AI did not do**

- It did not generate, alter or invent any image or measurement. Every pixel and every date in the
  tool comes from NASA SPHEREx files; the AI wrote the code that reads them.
- There is no AI model inside the product. Blink X uses ordinary arithmetic and classical image
  analysis (alignment, stretch, subtraction, adding exposures together, source finding with
  photutils); what you see is the data.

**Human role**

The team chose the challenge, defined what the tool must do and how it should work, reviewed the
result and is responsible for this submission. Commits written with the assistant are marked
`Co-Authored-By: Claude` in the git history.
