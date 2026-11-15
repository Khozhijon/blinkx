# Public URL — status and the one step left for you

| Step | Status |
|---|---|
| GitHub repository | Done: <https://github.com/Khozhijon/blinkx> (public) |
| Static page on GitHub Pages | Done: <https://khozhijon.github.io/blinkx/> — the saved examples work now |
| Backend on Render (live search of the whole archive) | **Needs you** — see below |
| Demo video | Needs you — `submission/VIDEO_SCRIPT.md` |
| Space Apps submission form | Needs you |

## Deploy the backend on Render (about 4 clicks, free plan)

1. Open <https://render.com/deploy?repo=https://github.com/Khozhijon/blinkx>
2. Press **GitHub** to sign in. The first time, Render asks to read your repositories: allow the
   `blinkx` repo (or all).
3. Render shows the blueprint "blinkx-khofra" on the **Free** plan. Press **Deploy Blueprint** / **Apply**.
   If Render asks for a payment card, stop and tell Claude: the blueprint only asks for the free plan.
4. Wait 3–5 minutes for the first build. The address should be
   `https://blinkx-khofra.onrender.com`. If Render shows a different address, tell Claude: one
   line in `frontend/config.js` must match it.

When it is up, the GitHub Pages site switches from "Live search is offline" to "Live search … is
ready" by itself. The Render address also serves the whole tool on its own.

A free Render service sleeps after 15 minutes without visitors and needs about a minute to wake;
that is why the GitHub Pages address is the better **demo URL**: it opens at once.

## Submission form

- Demo URL: `https://khozhijon.github.io/blinkx/`
- Repository: `https://github.com/Khozhijon/blinkx`
- Summary: `submission/SUMMARY.md`
- Data and resources: `submission/RESOURCES.md`
- AI use: `submission/AI_USE.md`
- Video: record it from `submission/VIDEO_SCRIPT.md`; slides from `submission/SLIDES.md`

## Updating the site later

```bash
git push origin main && sh scripts/publish_pages.sh
```
