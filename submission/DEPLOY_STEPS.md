# Getting the public URL — what only you can do

Everything is committed locally in `LocationKH/blinkx`. Three short steps need your accounts.
Claude does the rest (pushing code, publishing the static page, checking the live site).

## 1. Create the GitHub repository (1 click)

Open this link while signed in to GitHub as **Khozhijon** and press **Create repository**
(leave "Add a README" unticked):

<https://github.com/new?name=blinkx&visibility=public&description=Blink+X+%E2%80%94+watch+the+sky+change+in+NASA+SPHEREx+images+%28NASA+Space+Apps+2026%29>

Then tell Claude "repo created". Claude pushes the code and the static page from the Terminal panel:

```bash
git remote add origin https://github.com/Khozhijon/blinkx.git && git push -u origin main && sh scripts/publish_pages.sh
```

## 2. Deploy the backend on Render (about 4 clicks, free plan)

1. Open <https://render.com/deploy?repo=https://github.com/Khozhijon/blinkx>
2. Sign in with GitHub (first time: Render asks to read your repositories — allow the `blinkx` repo).
3. Render shows the blueprint "blinkx-khofra" on the **Free** plan. Press **Deploy Blueprint** / **Apply**.
   If Render asks for a payment card, stop and tell Claude: the blueprint only asks for the free plan.
4. Wait 3–5 minutes for the first build. The address will be
   `https://blinkx-khofra.onrender.com` (if Render shows a different address, tell Claude: one
   line in `frontend/config.js` must match it).

That address already serves the whole tool (page + API).

## 3. Turn on GitHub Pages for the instant-loading page (2 clicks, only if needed)

After Claude has run `scripts/publish_pages.sh`, open
<https://github.com/Khozhijon/blinkx/settings/pages>. If it does not already say the site is live,
choose **Branch: gh-pages**, folder **/ (root)**, **Save**. The page appears at
<https://khozhijon.github.io/blinkx/> after a minute.

Use the GitHub Pages address as the **demo URL** in the submission: it opens instantly with the
saved examples, and wakes the Render backend in the background for live search. (A free Render
service sleeps after 15 minutes without visitors and needs about a minute to wake.)

## 4. Submission form

- Demo URL: `https://khozhijon.github.io/blinkx/` (or the Render address)
- Repository: `https://github.com/Khozhijon/blinkx`
- Summary: `submission/SUMMARY.md`
- Data and resources: `submission/RESOURCES.md`
- AI use: `submission/AI_USE.md`
- Video: record it from `submission/VIDEO_SCRIPT.md`; slides from `submission/SLIDES.md`
