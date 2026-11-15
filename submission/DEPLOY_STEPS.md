# Public URL — status

| Step | Status |
|---|---|
| GitHub repository | Done: <https://github.com/Khozhijon/blinkx> (public) |
| Static page on GitHub Pages | Done: <https://khozhijon.github.io/blinkx/> |
| Backend on Render (free plan) | Done: <https://blinkx-khofra.onrender.com> (service `blinkx-khofra`, blueprint `blinkx`) |
| Demo video | **Needs you** — `submission/VIDEO_SCRIPT.md` |
| Space Apps submission form | **Needs you** |

## What to put in the submission form

- Demo URL: `https://khozhijon.github.io/blinkx/`
- Repository: `https://github.com/Khozhijon/blinkx`
- Summary: `submission/SUMMARY.md`
- Data and resources: `submission/RESOURCES.md`
- AI use: `submission/AI_USE.md`
- Video: record it from `submission/VIDEO_SCRIPT.md`; slides from `submission/SLIDES.md`

## Good to know before judging

- Use the GitHub Pages address as the demo URL. It opens at once with the saved examples. The
  Render server sleeps after 15 minutes without visitors; the page wakes it in the background
  (about a minute), and says so next to the search box.
- Before recording the video or presenting, open the page a few minutes early and run one search,
  so the server is awake and the search is cached.
- If NASA's archive search (IRSA) is slow or down, live search says so and falls back to saved
  results for well-known targets; the examples are not affected.
- Render will show "Upgrade" offers in its dashboard. The service is on the Free plan; nothing in
  this project needs a paid plan.

## Updating the site later

```bash
git push origin main && sh scripts/publish_pages.sh
```

`publish_pages.sh` updates the GitHub Pages copy. The Render backend did not redeploy by itself after a
push on 15 Nov 2026, so after changing backend code open the service in the Render dashboard and choose
**Manual Deploy → Deploy latest commit**.
