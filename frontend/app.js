/* Blink X — front end. No build step, no dependencies.
 *
 * Pixels arrive as sky-subtracted numbers (not pictures), so brightness, colours, blinking and the
 * difference image are all computed here in the browser and respond instantly.
 */
(() => {
  "use strict";

  const API = String(window.BLINKX_API || "").replace(/\/$/, "");
  const $ = (id) => document.getElementById(id);
  const SOFT = 3;                 // asinh softening, in units of sky noise
  const MAX_FRAMES = 72;          // pictures loaded per band (evenly thinned beyond this)
  const VISIT_GAP_DAYS = 20;
  const NODATA = [20, 26, 43];
  const COL_A = [85, 184, 255], COL_B = [255, 169, 77];
  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const DEFAULTS = { hi: 50, lo: 30, cmap: "gray", match: true, smooth: true, cross: true, known: false, showFilled: false };

  const st = {
    token: 0, target: null, example: null, search: null,
    band: 2, size: 0.1, n: 128, frames: [], a: null, b: null,
    mode: "blink", playing: true, phase: 0, timeIdx: 0, speed: 55, arm: "b",
    marking: false, marks: [], knownCache: new Map(), hover: null,
    ...DEFAULTS,
  };
  let renderCache = new Map();
  let scaleCache = new Map();
  let timer = null;
  let examples = [];
  let apiOk = null;               // null = unknown, true/false after the health check

  /* ------------------------------------------------------------------ helpers */
  const rad = (d) => d * Math.PI / 180, deg = (r) => r * 180 / Math.PI;
  const clamp = (v, lo, hi) => v < lo ? lo : v > hi ? hi : v;
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const byId = (id) => st.frames.find((f) => f.id === id) || null;
  const gridSize = (size) => size <= 0.1 ? 128 : size <= 0.2 ? 192 : 256;
  const whitePoint = () => Math.pow(10, 3.5 - 2.7 * st.hi / 100);   // sigma
  const blackPoint = () => -6 + 0.15 * st.lo;                        // sigma

  function fmtDate(iso, withTime = true) {
    if (!iso) return "date unknown";
    const m = /^(\d{4})-(\d\d)-(\d\d)T(\d\d):(\d\d)/.exec(iso);
    if (!m) return iso;
    const d = `${+m[3]} ${MONTHS[+m[2] - 1]} ${m[1]}`;
    return withTime ? `${d}, ${m[4]}:${m[5]} UTC` : d;
  }
  const monthYear = (iso) => { const m = /^(\d{4})-(\d\d)/.exec(iso || ""); return m ? `${MONTHS[+m[2] - 1]} ${m[1]}` : "?"; };
  const fmtWl = (f) => f.wavelength_um ? `${f.wavelength_um.toFixed(2)} µm` : "";

  function fmtSexa(ra, dec) {
    const h = ra / 15, hh = Math.floor(h), mm = Math.floor((h - hh) * 60), ss = ((h - hh) * 60 - mm) * 60;
    const sgn = dec < 0 ? "−" : "+", ad = Math.abs(dec), dd = Math.floor(ad), dm = Math.floor((ad - dd) * 60), ds = ((ad - dd) * 60 - dm) * 60;
    const p = (v, n = 2) => String(v).padStart(n, "0");
    return `${p(hh)}h ${p(mm)}m ${p(ss.toFixed(1), 4)}s  ${sgn}${p(dd)}° ${p(dm)}′ ${p(ds.toFixed(0))}″`;
  }
  function fmtGap(days) {
    const d = Math.abs(days);
    if (d < 1 / 24) return `${Math.round(d * 1440)} minutes`;
    if (d < 2) return `${(d * 24).toFixed(1)} hours`;
    if (d < 60) return `${Math.round(d)} days`;
    if (d < 700) return `${Math.round(d / 30.44)} months`;
    return `${(d / 365.25).toFixed(1)} years`;
  }

  // Gnomonic projection used by the server for the north-up grid (east to the left).
  function skyToPix(ra, dec) {
    const n = st.n, step = rad(st.size / n), c = (n - 1) / 2;
    const a0 = rad(st.target.ra), d0 = rad(st.target.dec), a = rad(ra), d = rad(dec);
    const cosc = Math.sin(d0) * Math.sin(d) + Math.cos(d0) * Math.cos(d) * Math.cos(a - a0);
    const xi = Math.cos(d) * Math.sin(a - a0) / cosc;
    const eta = (Math.cos(d0) * Math.sin(d) - Math.sin(d0) * Math.cos(d) * Math.cos(a - a0)) / cosc;
    return [c - xi / step, c - eta / step];
  }
  function pixToSky(i, j) {
    const n = st.n, step = rad(st.size / n), c = (n - 1) / 2;
    const a0 = rad(st.target.ra), d0 = rad(st.target.dec);
    const xi = -(i - c) * step, eta = (c - j) * step, den = Math.cos(d0) - eta * Math.sin(d0);
    const a = a0 + Math.atan2(xi, den);
    const d = Math.atan2((Math.sin(d0) + eta * Math.cos(d0)) * Math.cos(a - a0), den);
    return [((deg(a) % 360) + 360) % 360, deg(d)];
  }

  let toastTimer = null;
  function toast(msg, ms = 3200) {
    const t = $("toast"); t.textContent = msg; t.hidden = false;
    clearTimeout(toastTimer); toastTimer = setTimeout(() => { t.hidden = true; }, ms);
  }
  function setStatus(msg, isError = false) {
    const s = $("status"); s.textContent = msg || ""; s.classList.toggle("error", !!isError);
  }

  async function getJson(url, timeoutMs = 90000) {
    const ctl = new AbortController();
    const to = setTimeout(() => ctl.abort(), timeoutMs);
    try {
      const r = await fetch(url, { signal: ctl.signal });
      if (!r.ok) {
        let detail = `Request failed (${r.status})`;
        try { const j = await r.json(); if (j && j.detail) detail = typeof j.detail === "string" ? j.detail : detail; } catch (_) { /* not JSON */ }
        throw new Error(detail);
      }
      return await r.json();
    } catch (e) {
      if (e.name === "AbortError") throw new Error("That took too long — the archive may be busy. Please try again.");
      if (e instanceof TypeError) throw new Error("Can't reach the live image server right now. The examples still work.");
      throw e;
    } finally { clearTimeout(to); }
  }
  const api = (path, params) => getJson(`${API}${path}?${new URLSearchParams(params)}`);

  /* ------------------------------------------------------------------ pixel decoding */
  function decodeFrame(f) {
    if (f.z || !f.data) return f;
    const n = f.n, len = n * n, bin = atob(f.data), z = new Float32Array(len);
    const { soft, umin, umax } = f.enc, k = (umax - umin) / 65534, inv = 1 / f.sigma;
    for (let i = 0, p = 0; i < len; i++, p += 2) {
      const q = bin.charCodeAt(p) | (bin.charCodeAt(p + 1) << 8);
      z[i] = q === 0 ? NaN : soft * Math.sinh(umin + (q - 1) * k) * inv;   // in units of this frame's sky noise
    }
    f.z = z;
    if (f.filled) {
      const fb = atob(f.filled), m = new Uint8Array(len);
      for (let i = 0; i < len; i++) m[i] = (fb.charCodeAt(i >> 3) >> (7 - (i & 7))) & 1;
      f.mask = m;
    }
    delete f.data; delete f.filled;
    f.loaded = true;
    return f;
  }

  /* ------------------------------------------------------------------ colour */
  function makeLut(stops) {
    const lut = new Uint8Array(256 * 3);
    for (let i = 0; i < 256; i++) {
      const t = i / 255;
      let k = 0; while (k < stops.length - 2 && t > stops[k + 1][0]) k++;
      const [t0, c0] = stops[k], [t1, c1] = stops[k + 1], u = clamp((t - t0) / (t1 - t0), 0, 1);
      for (let c = 0; c < 3; c++) lut[i * 3 + c] = Math.round(c0[c] + (c1[c] - c0[c]) * u);
    }
    return lut;
  }
  const LUTS = {
    gray: makeLut([[0, [0, 0, 0]], [1, [255, 255, 255]]]),
    invert: makeLut([[0, [250, 250, 246]], [1, [0, 0, 0]]]),
    heat: makeLut([[0, [0, 0, 4]], [0.2, [50, 12, 92]], [0.42, [140, 30, 100]], [0.62, [222, 73, 50]], [0.82, [251, 170, 40]], [1, [252, 255, 200]]]),
  };

  /** Brightness factor that puts frame f on the same flux scale as ref, measured on stars both see. */
  function scaleFor(f, ref) {
    if (!st.match || !f || !ref || f === ref || !f.z || !ref.z) return 1;
    const key = f.id + ">" + ref.id;
    if (scaleCache.has(key)) return scaleCache.get(key);
    // Median ratio over pixels that are clearly bright in both: stars that did not move. A median
    // ignores the mover itself, which is bright in different places in the two pictures.
    const a = ref.z, b = f.z, ratios = [];
    for (let i = 0; i < a.length; i++) {
      const x = a[i], y = b[i];
      if (x > 15 && y > 15) ratios.push(x / y);
    }
    ratios.sort((p, q) => p - q);
    const k = ratios.length >= 12 ? clamp(ratios[ratios.length >> 1], 0.2, 5) : 1;
    scaleCache.set(key, k);
    return k;
  }

  function frameCanvas(f, scale) {
    const key = `${f.id}|${scale.toFixed(4)}`;
    let cv = renderCache.get(key);
    if (cv) return cv;
    const n = f.n; cv = document.createElement("canvas"); cv.width = cv.height = n;
    const ctx = cv.getContext("2d"), img = ctx.createImageData(n, n), d = img.data, z = f.z;
    const lo = blackPoint(), norm = 1 / Math.asinh((whitePoint() - lo) / SOFT), lut = LUTS[st.cmap] || LUTS.gray;
    const mask = st.showFilled ? f.mask : null;
    for (let i = 0, p = 0; i < z.length; i++, p += 4) {
      const v = z[i];
      if (v !== v) { d[p] = NODATA[0]; d[p + 1] = NODATA[1]; d[p + 2] = NODATA[2]; d[p + 3] = 255; continue; }
      const t = clamp(Math.asinh((v * scale - lo) / SOFT) * norm, 0, 1), c = ((t * 255) | 0) * 3;
      d[p] = lut[c]; d[p + 1] = lut[c + 1]; d[p + 2] = lut[c + 2]; d[p + 3] = 255;
      if (mask && mask[i]) { d[p] = 255; d[p + 1] = (d[p + 1] * 0.35) | 0; d[p + 2] = 200; }
    }
    ctx.putImageData(img, 0, 0);
    renderCache.set(key, cv);
    return cv;
  }

  function diffCanvas(A, B) {
    const k = scaleFor(B, A), key = `diff|${A.id}|${B.id}|${k.toFixed(4)}`;
    let cv = renderCache.get(key);
    if (cv) return cv;
    const n = A.n; cv = document.createElement("canvas"); cv.width = cv.height = n;
    const ctx = cv.getContext("2d"), img = ctx.createImageData(n, n), d = img.data, za = A.z, zb = B.z;
    // Gentler than the picture stretch, with a dead zone so plain noise stays black.
    const noise = Math.hypot(1, k), softD = 12, dead = 2.5, norm = 1 / Math.asinh(Math.max(8, whitePoint() * 0.7) / softD);
    for (let i = 0, p = 0; i < za.length; i++, p += 4) {
      const a = za[i], b = zb[i];
      d[p + 3] = 255;
      if (a !== a || b !== b) { d[p] = NODATA[0]; d[p + 1] = NODATA[1]; d[p + 2] = NODATA[2]; continue; }
      const dv = (k * b - a) / noise, mag = Math.abs(dv) - dead;
      const u = mag <= 0 ? 0 : clamp(Math.asinh(mag / softD) * norm, 0, 1), col = dv >= 0 ? COL_B : COL_A;
      const w = u > 0.8 ? (u - 0.8) * 2.2 : 0;                     // strongest changes bleach towards white
      d[p] = col[0] * u + (255 - col[0]) * w * u; d[p + 1] = col[1] * u + (255 - col[1]) * w * u; d[p + 2] = col[2] * u + (255 - col[2]) * w * u;
    }
    ctx.putImageData(img, 0, 0);
    renderCache.set(key, cv);
    return cv;
  }

  function applySettings(v) {
    for (const k of Object.keys(DEFAULTS)) if (k in v) st[k] = v[k];
    $("hi").value = st.hi; $("lo").value = st.lo; $("cmap").value = st.cmap;
    for (const id of ["match", "smooth", "cross", "known", "showFilled"]) $(id).checked = st[id];
    $("stage").classList.toggle("crisp", !st.smooth);
    invalidate(true);
  }

  function invalidate(scales = false) { renderCache = new Map(); if (scales) scaleCache = new Map(); schedule(); }

  /* ------------------------------------------------------------------ drawing */
  let scheduled = false;
  function schedule() {
    if (scheduled) return;
    scheduled = true;
    const run = () => { if (!scheduled) return; scheduled = false; draw(); paintThumbs(); };
    requestAnimationFrame(run); setTimeout(run, 120);            // the timeout covers background tabs
  }

  function paint(pane, cv) {
    const el = $("cv" + pane);
    if (el.width !== cv.width) { el.width = el.height = cv.width; }
    const ctx = el.getContext("2d"); ctx.imageSmoothingEnabled = false; ctx.drawImage(cv, 0, 0);
  }
  function blank(pane) {
    const el = $("cv" + pane), ctx = el.getContext("2d");
    ctx.fillStyle = `rgb(${NODATA})`; ctx.fillRect(0, 0, el.width, el.height);
  }

  function shown() {
    const A = byId(st.a), B = byId(st.b);
    if (st.mode === "side") return [A, B];
    if (st.mode === "time") return [st.frames[st.timeIdx] || null];
    if (st.mode === "diff") return [B];
    return [st.phase ? B : A];
  }

  function draw() {
    if (!st.frames.length || !st.target) return;
    const A = byId(st.a), B = byId(st.b), need = [];
    let cap0 = "", cap1 = "";
    // two pictures from the same day are told apart by their time
    const sameDay = !!(A && B && A !== B && (A.date_obs || "").slice(0, 10) === (B.date_obs || "").slice(0, 10));
    const label = (f) => f ? `${fmtDate(f.date_obs, sameDay)} · ${fmtWl(f)}` : "";
    if (st.mode === "side") {
      need.push(A, B);
      if (A && A.z) paint(0, frameCanvas(A, 1)); else blank(0);
      if (B && B.z) paint(1, frameCanvas(B, scaleFor(B, A))); else blank(1);
      cap0 = `<span class="tag a">A</span>${esc(label(A))}`; cap1 = `<span class="tag b">B</span>${esc(label(B))}`;
    } else if (st.mode === "diff") {
      need.push(A, B);
      if (A && B && A.z && B.z) paint(0, diffCanvas(A, B)); else blank(0);
      cap0 = `<span class="tag d">B − A</span>${esc(fmtDate(B && B.date_obs, sameDay))} minus ${esc(fmtDate(A && A.date_obs, sameDay))}`;
    } else if (st.mode === "time") {
      const f = st.frames[st.timeIdx]; need.push(f);
      if (f && f.z) paint(0, frameCanvas(f, scaleFor(f, A && A.z ? A : null))); else blank(0);
      cap0 = `<span class="tag t">${st.timeIdx + 1} / ${st.frames.length}</span>${esc(f ? `${fmtDate(f.date_obs)} · ${fmtWl(f)}` : "")}`;
      $("timeOut").textContent = `${st.timeIdx + 1} of ${st.frames.length}`;
      if (+$("timeSlider").value !== st.timeIdx) $("timeSlider").value = st.timeIdx;
    } else {
      const f = st.phase ? B : A; need.push(A, B);
      if (f && f.z) paint(0, frameCanvas(f, st.phase ? scaleFor(B, A) : 1)); else blank(0);
      cap0 = `<span class="tag ${st.phase ? "b" : "a"}">${st.phase ? "B" : "A"}</span>${esc(label(f))}`;
    }
    $("cap0").innerHTML = cap0; $("cap1").innerHTML = cap1;
    // text alternative for screen readers: what each picture is
    $("cv0").setAttribute("aria-label", `SPHEREx infrared image of ${st.target.name || "this position"}: ${$("cap0").textContent}`);
    $("cv1").setAttribute("aria-label", `SPHEREx infrared image of ${st.target.name || "this position"}: ${$("cap1").textContent}`);
    const waiting = need.some((f) => f && !f.z && !f.failed), failed = need.find((f) => f && f.failed);
    $("load0").hidden = !(waiting || failed);
    if (waiting) $("loadText").textContent = "Fetching this picture from the SPHEREx archive…";
    else if (failed) $("loadText").textContent = "This picture could not be loaded from the archive. Pick another one below.";
    const vis = shown();
    drawOverlay(0, vis[0]); drawOverlay(1, vis[1] || null);
    markStrip(vis);
  }

  function drawOverlay(pane, f) {
    const svg = $("ov" + pane), n = st.n;
    svg.setAttribute("viewBox", `0 0 ${n} ${n}`);
    const u = n / 128, fs = 4.2 * u, sw = 0.45 * u; let s = "";
    const light = st.cmap === "invert" && st.mode !== "diff", ink = light ? "#111" : "#fff";
    if (st.cross) {
      const c = n / 2, g = 4.5 * u, l = 6.5 * u;
      const lines = `<line x1="${c - g - l}" y1="${c}" x2="${c - g}" y2="${c}"/><line x1="${c + g}" y1="${c}" x2="${c + g + l}" y2="${c}"/>` +
        `<line x1="${c}" y1="${c - g - l}" x2="${c}" y2="${c - g}"/><line x1="${c}" y1="${c + g}" x2="${c}" y2="${c + g + l}"/>`;
      s += `<g stroke="${light ? "#fff" : "#000"}" stroke-opacity=".55" stroke-width="${sw * 2.4}" stroke-linecap="round">${lines}</g>` +
        `<g stroke="${ink}" stroke-opacity=".9" stroke-width="${sw}">${lines}</g>`;
    }
    // scale bar (bottom right) and compass (bottom left)
    const arcsec = st.size <= 0.05 ? 30 : st.size <= 0.1 ? 60 : st.size <= 0.2 ? 120 : 300, len = arcsec / (st.size * 3600 / n);
    const bx = n - 5 * u - len, by = n - 6 * u;
    s += `<g stroke="${ink}" stroke-width="${sw * 1.6}" fill="${ink}"><line x1="${bx}" y1="${by}" x2="${bx + len}" y2="${by}"/>` +
      `<text x="${bx + len / 2}" y="${by - 2 * u}" text-anchor="middle" stroke="none" style="font-size:${fs}px">${arcsec >= 60 ? arcsec / 60 + "′" : arcsec + "″"}</text></g>`;
    const cx = 13 * u, cy = n - 7 * u, al = 9 * u;
    s += `<g stroke="${ink}" stroke-width="${sw * 1.4}" fill="${ink}" stroke-linecap="round"><line x1="${cx}" y1="${cy}" x2="${cx}" y2="${cy - al}"/><line x1="${cx}" y1="${cy}" x2="${cx - al}" y2="${cy}"/>` +
      `<text x="${cx}" y="${cy - al - 1.5 * u}" text-anchor="middle" stroke="none" style="font-size:${fs}px">N</text>` +
      `<text x="${cx - al - 1.5 * u}" y="${cy + 1.5 * u}" text-anchor="end" stroke="none" style="font-size:${fs}px">E</text></g>`;
    // catalogued solar-system objects at the moment this frame was taken
    if (st.known && f) {
      const objs = knownFor(f);
      if (objs) for (const o of objs) {
        const [i, j] = skyToPix(o.ra, o.dec);
        if (i < 0 || j < 0 || i > n - 1 || j > n - 1) continue;
        const name = o.number ? `(${o.number}) ${o.name}` : o.name;
        s += `<circle cx="${i + 0.5}" cy="${j + 0.5}" r="${5 * u}" fill="none" stroke="#7CFFB2" stroke-width="${sw * 1.3}"/>` +
          `<text x="${i + 0.5}" y="${j + 0.5 - 7 * u}" text-anchor="middle" fill="#7CFFB2" style="font-size:${fs}px">${esc(name)}</text>`;
      }
    }
    st.marks.forEach((m, k) => {
      const [i, j] = skyToPix(m.ra, m.dec), r = 4 * u;
      if (i < 0 || j < 0 || i > n - 1 || j > n - 1) return;
      s += `<rect x="${i + 0.5 - r}" y="${j + 0.5 - r}" width="${2 * r}" height="${2 * r}" fill="none" stroke="#ff5fa2" stroke-width="${sw * 1.4}" transform="rotate(45 ${i + 0.5} ${j + 0.5})"/>` +
        `<text x="${i + 0.5 + r * 1.6}" y="${j + 0.5 + fs / 3}" fill="#ff5fa2" style="font-size:${fs}px">${k + 1}</text>`;
    });
    if (st.hover && st.hover.pane !== pane && st.mode === "side") {
      s += `<circle cx="${st.hover.i}" cy="${st.hover.j}" r="${3.5 * u}" fill="none" stroke="#ffe36e" stroke-width="${sw * 1.3}"/>`;
    }
    svg.innerHTML = s;
  }

  /* ------------------------------------------------------------------ known objects (SkyBoT) */
  function knownFor(f) {
    if (st.knownCache.has(f.id)) return st.knownCache.get(f.id);
    st.knownCache.set(f.id, null);                               // in flight
    if (st.example && st.example.known && st.example.size === st.size && st.example.known[f.id]) {
      st.knownCache.set(f.id, st.example.known[f.id]);
      return st.example.known[f.id];
    }
    const token = st.token;
    api("/api/known-objects", { ra: st.target.ra, dec: st.target.dec, mjd: f.mjd, size: st.size })
      .then((j) => { if (token === st.token) { st.knownCache.set(f.id, j.objects || []); schedule(); } })
      .catch(() => { if (token === st.token) { st.knownCache.set(f.id, []); toast("The asteroid catalogue (SkyBoT) didn't answer for this picture."); } });
    return null;
  }

  /* ------------------------------------------------------------------ strip of thumbnails */
  function visitsOf(frames) {
    const out = [];
    for (const f of frames) {
      const last = out[out.length - 1];
      if (!last || f.mjd - last.end > VISIT_GAP_DAYS) out.push({ label: monthYear(f.date_obs), frames: [f], end: f.mjd });
      else { last.frames.push(f); last.end = f.mjd; }
    }
    return out;
  }

  function buildStrip() {
    const strip = $("strip"); strip.innerHTML = "";
    for (const v of visitsOf(st.frames)) {
      const g = document.createElement("div"); g.className = "visit";
      const lab = document.createElement("div"); lab.className = "vlabel"; lab.textContent = v.label; g.appendChild(lab);
      for (const f of v.frames) {
        const b = document.createElement("button"); b.type = "button"; b.className = "thumb pending"; b.dataset.id = f.id;
        b.title = `${fmtDate(f.date_obs)} — ${fmtWl(f)}`;
        const d = /^\d{4}-(\d\d)-(\d\d)T(\d\d):(\d\d)/.exec(f.date_obs || "");
        b.innerHTML = `<canvas width="66" height="66"></canvas><small>${d ? `${+d[2]} ${MONTHS[+d[1] - 1]} ${d[3]}:${d[4]}` : ""}<br>${esc(fmtWl(f))}</small>`;
        b.addEventListener("click", () => pickFrame(f.id));
        g.appendChild(b);
      }
      strip.appendChild(g);
    }
    const total = st.totalInBand || st.frames.length;
    $("stripCount").textContent = total > st.frames.length ? `— showing ${st.frames.length} of ${total} in this colour band` : `— ${st.frames.length} in this colour band`;
  }

  function paintThumbs() {
    const A = byId(st.a);
    for (const b of $("strip").querySelectorAll(".thumb")) {
      const f = byId(b.dataset.id); if (!f) continue;
      b.classList.toggle("pending", !f.z && !f.failed); b.classList.toggle("failed", !!f.failed);
      if (!f.z) continue;
      const ctx = b.firstChild.getContext("2d"); ctx.imageSmoothingEnabled = true;
      ctx.drawImage(frameCanvas(f, scaleFor(f, A && A.z ? A : null)), 0, 0, 66, 66);
    }
  }

  function markStrip(vis) {
    for (const b of $("strip").querySelectorAll(".thumb")) {
      const id = b.dataset.id, isA = id === st.a, isB = id === st.b;
      b.classList.toggle("is-a", isA); b.classList.toggle("is-b", isB);
      b.classList.toggle("is-now", st.mode === "time" && vis[0] && vis[0].id === id);
      let badges = b.querySelectorAll(".badge"); badges.forEach((x) => x.remove());
      if (isA) b.insertAdjacentHTML("beforeend", '<span class="badge a">A</span>');
      if (isB) b.insertAdjacentHTML("beforeend", '<span class="badge b">B</span>');
    }
  }

  function pickFrame(id) {
    if (st.mode === "time") { st.timeIdx = st.frames.findIndex((f) => f.id === id); setPlaying(false); schedule(); return; }
    if (st.arm === "a") st.a = id; else st.b = id;
    afterPairChange();
  }

  function afterPairChange() {
    $("selA").value = st.a; $("selB").value = st.b;
    ensureLoaded([byId(st.a), byId(st.b)]);
    invalidate(false); updateGap(); updateFacts(); syncUrl();
  }

  /* ------------------------------------------------------------------ text panels */
  function fillPairSelects() {
    for (const [sel, cur] of [[$("selA"), st.a], [$("selB"), st.b]]) {
      sel.innerHTML = "";
      for (const v of visitsOf(st.frames)) {
        const g = document.createElement("optgroup"); g.label = `Visit of ${v.label}`;
        for (const f of v.frames) {
          const o = document.createElement("option"); o.value = f.id; o.textContent = `${fmtDate(f.date_obs)} · ${fmtWl(f)}`; g.appendChild(o);
        }
        sel.appendChild(g);
      }
      sel.value = cur;
    }
  }

  function updateGap() {
    const A = byId(st.a), B = byId(st.b), el = $("gap");
    if (!A || !B) { el.textContent = ""; return; }
    if (A === B) { el.textContent = "A and B are the same picture — choose two different ones to compare."; return; }
    const dt = B.mjd - A.mjd;
    el.textContent = `B was taken ${fmtGap(dt)} ${dt >= 0 ? "after" : "before"} A.` +
      (Math.abs(A.wavelength_um - B.wavelength_um) > 0.12 ? " Their infrared colours differ a lot, so some stars will change brightness for that reason alone." : "");
  }

  function factCard(f, cls, title) {
    if (!f) return "";
    return `<div class="fact ${cls}"><h3>${esc(title)}</h3><dl>` +
      `<dt>Taken</dt><dd>${esc(fmtDate(f.date_obs))} <span class="muted">(DATE-OBS in the image file)</span></dd>` +
      `<dt>Colour</dt><dd>${f.wavelength_um ? f.wavelength_um.toFixed(3) + " µm" : "?"} infrared · band ${f.detector}</dd>` +
      `<dt>Exposure</dt><dd>${f.exptime ? f.exptime.toFixed(0) + " s" : "?"} · ${esc(f.collection.replace("spherex_", "SPHEREx ").toUpperCase().replace("SPHEREX", "SPHEREx"))}</dd>` +
      (f.sky !== undefined ? `<dt>Sky glow</dt><dd>${f.sky.toFixed(3)} MJy/sr <span class="muted">(removed)</span></dd>` : "") +
      `<dt>Source</dt><dd><a href="${esc(f.irsa_url)}" target="_blank" rel="noopener" title="Full NASA/IPAC image file (about 62 MB)">${esc(f.id)} (FITS)</a></dd>` +
      `</dl></div>`;
  }
  function updateFacts() {
    const A = byId(st.a), B = byId(st.b);
    let html = "";
    if (st.mode === "time") html += factCard(st.frames[st.timeIdx], "", "Picture on screen");
    html += factCard(A, "a", "Earlier image (A)") + factCard(B, "b", "Later image (B)");
    $("facts").innerHTML = html;
  }

  const HINTS = {
    blink: "Flipping between A and B. The stars stay still — watch for anything that jumps, appears or vanishes.",
    side: "Earlier picture on the left, later one on the right. Move over one to see the same spot in the other.",
    diff: "B minus A. Orange is new or brighter in B, blue was there in A, and whatever didn't change fades to black.",
    time: "Every exposure of this spot in this colour band, oldest to newest.",
  };

  function setMode(mode) {
    st.mode = mode;
    for (const t of document.querySelectorAll(".tabs button")) t.setAttribute("aria-selected", String(t.dataset.mode === mode));
    $("stage").dataset.mode = mode;
    $("modeHint").textContent = HINTS[mode];
    const anim = mode === "blink" || mode === "time";
    $("playBtn").hidden = !anim; $("speedWrap").hidden = !anim; $("timeWrap").hidden = mode !== "time";
    if (mode === "time") { const i = st.frames.findIndex((f) => f.id === st.a); if (i >= 0 && !st.playing) st.timeIdx = i; }
    restartTimer(); updateFacts(); schedule(); syncUrl();
  }

  function setPlaying(on) {
    st.playing = on; $("playBtn").textContent = on ? "Pause" : "Play"; $("playBtn").setAttribute("aria-pressed", String(on)); restartTimer();
  }
  function restartTimer() {
    clearInterval(timer); timer = null;
    if (!st.playing || document.hidden) return;
    if (st.mode === "blink") timer = setInterval(() => { st.phase ^= 1; draw(); }, clamp(1700 - 15 * st.speed, 180, 1700));
    else if (st.mode === "time") timer = setInterval(stepTime, 1000 / (1 + 0.09 * st.speed));
  }
  function stepTime() {
    const n = st.frames.length; if (!n) return;
    for (let k = 1; k <= n; k++) {            // skip pictures that have not arrived yet
      const i = (st.timeIdx + k) % n;
      if (st.frames[i].z) { st.timeIdx = i; break; }
    }
    draw(); updateFacts();
  }

  /* ------------------------------------------------------------------ loading */
  /** 1 if the field would run off the 2040-pixel detector in this exposure, else 0. */
  function nearEdge(f) {
    if (!f.pixel) return 0;
    const m = st.size * 3600 / 6.15 * 0.72, [x, y] = f.pixel;
    return x < m || y < m || x > 2039 - m || y > 2039 - m ? 1 : 0;
  }

  function choosePair(frames) {
    if (!frames.length) return [null, null];
    if (frames.length === 1) return [frames[0].id, frames[0].id];
    let best = null;
    for (let i = 0; i < frames.length; i++) for (let j = i + 1; j < frames.length; j++) {
      const dt = frames[j].mjd - frames[i].mjd; if (dt < VISIT_GAP_DAYS) continue;
      // closest infrared colour first, but a year's wait is worth about one colour step;
      // avoid pictures where the spot sits at the very edge of the detector (part of the field is missing)
      const wa = frames[i].wavelength_um || 1, wb = frames[j].wavelength_um || 1;
      const score = Math.abs(wa - wb) / wa - 6e-5 * dt + nearEdge(frames[i]) + nearEdge(frames[j]);
      if (!best || score < best[0]) best = [score, frames[i].id, frames[j].id];
    }
    return best ? [best[1], best[2]] : [frames[0].id, frames[frames.length - 1].id];
  }

  function thin(frames, keep = []) {
    if (frames.length <= MAX_FRAMES) return frames;
    const out = new Set(keep.filter(Boolean)), stepSize = frames.length / (MAX_FRAMES - out.size);
    for (let x = 0; x < frames.length; x += stepSize) out.add(frames[Math.floor(x)].id);
    return frames.filter((f) => out.has(f.id));
  }

  let queue = [], active = 0;
  function ensureLoaded(list, front = true) {
    const todo = list.filter((f) => f && !f.z && !f.loading && !f.failed);
    if (!todo.length) return;
    queue = front ? [...todo, ...queue.filter((f) => !todo.includes(f))] : [...queue, ...todo.filter((f) => !queue.includes(f))];
    pump();
  }
  function pump() {
    while (active < 6 && queue.length) {
      const f = queue.shift(); if (f.z || f.loading || f.failed) continue;
      const token = st.token; f.loading = true; active++;
      api("/api/frame", { ra: st.target.ra, dec: st.target.dec, id: f.id, size: st.size })
        .then((full) => { if (token !== st.token) return; Object.assign(f, full); decodeFrame(f); if (f.id === st.a) scaleCache = new Map(); })
        .catch(() => { if (token === st.token) f.failed = true; })
        .finally(() => { f.loading = false; active--; if (token === st.token) { progress(); schedule(); } pump(); });
    }
  }
  function progress() {
    const done = st.frames.filter((f) => f.z || f.failed).length, bad = st.frames.filter((f) => f.failed).length;
    if (done < st.frames.length) setStatus(`${st.summary} Loading pictures… ${done} of ${st.frames.length}.`);
    else setStatus(`${st.summary}${bad ? ` ${bad} picture${bad > 1 ? "s" : ""} could not be loaded.` : ""}`);
    if (done === st.frames.length) updateFacts();
  }

  function summarise(search, frames) {
    const v = search.visits || [];
    const missing = search.stale ? " (NASA's archive search isn't answering right now, so this list of exposures is one saved earlier; the newest pictures may be missing.)" : "";
    if (search.deep) return "This spot is in one of SPHEREx's two deep fields, which it photographs almost every day — tens of thousands of exposures. Showing an even sample over time." + missing;
    const span = v.length ? `${monthYear(v[0].start)} – ${monthYear(v[v.length - 1].end)}` : "";
    let s = `SPHEREx has photographed this spot ${search.total.toLocaleString()} times in ${v.length} visit${v.length === 1 ? "" : "s"}${span ? ` (${span})` : ""}.`;
    if (v.length === 1) s += " With one visit so far, slow changes can't show yet — but asteroids still move within days.";
    return s + missing;
  }

  function fillBandSelect(search) {
    const sel = $("band"); sel.innerHTML = "";
    for (const b of search.bands) {
      const o = document.createElement("option"); o.value = b.detector; o.disabled = b.count === 0;
      o.textContent = `${b.range_um[0].toFixed(2)}–${b.range_um[1].toFixed(2)} µm` + (b.count == null ? "" : ` · ${b.count} picture${b.count === 1 ? "" : "s"}`);
      sel.appendChild(o);
    }
    sel.value = st.band;
  }

  function resetView(target, opts) {
    st.token++; queue = []; renderCache = new Map(); scaleCache = new Map(); st.knownCache = new Map();
    st.target = target; st.frames = []; st.a = st.b = null; st.phase = 0; st.timeIdx = 0; st.hover = null;
    st.band = +opts.band || 2; st.size = +opts.size || 0.1; st.n = gridSize(st.size);
    st.marks = loadMarks();
    $("viewer").hidden = false; $("size").value = String(st.size);
    $("targetName").textContent = target.name || "Sky position";
    $("targetMeta").textContent = `${fmtSexa(target.ra, target.dec)}   (RA ${target.ra.toFixed(4)}°, Dec ${target.dec >= 0 ? "+" : ""}${target.dec.toFixed(4)}°)` +
      (target.moved_arcsec_since_2000 ? ` — shifted ${target.moved_arcsec_since_2000}″ from its year-2000 catalogue position to allow for its own motion` : "");
    $("strip").innerHTML = ""; $("facts").innerHTML = ""; $("gap").textContent = ""; $("stripCount").textContent = "";
    blank(0); blank(1); $("cap0").innerHTML = ""; $("cap1").innerHTML = ""; $("load0").hidden = false; $("loadText").textContent = "Searching the SPHEREx archive…";
    renderMarks();
    for (const c of document.querySelectorAll(".chip")) c.setAttribute("aria-current", String(!!st.example && c.dataset.slug === st.example.slug));
    return st.token;
  }

  function adoptFrames(frames, opts) {
    st.frames = frames;
    const ids = new Set(frames.map((f) => f.id));
    let [a, b] = choosePair(frames);
    if (opts.a && ids.has(opts.a)) a = opts.a;
    if (opts.b && ids.has(opts.b)) b = opts.b;
    st.a = a; st.b = b;
    $("timeSlider").max = Math.max(0, frames.length - 1);
    st.timeIdx = Math.max(0, frames.findIndex((f) => f.id === a));
    buildStrip(); fillPairSelects(); updateGap(); updateFacts();
    setMode(opts.mode && HINTS[opts.mode] ? opts.mode : st.mode);
  }

  /** Live path: ask the server (which asks IRSA / AWS). */
  async function loadLive(target, opts = {}) {
    st.example = null;
    const token = resetView(target, opts);
    $("story").hidden = true;
    try {
      setStatus("Searching the SPHEREx archive for pictures of this spot…");
      const slow = setTimeout(() => {
        if (token !== st.token) return;
        setStatus("Still searching — NASA's archive is answering slowly right now. This can take up to a minute.");
        $("loadText").textContent = "Still searching — the archive is slow right now…";
      }, 7000);
      let search;
      try { search = await getJson(`${API}/api/search?${new URLSearchParams({ ra: target.ra, dec: target.dec })}`, 240000); }
      finally { clearTimeout(slow); }
      if (token !== st.token) return;
      st.search = search;
      if (!search.total) {
        $("load0").hidden = true; $("viewer").hidden = true;
        setStatus("SPHEREx has no public pictures of this exact spot yet. Try another place, or one of the examples.", true);
        return;
      }
      const want = search.bands.find((b) => b.detector === st.band);
      if (!want || want.count === 0) st.band = search.bands.slice().sort((x, y) => y.count - x.count)[0].detector;
      fillBandSelect(search);
      st.summary = summarise(search);
      setStatus(`${st.summary} Reading dates and colours…`);
      const res = await getJson(`${API}/api/frames?${new URLSearchParams({ ra: target.ra, dec: target.dec, band: st.band })}`, 240000);
      if (token !== st.token) return;
      st.totalInBand = res.total_in_band || res.frames.length;
      if (!res.frames.length) { $("load0").hidden = true; setStatus(`${st.summary} None of them in this colour band — choose another band.`, true); return; }
      const [a0, b0] = choosePair(res.frames);
      adoptFrames(thin(res.frames, [opts.a || a0, opts.b || b0]), opts);
      ensureLoaded([byId(st.a), byId(st.b)]);
      ensureLoaded(st.frames, false);
      progress(); syncUrl();
    } catch (e) {
      if (token !== st.token) return;
      $("load0").hidden = true; setStatus(e.message, true);
    }
  }

  /** Example path: everything (pictures included) comes from one static file, so it works offline from IRSA. */
  async function loadExample(slug, opts = {}) {
    const meta = examples.find((e) => e.slug === slug);
    if (!meta) { setStatus("That example doesn't exist any more.", true); return; }
    setStatus(`Opening “${meta.title}”…`);
    let ex;
    try { ex = await getJson(`examples/${slug}.json`); } catch (e) { setStatus("Couldn't open that example. " + e.message, true); return; }
    st.example = ex;
    const token = resetView(ex.target, { band: ex.band, size: ex.size });
    if (token !== st.token) return;
    st.search = ex.search; st.totalInBand = ex.total_in_band || ex.frames.length;
    fillBandSelect(ex.search);
    st.summary = summarise(ex.search);
    $("story").hidden = !ex.story; $("story").textContent = ex.story || "";
    const frames = ex.frames.map((f) => decodeFrame({ ...f }));
    // an example may ask for particular display settings (e.g. no crosshair in the "spot it" game)
    applySettings({ ...DEFAULTS, known: !!ex.known_default, ...(ex.settings || {}) });
    adoptFrames(frames, { a: opts.a || ex.a, b: opts.b || ex.b, mode: opts.mode || ex.mode });
    setPlaying(true);
    setStatus(st.summary + " (Example saved from the archive, so it opens instantly.)");
    $("load0").hidden = true; $("q").value = ""; syncUrl();
  }

  async function runSearch(text) {
    const q = text.trim(); if (!q) { setStatus("Type a star or galaxy name, or coordinates.", true); return; }
    setStatus(`Looking up “${q}”…`);
    try {
      const t = await api("/api/resolve", { q });
      await loadLive({ ...t, name: t.name || `RA ${t.ra.toFixed(4)}°, Dec ${t.dec >= 0 ? "+" : ""}${t.dec.toFixed(4)}°` }, { band: 2, size: st.size, mode: st.mode });
    } catch (e) { setStatus(e.message, true); }
  }

  /** Changing band or field size always goes to the live archive (examples hold one band and size). */
  function reload(change) {
    if (!st.target) return;
    const opts = { band: st.band, size: st.size, mode: st.mode, ...change };
    if (st.example && +opts.band === st.example.band && +opts.size === st.example.size) { loadExample(st.example.slug, { mode: st.mode }); return; }
    loadLive(st.target, opts);
  }

  /* ------------------------------------------------------------------ marks ("spot a mover") */
  const marksKey = () => st.target ? `blinkx.marks.${st.target.ra.toFixed(3)}_${st.target.dec.toFixed(3)}` : "";
  function loadMarks() { try { return JSON.parse(localStorage.getItem(marksKey()) || "[]"); } catch (_) { return []; } }
  function saveMarks() { try { localStorage.setItem(marksKey(), JSON.stringify(st.marks)); } catch (_) { /* private mode */ } }
  function renderMarks() {
    $("marks").hidden = !st.marks.length && !st.marking;
    $("markList").innerHTML = st.marks.map((m) => `<li>${esc(fmtSexa(m.ra, m.dec))} <span class="muted">— in the picture of ${esc(fmtDate(m.date))}</span></li>`).join("");
  }
  function marksText() {
    const head = `Blink X marks near ${st.target.name || ""} (RA ${st.target.ra.toFixed(5)}, Dec ${st.target.dec.toFixed(5)})`;
    return [head, ...st.marks.map((m, k) => `${k + 1}. RA ${m.ra.toFixed(5)} Dec ${m.dec.toFixed(5)}  seen ${m.date} UTC  frame ${m.frame}`), shareUrl()].join("\n");
  }

  /* ------------------------------------------------------------------ share */
  function shareUrl() {
    const p = new URLSearchParams();
    if (st.example && st.size === st.example.size && st.band === st.example.band) p.set("ex", st.example.slug);
    else if (st.target) {
      p.set("ra", st.target.ra.toFixed(5)); p.set("dec", st.target.dec.toFixed(5));
      if (st.target.name) p.set("name", st.target.name);
      p.set("band", st.band); p.set("size", st.size);
    }
    if (st.target) { p.set("mode", st.mode); if (st.a) p.set("a", st.a); if (st.b) p.set("b", st.b); }
    const qs = p.toString();
    return location.origin + location.pathname + (qs ? "?" + qs : "");
  }
  let urlTimer = null;
  function syncUrl() { clearTimeout(urlTimer); urlTimer = setTimeout(() => { try { history.replaceState(null, "", shareUrl()); } catch (_) { /* file:// */ } }, 250); }

  /* ------------------------------------------------------------------ wiring */
  function paneEvent(pane, ev) {
    const r = $("pane" + pane).getBoundingClientRect();
    return [clamp((ev.clientX - r.left) / r.width, 0, 1) * st.n, clamp((ev.clientY - r.top) / r.height, 0, 1) * st.n];
  }

  function wire() {
    $("searchForm").addEventListener("submit", (e) => { e.preventDefault(); $("q").blur(); runSearch($("q").value); });
    $("helpBtn").addEventListener("click", () => { const x = $("explain"); x.scrollIntoView({ behavior: "smooth", block: "start" }); x.classList.remove("flash"); void x.offsetWidth; x.classList.add("flash"); });
    for (const t of document.querySelectorAll(".tabs button")) t.addEventListener("click", () => setMode(t.dataset.mode));
    $("playBtn").addEventListener("click", () => setPlaying(!st.playing));
    $("speed").addEventListener("input", (e) => { st.speed = +e.target.value; restartTimer(); });
    $("timeSlider").addEventListener("input", (e) => { st.timeIdx = +e.target.value; setPlaying(false); ensureLoaded([st.frames[st.timeIdx]]); draw(); updateFacts(); });
    $("selA").addEventListener("change", (e) => { st.a = e.target.value; scaleCache = new Map(); afterPairChange(); });
    $("selB").addEventListener("change", (e) => { st.b = e.target.value; afterPairChange(); });
    $("swapBtn").addEventListener("click", () => { [st.a, st.b] = [st.b, st.a]; scaleCache = new Map(); afterPairChange(); });
    for (const b of document.querySelectorAll(".arm button")) b.addEventListener("click", () => {
      st.arm = b.dataset.arm; for (const x of document.querySelectorAll(".arm button")) x.setAttribute("aria-pressed", String(x === b));
    });
    $("band").addEventListener("change", (e) => reload({ band: +e.target.value }));
    $("size").addEventListener("change", (e) => reload({ size: +e.target.value }));
    $("hi").addEventListener("input", (e) => { st.hi = +e.target.value; invalidate(); });
    $("lo").addEventListener("input", (e) => { st.lo = +e.target.value; invalidate(); });
    $("cmap").addEventListener("change", (e) => { st.cmap = e.target.value; invalidate(); });
    for (const id of ["match", "cross", "known", "showFilled"]) $(id).addEventListener("change", (e) => { st[id] = e.target.checked; invalidate(id === "match"); });
    $("smooth").addEventListener("change", (e) => { st.smooth = e.target.checked; $("stage").classList.toggle("crisp", !st.smooth); });
    $("resetBtn").addEventListener("click", () => applySettings(DEFAULTS));
    $("shareBtn").addEventListener("click", async () => {
      const url = shareUrl();
      try { await navigator.clipboard.writeText(url); toast("Link copied — anyone who opens it sees this exact view."); }
      catch (_) { window.prompt("Copy this link:", url); }
    });
    $("markBtn").addEventListener("click", () => {
      st.marking = !st.marking; $("markBtn").setAttribute("aria-pressed", String(st.marking)); $("stage").classList.toggle("marking", st.marking);
      renderMarks(); if (st.marking) toast("Tap the picture where something moved.");
    });
    $("copyMarks").addEventListener("click", async () => { try { await navigator.clipboard.writeText(marksText()); toast("Marks copied."); } catch (_) { window.prompt("Copy your marks:", marksText()); } });
    $("clearMarks").addEventListener("click", () => { st.marks = []; saveMarks(); renderMarks(); schedule(); });

    for (const pane of [0, 1]) {
      const el = $("pane" + pane);
      el.addEventListener("pointermove", (ev) => {
        if (!st.target || !st.frames.length) return;
        const [x, y] = paneEvent(pane, ev), [ra, dec] = pixToSky(x - 0.5, y - 0.5), f = shown()[pane];
        let txt = `${fmtSexa(ra, dec)}   (${ra.toFixed(4)}°, ${dec >= 0 ? "+" : ""}${dec.toFixed(4)}°)`;
        if (f && f.z && st.mode !== "diff") {
          const v = f.z[clamp(Math.floor(y), 0, st.n - 1) * st.n + clamp(Math.floor(x), 0, st.n - 1)];
          txt += v === v ? ` · ${(v * f.sigma).toFixed(3)} MJy/sr above the sky (${v.toFixed(0)}× the noise)` : " · no data here";
        }
        $("readout").textContent = txt;
        st.hover = { pane, i: x, j: y }; if (st.mode === "side") drawOverlay(1 - pane, shown()[1 - pane]);
      });
      el.addEventListener("pointerleave", () => { st.hover = null; if (st.mode === "side") schedule(); });
      el.addEventListener("click", (ev) => {
        if (!st.marking || !st.target) return;
        const [x, y] = paneEvent(pane, ev), [ra, dec] = pixToSky(x - 0.5, y - 0.5), f = shown()[pane];
        st.marks.push({ ra, dec, date: f ? (f.date_obs || "").slice(0, 19) : "", frame: f ? f.id : "" });
        saveMarks(); renderMarks(); schedule();
      });
    }

    document.addEventListener("keydown", (e) => {
      if (/^(INPUT|SELECT|TEXTAREA|BUTTON)$/.test(e.target.tagName) || !st.frames.length) return;
      if (e.key === " ") { e.preventDefault(); setPlaying(!st.playing); }
      else if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
        e.preventDefault(); setPlaying(false);
        if (st.mode === "time") st.timeIdx = (st.timeIdx + (e.key === "ArrowRight" ? 1 : st.frames.length - 1)) % st.frames.length;
        else if (st.mode === "blink") st.phase ^= 1;
        ensureLoaded([st.frames[st.timeIdx]]); draw(); updateFacts();
      }
    });
    document.addEventListener("visibilitychange", restartTimer);
  }

  async function boot() {
    wire();
    $("stage").classList.toggle("crisp", !st.smooth);
    // Wake the live server early (free hosting sleeps when idle); examples never need it.
    getJson(`${API}/api/health`, 70000).then(() => { apiOk = true; showApi(); }).catch(() => { apiOk = false; showApi(); });
    setTimeout(() => { if (apiOk === null) showApi(); }, 2500);
    try {
      examples = await getJson("examples/index.json");
      const box = $("exampleList"); box.innerHTML = "";
      for (const ex of examples) {
        const b = document.createElement("button"); b.type = "button"; b.className = "chip"; b.dataset.slug = ex.slug;
        b.innerHTML = `<strong>${esc(ex.title)}</strong><span>${esc(ex.blurb)}</span>`;
        b.addEventListener("click", () => { loadExample(ex.slug); $("viewer").scrollIntoView({ behavior: "smooth", block: "start" }); });
        box.appendChild(b);
      }
    } catch (_) { $("exampleList").innerHTML = '<span class="muted">Examples are unavailable.</span>'; }

    const p = new URLSearchParams(location.search), opts = { band: p.get("band"), size: p.get("size"), a: p.get("a"), b: p.get("b"), mode: p.get("mode") };
    if (p.get("ex") && examples.some((e) => e.slug === p.get("ex"))) loadExample(p.get("ex"), opts);
    else if (p.get("ra") && p.get("dec") && isFinite(+p.get("ra")) && isFinite(+p.get("dec"))) loadLive({ ra: +p.get("ra"), dec: +p.get("dec"), name: p.get("name") || "" }, opts);
    else if (p.get("q")) { $("q").value = p.get("q"); runSearch(p.get("q")); }
    else if (examples.length) loadExample(examples[0].slug);
    else setStatus("Type a place in the sky to begin.");
  }

  function showApi() {
    const el = $("apiState"); el.hidden = false; el.className = "api-state" + (apiOk === true ? " ok" : apiOk === false ? " down" : "");
    el.textContent = apiOk === true ? "Live search of the whole SPHEREx archive is ready."
      : apiOk === false ? "Live search is offline right now — the examples below still work."
      : "Waking up the live search server (it sleeps when nobody is using it)…";
  }

  boot();
})();
