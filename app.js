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
  const COL_NEW = [255, 64, 200], COL_GONE = [52, 214, 112];   // difference view: magenta = new/brighter, green = gone/dimmer
  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const DEFAULTS = { hi: 50, lo: 30, cmap: "gray", match: true, smooth: true, cross: true, known: false, gaia: false, showFilled: false };

  const st = {
    token: 0, target: null, example: null, search: null,
    band: 2, size: 0.1, n: 128, frames: [], a: null, b: null,
    mode: "blink", playing: true, phase: 0, timeIdx: 0, speed: 55, arm: "b",
    marking: false, marks: [], knownCache: new Map(), hover: null,
    split: 0.5, doodles: [], align: {}, checked: null, doodleState: "idle", showDoodles: true, pickedDoodle: null,
    depth: "single", singles: [], stackWait: false, gaiaStars: null, gaiaState: "idle",      // single exposures, or exposures added together per visit / all of them
    ...DEFAULTS,
  };
  // Shared with doodles.js (Sky Doodles, Object Cards, exports): state, helpers and a few hooks.
  const BX = window.BX = { st, hooks: {} };
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
  const fmtWl = (f) => f.stack && f.stack.wl && f.stack.wl[0].toFixed(2) !== f.stack.wl[1].toFixed(2) ? `${f.stack.wl[0].toFixed(2)}–${f.stack.wl[1].toFixed(2)} µm` : f.wavelength_um ? `${f.wavelength_um.toFixed(2)} µm` : "";

  function fmtSexa(ra, dec) {
    const h = ra / 15, hh = Math.floor(h), mm = Math.floor((h - hh) * 60), ss = ((h - hh) * 60 - mm) * 60;
    const sgn = dec < 0 ? "−" : "+", ad = Math.abs(dec), dd = Math.floor(ad), dm = Math.floor((ad - dd) * 60), ds = ((ad - dd) * 60 - dm) * 60;
    const p = (v, n = 2) => String(v).padStart(n, "0");
    return `${p(hh)}h ${p(mm)}m ${p(ss.toFixed(1), 4)}s  ${sgn}${p(dd)}° ${p(dm)}′ ${p(ds.toFixed(0))}″`;
  }
  /** Short sky coordinates for the grid labels on the picture. */
  function fmtRaShort(ra, secs) {
    const h = (((ra % 360) + 360) % 360) / 15, t = Math.round(h * 3600), hh = Math.floor(t / 3600) % 24, mm = Math.floor((t % 3600) / 60), ss = t % 60, p = (v) => String(v).padStart(2, "0");
    return secs ? `${p(hh)}h${p(mm)}m${p(ss)}s` : `${p(hh)}h${p(mm)}m${p(ss)}s`;
  }
  function fmtDecShort(dec, secs) {
    const t = Math.round(Math.abs(dec) * 3600), dd = Math.floor(t / 3600), mm = Math.floor((t % 3600) / 60), ss = t % 60, p = (v) => String(v).padStart(2, "0");
    return `${dec < 0 ? "−" : "+"}${p(dd)}°${p(mm)}′` + (secs || ss ? `${p(ss)}″` : "");
  }
  const stamp = (iso) => iso ? `${iso.slice(0, 10)} ${iso.slice(11, 16)} UTC` : "";
  /** "12–30 May 2025": the days a stack of exposures spans. */
  function spanOf(a, b) {
    const d = (iso) => { const m = /^(\d{4})-(\d\d)-(\d\d)/.exec(iso || ""); return m ? { y: m[1], mo: MONTHS[+m[2] - 1], d: +m[3] } : null; };
    const x = d(a), y = d(b); if (!x || !y) return "";
    if (x.y === y.y && x.mo === y.mo) return x.d === y.d ? `${x.d} ${x.mo} ${x.y}` : `${x.d}–${y.d} ${x.mo} ${x.y}`;
    return x.y === y.y ? `${x.d} ${x.mo} – ${y.d} ${y.mo} ${y.y}` : `${x.d} ${x.mo} ${x.y} – ${y.d} ${y.mo} ${y.y}`;
  }
  /** When a picture was taken: one time for a single exposure, a span of days for exposures added together. */
  const when = (f, short) => !f ? "" : f.stack ? `${f.stack.count === 1 ? "1 exposure" : f.stack.count + (short ? " added" : " exposures added")} · ${spanOf(f.stack.first, f.stack.last)}` : stamp(f.date_obs);
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
    // Best: the brightness of the stars the two exposures share, measured by the change detection (one vote per star).
    const sa = st.align[ref.id], sb = st.align[f.id];
    if (sa && sb && sa.scale && sb.scale && ref.sigma && f.sigma) {
      const k = clamp((f.sigma * sa.scale) / (ref.sigma * sb.scale), 0.2, 5);
      scaleCache.set(key, k);
      return k;
    }
    // Otherwise: the median ratio over pixels that are clearly bright in both pictures, leaving out the middle of the
    // field, so that a target which itself changed brightness is not scaled back to look unchanged.
    const a = ref.z, b = f.z, ratios = [], n = f.n, c = (n - 1) / 2, r2 = Math.pow(3 * 6.15 / (st.size * 3600 / n), 2);
    for (let i = 0; i < a.length; i++) {
      const x = a[i], y = b[i];
      if (x > 15 && y > 15) { const dx = (i % n) - c, dy = ((i / n) | 0) - c; if (dx * dx + dy * dy > r2) ratios.push(x / y); }
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
      const u = mag <= 0 ? 0 : clamp(Math.asinh(mag / softD) * norm, 0, 1), col = dv >= 0 ? COL_NEW : COL_GONE;
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
    for (const id of ["match", "smooth", "cross", "known", "gaia", "showFilled"]) $(id).checked = st[id];
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

  /** Extra x/y shift for a frame whose image coordinates (WCS) disagreed with the star pattern. */
  function shiftOf(f) {
    const a = f && st.align[f.id];
    return a && a.shift_px && (a.shift_px[0] || a.shift_px[1]) ? a.shift_px : null;
  }
  function paint(pane, cv, f) {
    const el = $("cv" + pane);
    if (el.width !== cv.width) { el.width = el.height = cv.width; }
    const ctx = el.getContext("2d"), sh = shiftOf(f); ctx.imageSmoothingEnabled = false;
    if (sh) { ctx.fillStyle = `rgb(${NODATA})`; ctx.fillRect(0, 0, el.width, el.height); ctx.drawImage(cv, -sh[0], -sh[1]); }
    else ctx.drawImage(cv, 0, 0);
  }
  /** Swipe view: A to the left of the divider, B to the right. */
  function paintSwipe(ca, cb, A, B) {
    const el = $("cv0");
    if (el.width !== ca.width) { el.width = el.height = ca.width; }
    const ctx = el.getContext("2d"), n = el.width, x = Math.round(st.split * n), sa = shiftOf(A) || [0, 0], sb = shiftOf(B) || [0, 0];
    ctx.imageSmoothingEnabled = false;
    ctx.fillStyle = `rgb(${NODATA})`; ctx.fillRect(0, 0, n, n);
    ctx.save(); ctx.beginPath(); ctx.rect(0, 0, x, n); ctx.clip(); ctx.drawImage(ca, -sa[0], -sa[1]); ctx.restore();
    ctx.save(); ctx.beginPath(); ctx.rect(x, 0, n - x, n); ctx.clip(); ctx.drawImage(cb, -sb[0], -sb[1]); ctx.restore();
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
    if (st.mode === "swipe") return [st.hover && st.hover.i / st.n < st.split ? A : B];
    return [st.phase ? B : A];
  }

  function draw() {
    if (!st.frames.length || !st.target) return;
    const A = byId(st.a), B = byId(st.b), need = [];
    let cap0 = "", cap1 = "";
    // two pictures from the same day are told apart by their time
    const sameDay = !!(A && B && A !== B && (A.date_obs || "").slice(0, 10) === (B.date_obs || "").slice(0, 10));
    const two = st.mode === "side" || st.mode === "swipe";       // two captions share the width: keep them short
    const label = (f) => f ? `${when(f, two)}  ·  ${fmtWl(f)}` : "";
    if (st.mode === "side") {
      need.push(A, B);
      if (A && A.z) paint(0, frameCanvas(A, 1), A); else blank(0);
      if (B && B.z) paint(1, frameCanvas(B, scaleFor(B, A)), B); else blank(1);
      cap0 = `<span class="tag a">A</span>${esc(label(A))}`; cap1 = `<span class="tag b">B</span>${esc(label(B))}`;
    } else if (st.mode === "diff") {
      need.push(A, B);
      if (A && B && A.z && B.z) paint(0, diffCanvas(A, B)); else blank(0);
      cap0 = `<span class="tag d">B − A</span>${esc(when(B))}  −  ${esc(when(A))}`;
    } else if (st.mode === "time") {
      const f = st.frames[st.timeIdx]; need.push(f);
      if (f && f.z) paint(0, frameCanvas(f, scaleFor(f, A && A.z ? A : null)), f); else blank(0);
      cap0 = `<span class="tag t">${st.timeIdx + 1} / ${st.frames.length}</span>${esc(label(f))}`;
      $("timeOut").textContent = `${st.timeIdx + 1} of ${st.frames.length}`;
      if (+$("timeSlider").value !== st.timeIdx) $("timeSlider").value = st.timeIdx;
    } else if (st.mode === "swipe") {
      need.push(A, B);
      if (A && B && A.z && B.z) paintSwipe(frameCanvas(A, 1), frameCanvas(B, scaleFor(B, A)), A, B); else blank(0);
      cap0 = `<span class="tag a">A</span>${esc(label(A))}<span class="capgap"></span><span class="tag b">B</span>${esc(label(B))}`;
    } else {
      const f = st.phase ? B : A; need.push(A, B);
      if (f && f.z) paint(0, frameCanvas(f, st.phase ? scaleFor(B, A) : 1), f); else blank(0);
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

  /** One overlay unit = 5 CSS pixels on screen, whatever the grid size or the size of the picture. */
  function unit(pane = 0) { const w = $("pane" + pane).clientWidth || $("pane0").clientWidth || 640; return (st.n / w) * 5; }

  function drawOverlay(pane, f) {
    const svg = $("ov" + pane), n = st.n;
    svg.setAttribute("viewBox", `0 0 ${n} ${n}`);
    const u = unit(pane), fs = 2.2 * u, sw = 0.24 * u; let s = "";
    const light = st.cmap === "invert" && st.mode !== "diff", ink = light ? "#111" : "#efe9dd";
    const bone = light ? "#111" : "#efe9dd", faint = light ? "rgba(0,0,0,.22)" : "rgba(239,233,221,.13)", hair = 0.2 * u, lf = 2.2 * u;
    const sizeAs = st.size * 3600, pxPer = n / sizeAs, c = n / 2;
    if (st.cross) {
      // coordinate grid: a line every `step` arcseconds from the centre, with ticks on all four edges
      const step = sizeAs <= 200 ? 30 : sizeAs <= 400 ? 60 : sizeAs <= 800 ? 120 : 300, kmax = Math.floor(sizeAs / 2 / step);
      let grid = "", ticks = "", labels = "";
      for (let k = -kmax; k <= kmax; k++) {
        const q = (c + k * step * pxPer).toFixed(2), tl = (k % 2 === 0 ? 2.4 : 1.4) * u;
        if (k) grid += `<line x1="${q}" y1="0" x2="${q}" y2="${n}"/><line x1="0" y1="${q}" x2="${n}" y2="${q}"/>`;
        ticks += `<line x1="${q}" y1="${n}" x2="${q}" y2="${n - tl}"/><line x1="${q}" y1="0" x2="${q}" y2="${tl}"/><line x1="0" y1="${q}" x2="${tl}" y2="${q}"/><line x1="${n}" y1="${q}" x2="${n - tl}" y2="${q}"/>`;
      }
      // RA along the bottom edge, Dec up the left edge (real sky coordinates of those grid lines)
      const kl = Math.min(2, kmax), secs = step < 60;
      for (const k of [-kl, 0, kl]) {
        const raLabel = k <= 0;                               // the bottom-right corner belongs to the scale bar
        const q = c + k * step * pxPer, [ra] = pixToSky(q - 0.5, c - 0.5), [, dec] = pixToSky(c - 0.5, q - 0.5);
        labels += (raLabel ? `<text x="${q.toFixed(1)}" y="${(n - 3.4 * u).toFixed(1)}" text-anchor="middle" style="font-size:${lf}px">${fmtRaShort(ra, secs)}</text>` : "") +
          `<text x="${(3.4 * u).toFixed(1)}" y="${(q - 1.1 * u).toFixed(1)}" style="font-size:${lf}px">${fmtDecShort(dec, secs)}</text>`;
      }
      const r1 = 4.4 * u, r2 = 7.6 * u, br = 5 * u, e = 1.2 * u;
      const ret = `<circle cx="${c}" cy="${c}" r="${r1}" fill="none"/><line x1="${c - r2}" y1="${c}" x2="${c - r1}" y2="${c}"/><line x1="${c + r1}" y1="${c}" x2="${c + r2}" y2="${c}"/><line x1="${c}" y1="${c - r2}" x2="${c}" y2="${c - r1}"/><line x1="${c}" y1="${c + r1}" x2="${c}" y2="${c + r2}"/>`;
      const brackets = `<path d="M${e} ${e + br}V${e}H${e + br}M${n - e - br} ${e}H${n - e}V${e + br}M${n - e} ${n - e - br}V${n - e}H${n - e - br}M${e + br} ${n - e}H${e}V${n - e - br}" fill="none"/>`;
      s += `<g stroke="${faint}" stroke-width="${hair}">${grid}</g><g stroke="${bone}" stroke-width="${hair * 1.5}" stroke-opacity=".85">${ticks}${brackets}</g>` +
        `<g stroke="${light ? "#fff" : "#000"}" stroke-opacity=".55" stroke-width="${hair * 4.2}">${ret}</g><g stroke="${bone}" stroke-width="${hair * 1.6}">${ret}</g>` +
        `<g fill="${bone}" fill-opacity=".86">${labels}</g>`;
    }
    // scale bar (bottom right, above the RA labels) and compass (top right, under the caption)
    const arcsec = st.size <= 0.05 ? 30 : st.size <= 0.1 ? 60 : st.size <= 0.2 ? 120 : 300, len = arcsec * pxPer, bx = n - 4 * u - len, by = n - 4 * u;
    s += `<g stroke="${bone}" stroke-width="${hair * 2}" fill="${bone}"><path d="M${bx} ${by - 1.2 * u}V${by}H${bx + len}V${by - 1.2 * u}" fill="none"/>` +
      `<text x="${bx + len / 2}" y="${by - 1.8 * u}" text-anchor="middle" stroke="none" style="font-size:${lf}px">${arcsec >= 60 ? arcsec / 60 + "′" : arcsec + "″"}</text></g>`;
    const cx = n - 5 * u, cy = 15 * u, al = 5 * u;
    s += `<g stroke="${bone}" stroke-width="${hair * 1.8}" fill="${bone}" stroke-linecap="square"><path d="M${cx} ${cy - al}V${cy}H${cx - al}" fill="none"/>` +
      `<text x="${cx}" y="${cy - al - 1.1 * u}" text-anchor="middle" stroke="none" style="font-size:${lf}px">N</text>` +
      `<text x="${cx - al - 1.1 * u}" y="${cy + 0.8 * u}" text-anchor="end" stroke="none" style="font-size:${lf}px">E</text></g>`;
    // catalogued solar-system objects at the moment this frame was taken
    if (st.known && f) {
      const objs = knownFor(f);
      if (objs) for (const o of objs) {
        const [i, j] = skyToPix(o.ra, o.dec);
        if (i < 0 || j < 0 || i > n - 1 || j > n - 1) continue;
        const name = o.number ? `(${o.number}) ${o.name}` : o.name;
        s += `<circle cx="${i + 0.5}" cy="${j + 0.5}" r="${5 * u}" fill="none" stroke="#efe9dd" stroke-width="${sw * 1.3}"/>` +
          `<text x="${i + 0.5}" y="${j + 0.5 - 7 * u}" text-anchor="middle" fill="#efe9dd" style="font-size:${fs}px">${esc(name)}</text>`;
      }
    }
    // Gaia stars (ESA), each moved to where its catalogued motion puts it on the date of this picture
    if (st.gaia && f) {
      const stars = gaiaStars();
      if (stars) for (const g of stars) {
        const [ra, dec] = gaiaAt(g, f.mjd), [i, j] = skyToPix(ra, dec);
        if (i < 0 || j < 0 || i > n - 1 || j > n - 1) continue;
        const pm = Math.hypot(g.pmra || 0, g.pmdec || 0) / 1000, fast = pm >= 0.2;          // arcseconds a year
        s += `<circle cx="${(i + 0.5).toFixed(2)}" cy="${(j + 0.5).toFixed(2)}" r="${(fast ? 2.4 : 1.7) * u}" fill="none" stroke="${bone}" stroke-opacity="${fast ? 0.95 : 0.55}" stroke-width="${hair * (fast ? 2 : 1.4)}"${fast ? "" : ` stroke-dasharray="${0.6 * u} ${0.6 * u}"`}/>`;
        if (fast) {                                              // a fast star: a dashed line to where Gaia puts it ten years on
          const [ra2, dec2] = gaiaAt(g, f.mjd + 3652.5), [i2, j2] = skyToPix(ra2, dec2);
          s += `<line x1="${(i + 0.5).toFixed(2)}" y1="${(j + 0.5).toFixed(2)}" x2="${(i2 + 0.5).toFixed(2)}" y2="${(j2 + 0.5).toFixed(2)}" stroke="${bone}" stroke-opacity=".9" stroke-width="${hair * 1.6}" stroke-dasharray="${0.9 * u} ${0.7 * u}"/>` +
            `<text x="${(i + 0.5 + 3.4 * u).toFixed(1)}" y="${(j + 0.5 + 4.6 * u).toFixed(1)}" fill="${bone}" style="font-size:${lf}px">Gaia: ${pm.toFixed(2)}″/yr</text>`;
        }
      }
    }
    st.marks.forEach((m, k) => {
      const [i, j] = skyToPix(m.ra, m.dec), r = 4 * u;
      if (i < 0 || j < 0 || i > n - 1 || j > n - 1) return;
      s += `<rect x="${i + 0.5 - r}" y="${j + 0.5 - r}" width="${2 * r}" height="${2 * r}" fill="none" stroke="#ff5a1f" stroke-width="${sw * 1.4}" transform="rotate(45 ${i + 0.5} ${j + 0.5})"/>` +
        `<text x="${i + 0.5 + r * 1.6}" y="${j + 0.5 + fs / 3}" fill="#ff5a1f" style="font-size:${fs}px">${k + 1}</text>`;
    });
    if (st.hover && st.hover.pane !== pane && st.mode === "side") {
      s += `<circle cx="${st.hover.i}" cy="${st.hover.j}" r="${3.5 * u}" fill="none" stroke="#efe9dd" stroke-width="${sw * 1.3}"/>`;
    }
    if (st.mode === "swipe" && pane === 0) {
      const x = st.split * n;
      s += `<line x1="${x}" y1="0" x2="${x}" y2="${n}" stroke="#ff5a1f" stroke-width="${sw * 1.5}"/>` +
        `<rect x="${x - 2.8 * u}" y="${n / 2 - 4.4 * u}" width="${5.6 * u}" height="${8.8 * u}" fill="#ff5a1f"/>` +
        `<path d="M${x - 0.5 * u} ${n / 2 - 1.5 * u} l${-1.5 * u} ${1.5 * u} l${1.5 * u} ${1.5 * u} M${x + 0.5 * u} ${n / 2 - 1.5 * u} l${1.5 * u} ${1.5 * u} l${-1.5 * u} ${1.5 * u}" fill="none" stroke="#150703" stroke-width="${sw * 2}" stroke-linecap="square" stroke-linejoin="miter"/>`;
    }
    if (BX.hooks.overlay) s += BX.hooks.overlay(pane, f, u, n) || "";
    svg.innerHTML = s;
  }

  /* ------------------------------------------------------------------ Gaia stars (ESA's star-mapping mission) */
  function gaiaStars() {
    if (st.gaiaStars || st.gaiaState !== "idle") return st.gaiaStars;
    if (st.example && st.example.simulated) { st.gaiaStars = []; return st.gaiaStars; }      // a made-up field has no real stars
    if (st.example && st.example.gaia && st.example.size === st.size) { st.gaiaStars = st.example.gaia; return st.gaiaStars; }
    st.gaiaState = "loading"; const token = st.token;
    api("/api/gaia", { ra: st.target.ra, dec: st.target.dec, size: st.size })
      .then((j) => { if (token === st.token) { st.gaiaStars = j.stars || []; st.gaiaState = "done"; schedule(); } })
      .catch(() => { if (token === st.token) { st.gaiaState = "idle"; st.gaia = false; $("gaia").checked = false; toast("The Gaia star catalogue didn't answer just now. Try again in a moment."); } });
    return null;
  }
  /** Where Gaia puts a star on a given date: its catalogue position is for 2016.0, and it lists the yearly motion. */
  function gaiaAt(g, mjd) {
    const yr = (mjd - 57388.0) / 365.25;
    return [g.ra + (g.pmra || 0) * yr / 3.6e6 / Math.cos(rad(g.dec)), g.dec + (g.pmdec || 0) * yr / 3.6e6];
  }
  /** The Gaia star under the pointer, in words. */
  function gaiaNear(x, y, f) {
    if (!st.gaia || !st.gaiaStars || !f) return "";
    let best = null, bd = 2.6 * unit();
    for (const g of st.gaiaStars) { const [ra, dec] = gaiaAt(g, f.mjd), [i, j] = skyToPix(ra, dec), d = Math.hypot(i + 0.5 - x, j + 0.5 - y); if (d < bd) { bd = d; best = g; } }
    if (!best) return "";
    const pm = Math.hypot(best.pmra || 0, best.pmdec || 0) / 1000;
    return ` · Gaia star${best.g != null ? `, G magnitude ${best.g.toFixed(1)}` : ""}` + (best.pmra != null ? `, moving ${pm.toFixed(pm < 0.1 ? 3 : 2)}″ a year` : "") +
      (best.plx > 2 ? `, about ${(3261.6 / best.plx).toFixed(best.plx > 100 ? 1 : 0)} light-years away` : "");
  }

  /* ------------------------------------------------------------------ known objects (SkyBoT) */
  function knownFor(f) {
    if (f.stack) return [];                                      // asteroids are somewhere else in every exposure of a stack
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
        b.title = `${f.stack ? when(f) : fmtDate(f.date_obs)} — ${fmtWl(f)}`;
        const d = /^\d{4}-(\d\d)-(\d\d)T(\d\d):(\d\d)/.exec(f.date_obs || "");
        b.innerHTML = `<canvas width="66" height="66"></canvas><small>${f.stack ? (f.stack.count === 1 ? "1 exposure" : `${f.stack.count} added`) : d ? `${+d[2]} ${MONTHS[+d[1] - 1]} ${d[3]}:${d[4]}` : ""}<br>${esc(fmtWl(f))}</small>`;
        b.addEventListener("click", () => pickFrame(f.id));
        g.appendChild(b);
      }
      strip.appendChild(g);
    }
    const total = st.totalInBand || st.frames.length;
    if (st.frames[0] && st.frames[0].stack) { const used = st.frames.reduce((k, f) => k + f.stack.count, 0); $("stripCount").textContent = `— ${st.frames.length} deep picture${st.frames.length === 1 ? "" : "s"}, made by adding ${used} exposures together`; return; }
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
          const o = document.createElement("option"); o.value = f.id; o.textContent = `${f.stack ? when(f) : fmtDate(f.date_obs)} · ${fmtWl(f)}`; g.appendChild(o);
        }
        sel.appendChild(g);
      }
      sel.value = cur;
    }
  }

  function updateGap() {
    const A = byId(st.a), B = byId(st.b), el = $("gap");
    if (!A || !B) { el.textContent = ""; return; }
    if (A === B) { el.textContent = A.stack && st.frames.length === 1 ? "Every exposure is added into this one deep picture. Choose “Added up per visit” to compare dates." : "A and B are the same picture — choose two different ones to compare."; return; }
    const dt = B.mjd - A.mjd;
    el.textContent = `B was taken ${fmtGap(dt)} ${dt >= 0 ? "after" : "before"} A.`;
    updateColourMatch(A, B);
  }

  /** How close in infrared colour (wavelength) the two pictures are, and the closest partner for A. */
  function bestColourPartner(A) {
    let best = null, score = Infinity;
    for (const f of st.frames) {
      if (f === A || Math.abs(f.mjd - A.mjd) < 10 / 1440) continue;
      const sc = Math.abs(f.wavelength_um - A.wavelength_um) / A.wavelength_um - 6e-5 * Math.abs(f.mjd - A.mjd) + nearEdge(f);
      if (sc < score) { score = sc; best = f; }
    }
    return best;
  }
  function updateColourMatch(A, B) {
    const el = $("colourMatch"); if (!el) return;
    if (!A || !B || A === B || !A.wavelength_um || !B.wavelength_um) { el.hidden = true; return; }
    const rel = Math.abs(A.wavelength_um - B.wavelength_um) / A.wavelength_um, ok = rel < 0.03, best = bestColourPartner(A);
    const better = best && best !== B && Math.abs(best.wavelength_um - A.wavelength_um) / A.wavelength_um < rel * 0.6;
    el.hidden = false; el.className = "colour-match " + (ok ? "ok" : "warn");
    el.querySelector(".cm-text").textContent = ok
      ? `Same infrared colour: A ${A.wavelength_um.toFixed(2)} µm, B ${B.wavelength_um.toFixed(2)} µm.`
      : `Different infrared colours: A ${A.wavelength_um.toFixed(2)} µm, B ${B.wavelength_um.toFixed(2)} µm. Some stars will look brighter or fainter for that reason alone.`;
    $("matchBtn").hidden = !better;
  }

  function factCard(f, cls, title) {
    if (!f) return "";
    if (f.stack) return `<div class="fact ${cls}"><h3>${esc(title)}</h3><dl>` +
      `<dt>Made from</dt><dd>${f.stack.count === 1 ? "1 exposure (the only one in this visit)" : f.stack.count + " exposures added together"} <span class="muted">${f.stack.count >= 3 ? "(the middle value of each pixel, so cosmic-ray hits and passing asteroids drop out)" : f.stack.count === 2 ? "(the average of each pixel)" : ""}</span></dd>` +
      `<dt>Taken</dt><dd>${esc(spanOf(f.stack.first, f.stack.last))} <span class="muted">(first to last DATE-OBS)</span></dd>` +
      `<dt>Colour</dt><dd>${esc(fmtWl(f))} infrared · band ${f.detector}</dd>` +
      (f.stack.count > 1 ? `<dt>Depth</dt><dd>noise about ${f.stack.gain.toFixed(1)}× lower than in one exposure</dd>` : "") + `</dl></div>`;
    return `<div class="fact ${cls}"><h3>${esc(title)}</h3><dl>` +
      `<dt>Taken</dt><dd>${esc(fmtDate(f.date_obs))} <span class="muted">(DATE-OBS in the image file)</span></dd>` +
      `<dt>Colour</dt><dd>${f.wavelength_um ? f.wavelength_um.toFixed(3) + " µm" : "?"} infrared · band ${f.detector}</dd>` +
      `<dt>Exposure</dt><dd>${f.exptime ? f.exptime.toFixed(0) + " s" : "?"} · ${esc(f.collection.replace("spherex_", "SPHEREx ").toUpperCase().replace("SPHEREX", "SPHEREx"))}</dd>` +
      (f.sky !== undefined ? `<dt>Sky glow</dt><dd>${f.sky.toFixed(3)} MJy/sr <span class="muted">(removed)</span></dd>` : "") +
      (f.irsa_url ? `<dt>Source</dt><dd><a href="${esc(f.irsa_url)}" target="_blank" rel="noopener" title="Full NASA/IPAC image file (about 62 MB)">${esc(f.id)} (FITS)</a></dd>`
        : `<dt>Source</dt><dd>Simulated picture, not a NASA file</dd>`) +
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
    swipe: "Drag the white handle: the earlier picture (A) is on its left, the later one (B) on its right.",
    diff: "B minus A. Magenta is new or brighter in B, green is gone or dimmer, and whatever didn't change fades to black.",
    time: "Every exposure of this spot in this colour band, oldest to newest.",
  };

  function setMode(mode) {
    st.mode = mode;
    for (const t of document.querySelectorAll(".tabs button")) t.setAttribute("aria-selected", String(t.dataset.mode === mode));
    $("stage").dataset.mode = mode;
    $("modeHint").textContent = HINTS[mode] + (st.frames[0] && st.frames[0].stack ? " Each picture here is many exposures added together: fainter things show, but anything that moves within a visit is averaged away." : "");
    const anim = mode === "blink" || mode === "time";
    $("playBtn").hidden = !anim; $("speedWrap").hidden = !anim; $("timeWrap").hidden = mode !== "time";
    if (mode === "time") { const i = st.frames.findIndex((f) => f.id === st.a); if (i >= 0 && !st.playing) st.timeIdx = i; }
    if (mode === "swipe") openSwipe();
    restartTimer(); updateFacts(); schedule(); syncUrl();
  }

  const reduceMotion = !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  /** Keep the outgoing picture underneath and fade the new one in over it. */
  function crossfade() {
    if (reduceMotion) return;
    const top = $("cv0"), under = $("cu0"); if (!under) return;
    if (under.width !== top.width) { under.width = under.height = top.width; }
    under.getContext("2d").drawImage(top, 0, 0);
    top.classList.remove("fade"); void top.offsetWidth; top.classList.add("fade");
  }
  function openSwipe() {
    if (reduceMotion) { st.split = 0.5; return; }
    const t0 = performance.now(), from = 0.1;
    const tick = (t) => { if (st.mode !== "swipe") return; const k = Math.min(1, (t - t0) / 650), e = 1 - Math.pow(1 - k, 3); st.split = from + (0.5 - from) * e; draw(); if (k < 1) requestAnimationFrame(tick); };
    requestAnimationFrame(tick);
  }

  function setPlaying(on) {
    st.playing = on; $("playBtn").textContent = on ? "Pause" : "Play"; $("playBtn").setAttribute("aria-pressed", String(on)); restartTimer();
  }
  function restartTimer() {
    clearInterval(timer); timer = null;
    if (!st.playing || document.hidden) return;
    if (st.mode === "blink") timer = setInterval(() => { crossfade(); st.phase ^= 1; draw(); }, clamp(1700 - 15 * st.speed, 180, 1700));
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
    if (done === st.frames.length) {
      updateFacts(); if (!st.example && st.doodleState === "idle" && BX.hooks.framesReady) BX.hooks.framesReady();
      if (st.stackWait) { showFrames({ mode: st.mode }); schedule(); }
    }
  }

  function summarise(search, frames) {
    const v = search.visits || [];
    const missing = search.stale ? " (NASA's archive search isn't answering right now, so this list of exposures is one saved earlier; the newest pictures may be missing.)" : "";
    if (search.deep) return "This spot is in one of SPHEREx's two deep fields, which it photographs almost every day — tens of thousands of exposures. Showing an even sample over time." + missing;
    const span = v.length ? `${monthYear(v[0].start)} – ${monthYear(v[v.length - 1].end)}` : "";
    let s = `SPHEREx has photographed this spot ${search.total.toLocaleString()} times in ${v.length} visit${v.length === 1 ? "" : "s"}${span ? ` (${span})` : ""}.`;
    if (v.length === 1) s += " With one visit so far, slow changes can't show yet — but asteroids still move within days.";
    if (search.saved_on) s += ` (For speed, this list of exposures was saved on ${fmtDate(search.saved_on + "T00:00", false)}; anything SPHEREx released after that is not in it yet.)`;
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
    st.gaiaStars = null; st.gaiaState = "idle";
    st.singles = []; st.stackWait = false; st.depth = opts.depth === "visit" || opts.depth === "all" ? opts.depth : "single"; $("depth").value = st.depth;
    st.band = +opts.band || 2; st.size = +opts.size || 0.1; st.n = gridSize(st.size);
    st.marks = loadMarks();
    st.doodles = []; st.align = {}; st.checked = null; st.expected = []; st.dismissed = []; st.doodleState = "idle"; st.pickedDoodle = null;
    if (BX.hooks.reset) BX.hooks.reset();
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
    st.singles = frames;
    if (frames[0] && frames[0].n) st.n = frames[0].n;            // saved examples carry their own grid size
    showFrames(opts);
  }

  /** Put the single exposures, or the same exposures added together (st.depth), on screen. */
  function showFrames(opts = {}) {
    const singles = st.singles, ready = singles.length > 0 && singles.every((f) => f.z || f.failed);
    let frames = singles; st.stackWait = false;
    if (st.depth !== "single") {
      const have = singles.filter((f) => f.z);
      if (ready && have.length) frames = stacksOf(have);
      else st.stackWait = true;                                  // single exposures stay on screen until every picture has arrived
    }
    st.frames = frames; renderCache = new Map(); scaleCache = new Map();
    const ids = new Set(frames.map((f) => f.id));
    let [a, b] = choosePair(frames);
    if (opts.a && ids.has(opts.a)) a = opts.a;
    if (opts.b && ids.has(opts.b)) b = opts.b;
    st.a = a; st.b = b; st.phase = 0;
    $("timeSlider").max = Math.max(0, frames.length - 1);
    st.timeIdx = Math.max(0, frames.findIndex((f) => f.id === a));
    $("depth").value = st.depth;
    buildStrip(); fillPairSelects(); updateGap(); updateFacts();
    setMode(opts.mode && HINTS[opts.mode] ? opts.mode : st.mode);
  }

  /** Exposures added together: one deep picture per visit, or one for everything in this colour band. */
  function stacksOf(singles) {
    const groups = (st.depth === "all" ? [singles] : visitsOf(singles).map((v) => v.frames)).filter((g) => g.length);
    return groups.map((g, i) => makeStack(g, i));
  }
  /**
   * The middle value (median) of each pixel when there are three or more exposures, so cosmic-ray hits and things
   * that move within the visit drop out; the average for two. Pixel values stay in units of sky noise: the result is
   * scaled up so that its noise is 1 again, which is why faint things rise out of it.
   */
  function makeStack(g, i) {
    const n = g[0].n, len = n * n, m = g.length, z = new Float32Array(len), buf = new Float32Array(m);
    for (let p = 0; p < len; p++) {
      let c = 0;
      for (let k = 0; k < m; k++) { const v = g[k].z[p]; if (v === v) buf[c++] = v; }
      if (!c) { z[p] = NaN; continue; }
      if (c >= 3) { const q = buf.subarray(0, c).sort(); z[p] = (c & 1 ? q[c >> 1] : 0.5 * (q[(c >> 1) - 1] + q[c >> 1])) * Math.sqrt(c) / 1.2533; }
      else { let sum = 0; for (let k = 0; k < c; k++) sum += buf[k]; z[p] = sum / Math.sqrt(c); }
    }
    const wl = g.map((f) => f.wavelength_um).filter(Boolean), mid = g[m >> 1];
    return {
      id: `stack-${st.depth}-${i + 1}`, n, z, loaded: true, detector: mid.detector, band: mid.band, collection: mid.collection,
      date_obs: g[0].date_obs, mjd: g.reduce((t, f) => t + f.mjd, 0) / m, wavelength_um: wl.length ? wl.reduce((t, v) => t + v, 0) / wl.length : null,
      stack: { count: m, ids: g.map((f) => f.id), first: g[0].date_obs, last: g[m - 1].date_obs, wl: wl.length ? [Math.min(...wl), Math.max(...wl)] : null, gain: m >= 3 ? Math.sqrt(m) / 1.2533 : Math.sqrt(m) },
    };
  }
  function setDepth(depth) {
    st.depth = depth === "visit" || depth === "all" ? depth : "single";
    if (st.depth !== "single") ensureLoaded(st.singles, false);
    showFrames({ mode: st.mode });
    if (st.stackWait) toast("The exposures will be added together as soon as all of them have arrived.");
    schedule(); syncUrl();
  }

  /** Live path: ask the server (which asks IRSA / AWS). */
  async function loadLive(target, opts = {}) {
    st.example = null;
    const token = resetView(target, opts);
    $("story").hidden = true; $("stage").classList.remove("simulated");
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
    const token = resetView(ex.target, { band: ex.band, size: ex.size, depth: opts.depth || ex.depth });
    if (token !== st.token) return;
    st.search = ex.search; st.totalInBand = ex.total_in_band || ex.frames.length;
    fillBandSelect(ex.search);
    st.summary = summarise(ex.search);
    $("story").hidden = !ex.story; $("story").textContent = ex.story || ""; $("story").classList.toggle("simulated", !!ex.simulated);
    $("stage").classList.toggle("simulated", !!ex.simulated);
    const frames = ex.frames.map((f) => decodeFrame({ ...f }));
    // an example may ask for particular display settings (e.g. no crosshair in the "spot it" game)
    applySettings({ ...DEFAULTS, known: !!ex.known_default, ...(ex.settings || {}) });
    adoptFrames(frames, { a: opts.a || ex.a, b: opts.b || ex.b, mode: opts.mode || ex.mode });
    setPlaying(true);
    st.doodles = knownFirst(ex.doodles || []); st.align = ex.align || {}; st.checked = ex.checked || null; st.expected = ex.expected || []; st.dismissed = ex.dismissed || []; st.doodleState = "done";
    if (BX.hooks.doodles) BX.hooks.doodles();
    setStatus(st.summary + " (Example saved from the archive, so it opens instantly.)");
    $("load0").hidden = true; $("q").value = ""; syncUrl();
  }

  async function runSearch(text) {
    st.fromCode = null;
    const q = text.trim(); if (!q) { setStatus("Type a star or galaxy name, or coordinates.", true); return; }
    setStatus(`Looking up “${q}”…`);
    try {
      const t = await api("/api/resolve", { q });
      // a typed name that is one of the saved targets opens the saved view: same real pictures, already chosen and checked
      const near = t.kind === "name" && examples.find((e) => !e.simulated && e.ra != null && Math.hypot((e.ra - t.ra) * Math.cos(rad(t.dec)), e.dec - t.dec) * 3600 < 30);
      if (near) { await loadExample(near.slug); $("viewer").scrollIntoView({ behavior: "smooth", block: "start" }); return; }
      await loadLive({ ...t, name: t.name || `RA ${t.ra.toFixed(4)}°, Dec ${t.dec >= 0 ? "+" : ""}${t.dec.toFixed(4)}°` }, { band: 2, size: st.size, mode: st.mode });
    } catch (e) { setStatus(e.message, true); }
  }

  /** Changing band or field size always goes to the live archive (examples hold one band and size). */
  function reload(change) {
    if (!st.target) return;
    if (st.example && st.example.simulated) {            // a made-up field has no other bands or sizes to fetch
      $("band").value = st.band; $("size").value = String(st.size);
      toast("The simulated field exists only in this one view. Pick a real example or search the sky to change these."); return;
    }
    const opts = { band: st.band, size: st.size, mode: st.mode, depth: st.depth, ...change };
    if (st.example && +opts.band === st.example.band && +opts.size === st.example.size) { loadExample(st.example.slug, { mode: st.mode, depth: st.depth }); return; }
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
  /** Doodles that a catalogue could name come first; the rest keep their order. */
  const knownFirst = (list) => list.slice().sort((p, q) => (p.status === "known" ? 0 : 1) - (q.status === "known" ? 0 : 1));

  /** Drop a numbered mark at a sky position (used for "look near here"). */
  function addMark(ra, dec) {
    const f = shown()[0];
    if (!st.marks.some((m) => Math.hypot((m.ra - ra) * Math.cos(rad(dec)), m.dec - dec) * 3600 < 3)) st.marks.push({ ra, dec, date: f ? (f.date_obs || "").slice(0, 19) : "", frame: f ? f.id : "" });
    saveMarks(); renderMarks(); schedule();
  }

  function shareUrl() {
    const p = new URLSearchParams();
    if (st.example && st.size === st.example.size && st.band === st.example.band) p.set("ex", st.example.slug);
    else if (st.target) {
      p.set("ra", st.target.ra.toFixed(5)); p.set("dec", st.target.dec.toFixed(5));
      if (st.target.name) p.set("name", st.target.name);
      p.set("band", st.band); p.set("size", st.size);
    }
    if (st.target) { p.set("mode", st.mode); if (st.depth !== "single") p.set("depth", st.depth); if (st.a) p.set("a", st.a); if (st.b) p.set("b", st.b); }
    const qs = p.toString();
    return location.origin + location.pathname + (qs ? "?" + qs : "");
  }
  let urlTimer = null;
  function syncUrl() { clearTimeout(urlTimer); urlTimer = setTimeout(() => { try { history.replaceState(null, "", shareUrl()); } catch (_) { /* file:// */ } }, 250); }

  /** Download what is on screen as a PNG, with a caption strip saying what, when and from where. */
  function savePicture() {
    if (!st.target || !st.frames.length) return;
    const panes = st.mode === "side" ? [0, 1] : [0], S = 640, pad = 12, capH = 64;
    const out = document.createElement("canvas"); out.width = panes.length * S + (panes.length + 1) * pad; out.height = S + capH + 2 * pad;
    const ctx = out.getContext("2d");
    ctx.fillStyle = "#050506"; ctx.fillRect(0, 0, out.width, out.height);
    ctx.imageSmoothingEnabled = st.smooth;
    panes.forEach((pn, k) => {
      const x = pad + k * (S + pad);
      ctx.drawImage($("cv" + pn), x, pad, S, S);
      ctx.fillStyle = "#fff"; ctx.font = "500 15px 'IBM Plex Mono', monospace"; ctx.shadowColor = "#000"; ctx.shadowBlur = 6;
      ctx.fillText($("cap" + pn).textContent.replace(/^([AB]|B − A|\d+ \/ \d+)/, "$1  "), x + 10, pad + 26);
      ctx.shadowBlur = 0;
    });
    ctx.fillStyle = "#efe9dd"; ctx.font = "500 14px 'IBM Plex Mono', monospace";
    ctx.fillText(`${st.target.name || "Sky position"} — RA ${st.target.ra.toFixed(4)}°, Dec ${st.target.dec >= 0 ? "+" : ""}${st.target.dec.toFixed(4)}°, field ${(st.size * 60).toFixed(0)}′, north up`, pad, S + pad + 26);
    ctx.fillStyle = "#aaa294"; ctx.font = "12px 'IBM Plex Mono', monospace";
    ctx.fillText("NASA SPHEREx Level-2 image(s) via NASA/IPAC IRSA · made with Blink X", pad, S + pad + 48);
    out.toBlob((blob) => {
      if (!blob) return;
      const a = document.createElement("a"); a.href = URL.createObjectURL(blob);
      a.download = `blinkx-${(st.target.name || "sky").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "")}-${st.mode}.png`;
      document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(a.href), 4000);
    }, "image/png");
  }

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
    $("depth").addEventListener("change", (e) => setDepth(e.target.value));
    $("hi").addEventListener("input", (e) => { st.hi = +e.target.value; invalidate(); });
    $("lo").addEventListener("input", (e) => { st.lo = +e.target.value; invalidate(); });
    $("cmap").addEventListener("change", (e) => { st.cmap = e.target.value; invalidate(); });
    for (const id of ["match", "cross", "known", "gaia", "showFilled"]) $(id).addEventListener("change", (e) => { st[id] = e.target.checked; invalidate(id === "match"); });
    $("smooth").addEventListener("change", (e) => { st.smooth = e.target.checked; $("stage").classList.toggle("crisp", !st.smooth); });
    $("resetBtn").addEventListener("click", () => applySettings(DEFAULTS));
    $("shareBtn").addEventListener("click", async () => {
      const url = shareUrl();
      try { await navigator.clipboard.writeText(url); toast("Link copied — anyone who opens it sees this exact view."); }
      catch (_) { window.prompt("Copy this link:", url); }
    });
    $("saveBtn").addEventListener("click", savePicture);
    $("markBtn").addEventListener("click", () => {
      st.marking = !st.marking; $("markBtn").setAttribute("aria-pressed", String(st.marking)); $("stage").classList.toggle("marking", st.marking);
      renderMarks(); if (st.marking) toast("Tap the picture where something moved.");
    });
    $("copyMarks").addEventListener("click", async () => { try { await navigator.clipboard.writeText(marksText()); toast("Marks copied."); } catch (_) { window.prompt("Copy your marks:", marksText()); } });
    $("clearMarks").addEventListener("click", () => { st.marks = []; saveMarks(); renderMarks(); schedule(); });

    let dragging = false;
    $("matchBtn").addEventListener("click", () => {
      const A = byId(st.a), best = A && bestColourPartner(A);
      if (best) { st.b = best.id; afterPairChange(); toast("B switched to the picture closest in colour to A."); }
    });
    for (const pane of [0, 1]) {
      const el = $("pane" + pane);
      el.addEventListener("pointermove", (ev) => {
        if (!st.target || !st.frames.length) return;
        if (dragging && pane === 0 && st.mode === "swipe") { st.split = clamp(paneEvent(0, ev)[0] / st.n, 0.02, 0.98); st.hover = null; draw(); return; }
        const [x, y] = paneEvent(pane, ev), [ra, dec] = pixToSky(x - 0.5, y - 0.5);
        st.hover = { pane, i: x, j: y };
        const f = shown()[pane];
        let txt = `${fmtSexa(ra, dec)}   (${ra.toFixed(4)}°, ${dec >= 0 ? "+" : ""}${dec.toFixed(4)}°)`;
        if (f && f.z && st.mode !== "diff") {
          const v = f.z[clamp(Math.floor(y), 0, st.n - 1) * st.n + clamp(Math.floor(x), 0, st.n - 1)];
          txt += v === v ? ` · ${(v * f.sigma).toFixed(3)} MJy/sr above the sky (${v.toFixed(0)}× the noise)` : " · no data here";
        }
        $("readout").textContent = txt + gaiaNear(x, y, f);
        st.hover = { pane, i: x, j: y }; if (st.mode === "side") drawOverlay(1 - pane, shown()[1 - pane]);
      });
      el.addEventListener("pointerleave", () => { st.hover = null; if (st.mode === "side") schedule(); });
      el.addEventListener("pointerdown", (ev) => {
        if (pane !== 0 || st.mode !== "swipe" || st.marking) return;
        dragging = true; try { el.setPointerCapture(ev.pointerId); } catch (_) { /* older browsers */ }
        st.split = clamp(paneEvent(0, ev)[0] / st.n, 0.02, 0.98); draw();
      });
      el.addEventListener("pointerup", () => { dragging = false; });
      el.addEventListener("pointercancel", () => { dragging = false; });
      el.addEventListener("click", (ev) => {
        if (!st.marking && st.target && BX.hooks.paneClick) { const [x, y] = paneEvent(pane, ev); BX.hooks.paneClick(pane, x - 0.5, y - 0.5); return; }
        if (!st.marking || !st.target) return;
        const [x, y] = paneEvent(pane, ev), [ra, dec] = pixToSky(x - 0.5, y - 0.5), f = shown()[pane];
        st.marks.push({ ra, dec, date: f ? (f.date_obs || "").slice(0, 19) : "", frame: f ? f.id : "" });
        saveMarks(); renderMarks(); schedule();
      });
    }

    document.addEventListener("keydown", (e) => {
      if (/^(INPUT|SELECT|TEXTAREA|BUTTON)$/.test(e.target.tagName) || !st.frames.length) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const key = e.key.toLowerCase(), modeKey = { b: "blink", s: "swipe", d: "diff", t: "time" }[key];
      if (e.key === " ") { e.preventDefault(); setPlaying(!st.playing); }
      else if (modeKey) { e.preventDefault(); setMode(modeKey); toast(`${modeKey === "diff" ? "Difference" : modeKey === "time" ? "Time-lapse" : modeKey[0].toUpperCase() + modeKey.slice(1)} view`, 1200); }
      else if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
        e.preventDefault(); setPlaying(false);
        const step = e.key === "ArrowRight" ? 1 : st.frames.length - 1;
        if (st.mode === "time") { st.timeIdx = (st.timeIdx + step) % st.frames.length; ensureLoaded([st.frames[st.timeIdx]]); draw(); updateFacts(); }
        else {   // change the later epoch (B) to the next / previous exposure
          const i = Math.max(0, st.frames.findIndex((f) => f.id === st.b));
          st.b = st.frames[(i + step) % st.frames.length].id; st.phase = 1; afterPairChange();
        }
      }
    });
    document.addEventListener("visibilitychange", restartTimer);
    let rz = null;
    window.addEventListener("resize", () => { clearTimeout(rz); rz = setTimeout(() => { schedule(); if (BX.renderDoodleLayer) BX.renderDoodleLayer(false); }, 120); });
  }

  async function boot() {
    wire();
    $("stage").classList.toggle("crisp", !st.smooth);
    // Wake the live server early (free hosting sleeps when idle); examples never need it.
    getJson(`${API}/api/health`, 70000).then(() => { apiOk = true; showApi(); }).catch(() => { apiOk = false; showApi(); });
    setTimeout(() => { if (apiOk === null) showApi(); }, 2500);
    try {
      examples = await getJson("examples/index.json");
      const box = $("exampleList"), nasa = $("nasaList"); box.innerHTML = ""; nasa.innerHTML = "";
      for (const ex of examples) {
        const b = document.createElement("button"); b.type = "button"; b.className = "chip"; b.dataset.slug = ex.slug;
        b.innerHTML = `<strong>${esc(ex.title)}</strong><span>${esc(ex.blurb)}</span>`; if (ex.simulated) b.classList.add("simulated");
        b.addEventListener("click", () => { st.fromCode = null; loadExample(ex.slug); $("viewer").scrollIntoView({ behavior: "smooth", block: "start" }); });
        (ex.group === "nasa" ? nasa : box).appendChild(b);
      }
      $("nasaWrap").hidden = !nasa.children.length;
    } catch (_) { $("exampleList").innerHTML = '<span class="muted">Examples are unavailable.</span>'; $("nasaWrap").hidden = true; }

    const p = new URLSearchParams(location.search), opts = { band: p.get("band"), size: p.get("size"), a: p.get("a"), b: p.get("b"), mode: p.get("mode"), depth: p.get("depth") };
    if (p.get("sky") && BX.openSky) BX.openSky(p.get("sky")).then((ok) => { if (!ok && examples.length) loadExample(examples[0].slug); });
    else if (p.get("ex") && examples.some((e) => e.slug === p.get("ex"))) loadExample(p.get("ex"), opts);
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

  Object.assign(BX, {
    $, esc, api, getJson, toast, setStatus, fmtDate, fmtSexa, fmtGap, fmtWl, monthYear, skyToPix, pixToSky, byId, schedule, invalidate,
    unit, setMode, setPlaying, afterPairChange, shareUrl, visitsOf, ensureLoaded, frameCanvas, scaleFor, shown, draw, API, loadExample, loadLive, setDepth, when, addMark, knownFirst,
  });
  boot();
})();
