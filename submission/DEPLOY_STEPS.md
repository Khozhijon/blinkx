# Public URL — status

| Step | Status |
|---|---|
| GitHub repository | Done: <https://github.com/Khozhijon/blinkx> (public) |
| Static page on GitHub Pages | Done: <https://khozhijon.github.io/blinkx/> |
| Backend on Render (free plan) | Done: <https://blinkx-khofra.onrender.com> (service `blinkx-khofra`, blueprint `blinkx`) |
| Demo video | **Needs you** — `submission/VIDEO_SCRIPT.md` |
| Demo slides (the allowed alternative to the video) | Done: <https://khozhijon.github.io/blinkx/slides/blinkx-slides.pdf> (7 slides; web version at `/slides/`) |
| Space Apps submission form | **Needs you** |

## What to put in the submission form

Everything is written out field by field in **`submission/PROJECT_PAGE.md`**: open it and paste.

- Project Name, High-Level Project Summary, Detailed Project Description, Use of Super Intelligence,
  NASA Data, Space Agency Partner Data and Other References: copy from `PROJECT_PAGE.md`.
- Link to Final Project: `https://khozhijon.github.io/blinkx/`
- Link to Project Demo: your video (30 seconds or less), recorded from `submission/VIDEO_SCRIPT.md`,
  or the ready 7-slide deck: `https://khozhijon.github.io/blinkx/slides/blinkx-slides.pdf`.
- Then tick the two boxes and press **Submit for Judging** before 11:59 PM Eastern on 15 November.

## Good to know before judging

- Use the GitHub Pages address as the demo URL. It opens at once with the saved examples. The
  Render server sleeps after 15 minutes without visitors; the page wakes it in the background
  (about a minute), and says so next to the search box.
- Before recording the video or presenting, open the page a few minutes early and run one search,
  so the server is awake and the search is cached.
- If NASA's archive search (IRSA) is slow or down, live search still works: it uses saved lists for
  well-known targets and, for anywhere else, its own record of where SPHEREx pointed. The examples
  are not affected.
- Render will show "Upgrade" offers in its dashboard. The service is on the Free plan; nothing in
  this project needs a paid plan.

## Updating the site later

```bash
git push origin main && sh scripts/publish_pages.sh
```

`publish_pages.sh` updates the GitHub Pages copy. The Render backend did not redeploy by itself after a
push on 15 Nov 2026, so after changing backend code open the service in the Render dashboard and choose
**Manual Deploy → Deploy latest commit**.
