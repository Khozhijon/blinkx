/* Blink X — Sky Doodles.
 *
 * Every object that changed between SPHEREx pictures is drawn as one of five simple shapes:
 *   ZIGZAG  a very distant solar-system body (jumps back and forth with Earth's orbit)
 *   ARROW   a nearby star or brown dwarf sliding steadily
 *   SPARK   seen during one visit only: an asteroid passing through
 *   TAIL    the same but fuzzy: a comet
 *   PULSE   stays put, changes brightness
 * Length = speed, angle = direction, colour = type, line thickness = brightness.
 * The detection itself happens on the server (backend/detect.py); this file draws and explains.
 */
(() => {
  "use strict";
  const BX = window.BX, { st, $, esc } = BX;
  const clamp = (v, lo, hi) => v < lo ? lo : v > hi ? hi : v;
  const rad = (d) => d * Math.PI / 180;

  // Okabe–Ito colours: distinguishable with the common kinds of colour blindness.
  const TYPES = {
    zigzag: { label: "Zigzag", color: "#F0E442", what: "A very distant world", why: "SPHEREx sees each patch of sky from opposite sides of Earth's orbit, six months apart. Something far beyond Neptune seems to jump back and forth while it slowly drifts. A new one would be a Planet X candidate." },
    arrow: { label: "Arrow", color: "#56B4E9", what: "A nearby star or brown dwarf", why: "It is always there, but slides steadily in one direction from visit to visit. The closest stars do this." },
    spark: { label: "Spark", color: "#E69F00", what: "An asteroid passing through", why: "Seen during one visit only, crossing the stars within hours, then gone." },
    tail: { label: "Comet tail", color: "#2FBF91", what: "A comet", why: "Like a spark, but fuzzy: a cloud of gas and dust, often with a tail." },
    pulse: { label: "Pulse", color: "#CC79A7", what: "A star that changes brightness", why: "It stays in place but gets brighter or dimmer, appears or fades." },
  };
  BX.TYPES = TYPES;

  /* ------------------------------------------------------------------ the glyph */
  function speed01(d) {
    const m = d.motion || {}, lg = (v, lo, hi) => clamp((Math.log10(Math.max(v, lo)) - Math.log10(lo)) / (Math.log10(hi) - Math.log10(lo)), 0, 1);
    if (d.type === "arrow") return lg(m.rate_arcsec_per_year || 0.3, 0.3, 30);
    if (d.type === "zigzag") return lg(m.jump_arcsec || 60, 60, 1800);
    if (m.rate_arcsec_per_hour) return lg(m.rate_arcsec_per_hour, 3, 300);
    return 0.3;
  }
  const weight = (d) => clamp(1.8 + 0.9 * Math.log10(Math.max(d.peak_sigma || 10, 10) / 10), 1.8, 5);
  /** Screen direction of a position angle (north up, east to the LEFT). */
  const dirOf = (pa) => [-Math.sin(rad(pa)), -Math.cos(rad(pa))];
  function head(x, y, ux, uy, len, col, w) {
    const a = Math.atan2(uy, ux), p = (t) => `${(x + len * Math.cos(a + t)).toFixed(1)} ${(y + len * Math.sin(a + t)).toFixed(1)}`;
    return `<path d="M${p(2.55)} L${x.toFixed(1)} ${y.toFixed(1)} L${p(-2.55)}" fill="none" stroke="${col}" stroke-width="${w}" stroke-linecap="round" stroke-linejoin="round"/>`;
  }

  function glyph(d, size = 56) {
    const T = TYPES[d.type] || TYPES.spark, col = T.color, m = d.motion || {}, w = weight(d).toFixed(1), v = speed01(d);
    const [ux, uy] = m.pa_deg == null ? [0.92, -0.38] : dirOf(m.pa_deg), c = 32;
    let g = "";
    if (d.type === "arrow") {
      const L = 9 + 15 * v, x1 = c - ux * L, y1 = c - uy * L, x2 = c + ux * L, y2 = c + uy * L;
      g = `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${col}" stroke-width="${w}" stroke-linecap="round"/>` + head(x2, y2, ux, uy, 9, col, w) +
        `<circle cx="${x1}" cy="${y1}" r="${(+w * 0.9).toFixed(1)}" fill="${col}"/>`;
    } else if (d.type === "zigzag") {
      const L = 10 + 13 * v, px = -uy, py = ux, pts = [];
      for (let k = 0; k <= 4; k++) { const t = -L + (2 * L * k) / 4, o = (k % 2 ? 1 : -1) * 8; pts.push(`${(c + ux * t + px * o).toFixed(1)},${(c + uy * t + py * o).toFixed(1)}`); }
      g = `<polyline points="${pts.join(" ")}" fill="none" stroke="${col}" stroke-width="${w}" stroke-linecap="round" stroke-linejoin="round"/>`;
    } else if (d.type === "tail") {
      const [tx, ty] = d.tail_pa_deg == null ? [-ux, -uy] : dirOf(d.tail_pa_deg), L = 16 + 14 * v, hx = c - tx * L * 0.42, hy = c - ty * L * 0.42;
      for (const a of [-0.42, 0, 0.42]) {
        const ex = hx + (tx * Math.cos(a) - ty * Math.sin(a)) * L, ey = hy + (tx * Math.sin(a) + ty * Math.cos(a)) * L;
        g += `<path d="M${hx.toFixed(1)} ${hy.toFixed(1)} Q${(hx + tx * L * 0.55).toFixed(1)} ${(hy + ty * L * 0.55).toFixed(1)} ${ex.toFixed(1)} ${ey.toFixed(1)}" fill="none" stroke="${col}" stroke-width="${(+w * (a ? 0.6 : 0.9)).toFixed(1)}" stroke-linecap="round" opacity="${a ? 0.7 : 1}"/>`;
      }
      g += `<circle cx="${hx.toFixed(1)}" cy="${hy.toFixed(1)}" r="${(3.5 + +w * 0.6).toFixed(1)}" fill="${col}"/>`;
    } else if (d.type === "pulse") {
      const up = !d.brightness || d.brightness.change !== "dimmed", rs = [6, 13, 20], op = up ? [0.45, 0.75, 1] : [1, 0.75, 0.45];
      rs.forEach((r, k) => { g += `<circle cx="${c}" cy="${c}" r="${r}" fill="none" stroke="${col}" stroke-width="${(+w * (0.55 + 0.2 * (up ? k : 2 - k))).toFixed(1)}" opacity="${op[k]}"/>`; });
      g += `<circle cx="${c}" cy="${c}" r="2.2" fill="${col}"/>`;
    } else {                                   // spark
      const moving = m.pa_deg != null, sx = moving ? c + ux * 7 : c, sy = moving ? c + uy * 7 : c;
      if (moving) { const L = 10 + 14 * v; g += `<line x1="${(sx - ux * L).toFixed(1)}" y1="${(sy - uy * L).toFixed(1)}" x2="${(sx - ux * 8).toFixed(1)}" y2="${(sy - uy * 8).toFixed(1)}" stroke="${col}" stroke-width="${(+w * 0.8).toFixed(1)}" stroke-dasharray="3 3.5" stroke-linecap="round" opacity=".85"/>`; }
      for (let k = 0; k < 8; k++) { const a = (k * Math.PI) / 4, r = k % 2 ? 6 : 12; g += `<line x1="${sx}" y1="${sy}" x2="${(sx + r * Math.cos(a)).toFixed(1)}" y2="${(sy + r * Math.sin(a)).toFixed(1)}" stroke="${col}" stroke-width="${(+w * (k % 2 ? 0.6 : 0.9)).toFixed(1)}" stroke-linecap="round"/>`; }
    }
    return `<svg class="glyph" viewBox="0 0 64 64" width="${size}" height="${size}" role="img" aria-label="${esc(T.label)} doodle">${g}</svg>`;
  }
  BX.glyph = glyph;

  /* ------------------------------------------------------------------ words */
  function summary(d) {
    const m = d.motion || {}, b = d.brightness || {};
    if (d.type === "arrow") return `slides ${m.rate_arcsec_per_year.toFixed(1)}″ a year toward the ${m.direction}`;
    if (d.type === "zigzag") return `jumps ${Math.round(m.jump_arcsec)}″ back and forth between visits`;
    if (m.dist_arcsec) return `moved ${Math.round(m.dist_arcsec)}″ toward the ${m.direction} in ${BX.fmtGap(m.days)}`;
    if (d.type === "pulse" && b.change_pct) return `${b.change} by ${Math.round(b.change_pct)}% between visits`;
    if (d.type === "pulse") return "there in one visit, gone in another";
    return "seen in one group of exposures only";
  }
  function statusChip(d) {
    if (d.status === "known" && d.known) return `<span class="tagchip known" title="Matched in ${esc(d.known.source)}">Known: ${esc(d.known.name)}</span>`;
    if (d.status === "unchecked") return `<span class="tagchip unchecked" title="The catalogue services did not answer">Not checked yet</span>`;
    return `<span class="tagchip candidate" title="Not found in the catalogues we checked. Not a discovery.">Candidate</span>`;
  }

  /* ------------------------------------------------------------------ on the picture */
  const pxOf = (p) => { const [i, j] = BX.skyToPix(p.ra, p.dec); return [i + 0.5, j + 0.5]; };

  /** The doodles as SVG, in picture coordinates. With `animate` they draw themselves in. */
  function doodleSvg(u, n, animate) {
    if (!st.doodles.length) return "";
    let s = "";
    st.doodles.forEach((d, idx) => {
      if (BX.doodleVisible && !BX.doodleVisible(d)) return;
      const col = (TYPES[d.type] || TYPES.spark).color, picked = st.pickedDoodle === d.id, sw = (picked ? 0.6 : 0.36) * u, pts = d.points.map(pxOf);
      if (!pts.some(([x, y]) => x >= 0 && y >= 0 && x <= n && y <= n)) return;
      const t0 = idx * 0.18, an = (cls, delay) => animate ? ` class="${cls}" style="--d:${(t0 + delay).toFixed(2)}s"` : "";
      const [x0, y0] = pts[0], [x1, y1] = pts[pts.length - 1];
      let g = "";
      if (pts.length >= 2 && Math.hypot(x1 - x0, y1 - y0) > 0.5) {
        let [ux, uy] = [x1 - pts[pts.length - 2][0], y1 - pts[pts.length - 2][1]]; const L = Math.hypot(ux, uy) || 1; ux /= L; uy /= L;
        let tx = x1, ty = y1; const line = pts.map((q) => q.map((v) => v.toFixed(1)).join(","));
        if (Math.hypot(x1 - x0, y1 - y0) < 9 * u) { tx = x1 + ux * 9 * u; ty = y1 + uy * 9 * u; line.push(`${tx.toFixed(1)},${ty.toFixed(1)}`); }   // a tiny shift: lengthen so the direction is readable
        g += `<polyline points="${line.join(" ")}" pathLength="1" fill="none" stroke="${col}" stroke-width="${sw}" stroke-linejoin="round" stroke-linecap="round"${an("draw", 0)}/>`;
        g += `<g${an("pop", 1.0)}>${head(tx, ty, ux, uy, 2.6 * u, col, sw)}</g>`;
        const few = pts.length <= 6;
        pts.forEach(([x, y], k) => { g += `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${(few ? 2.6 : 0.8) * u}" fill="${few ? "none" : col}" stroke="${col}" stroke-width="${sw * 0.9}"${an("pop", 0.15 + (0.8 * k) / Math.max(1, pts.length - 1))}/>`; });
      } else {
        (d.type === "pulse" ? [3, 5.2, 7.4] : [3.4]).forEach((r, k) => { g += `<circle cx="${x0.toFixed(1)}" cy="${y0.toFixed(1)}" r="${r * u}" pathLength="1" fill="none" stroke="${col}" stroke-width="${sw}" opacity="${1 - k * 0.28}"${an("draw", k * 0.22)}/>`; });
      }
      const lx = clamp(x0 + 3.6 * u, 2 * u, n - 16 * u), ly = clamp(y0 - 3.6 * u, 8 * u, n - 6 * u);
      g += `<text x="${lx.toFixed(1)}" y="${ly.toFixed(1)}" fill="${col}" style="font-size:${2.3 * u}px;--d:${(t0 + 0.5).toFixed(2)}s"${animate ? ' class="pop"' : ""}>${esc(d.id)}</text>`;
      s += `<g data-id="${esc(d.id)}">${g}</g>`;
    });
    return s;
  }
  BX.doodleSvg = doodleSvg;

  /** Own layer above the picture, redrawn only when the doodles change, so the draw-in plays once. */
  function renderDoodleLayer(animate) {
    const n = st.n, u = BX.unit(0), html = st.showDoodles ? doodleSvg(u, n, animate) : "";
    for (const id of ["dl0", "dl1"]) { const el = $(id); if (!el) continue; el.setAttribute("viewBox", `0 0 ${n} ${n}`); el.innerHTML = html; }
  }
  BX.renderDoodleLayer = renderDoodleLayer;

  /** A click on the picture opens the card of the doodle under it, if any. */
  BX.hooks.paneClick = (pane, x, y) => {
    if (!st.showDoodles || !st.doodles.length) return;
    const u = BX.unit(pane); let best = null, bd = 5 * u;
    for (const d of st.doodles) {
      const pts = d.points.map(pxOf);
      for (let k = 0; k < pts.length; k++) {
        let dist = Math.hypot(pts[k][0] - x - 0.5, pts[k][1] - y - 0.5);
        if (k) {                                                   // distance to the segment between sightings
          const [ax, ay] = pts[k - 1], [bx, by] = pts[k], L2 = (bx - ax) ** 2 + (by - ay) ** 2 || 1;
          const t = clamp(((x + 0.5 - ax) * (bx - ax) + (y + 0.5 - ay) * (by - ay)) / L2, 0, 1);
          dist = Math.min(dist, Math.hypot(ax + t * (bx - ax) - x - 0.5, ay + t * (by - ay) - y - 0.5));
        }
        if (dist < bd) { bd = dist; best = d; }
      }
    }
    if (best) openCard(best.id);
  };

  /* ------------------------------------------------------------------ the list under the picture */
  function renderBoard() {
    const list = $("doodleList"), status = $("doodleStatus"), n = st.doodles.length;
    $("doodleCount").textContent = st.doodleState === "done" ? `(${n})` : "";
    if (st.doodleState === "loading") status.innerHTML = '<span class="spinner small"></span> Looking for anything that moved or changed brightness…';
    else if (st.doodleState === "error") status.textContent = `The automatic search could not run just now (${st.doodleError || "no answer"}). You can still blink the pictures yourself.`;
    else if (st.doodleState === "idle") status.textContent = st.frames.length ? "The automatic search starts when all pictures have arrived." : "";
    else if (!n) status.textContent = "No doodles here: nothing moved or changed brightness enough to stand out in these exposures. Try the examples, a wider field or another colour band.";
    else {
      const known = st.doodles.filter((d) => d.status === "known").length;
      status.textContent = `${n} thing${n === 1 ? "" : "s"} changed in this patch of sky. ${known === n ? "All already known to astronomers." : `${n - known} not matched to a catalogue: candidate${n - known === 1 ? "" : "s"} only, never a discovery claim.`} Tap one to read its card.`;
    }
    const visible = st.doodles.filter((d) => !BX.doodleVisible || BX.doodleVisible(d));
    list.innerHTML = visible.map((d) => `<button type="button" class="doodle${st.pickedDoodle === d.id ? " picked" : ""}" data-id="${esc(d.id)}">` +
      `<span class="g">${glyph(d, 54)}</span><span class="t"><strong>${esc(d.id)} · ${esc(d.nickname)}</strong>` +
      `<span>${esc((TYPES[d.type] || {}).label || d.type)}: ${esc(summary(d))}</span></span>${statusChip(d)}</button>`).join("");
    for (const b of list.querySelectorAll(".doodle")) b.addEventListener("click", () => openCard(b.dataset.id));
    // honesty cuts both ways: a catalogued fast mover that should be here and that no doodle explains
    const miss = $("doodleExpected"), exp = st.doodleState === "done" ? (st.expected || []) : [];
    miss.hidden = !exp.length;
    if (exp.length) {
      const cool = st.band < 5 && exp.some((e) => /brown dwarf/.test(e.kind));
      const deep = cool ? ` Cool objects show best at 3.8–5.0 µm: <button type="button" class="linklike" id="tryCool">switch to the 3.8–4.4 µm band with the exposures added up</button>.` : "";
      miss.innerHTML = `<strong>Not found here, but catalogued:</strong> ` + exp.map((e) => `${esc(e.name)}, a ${esc(e.kind)} that ${esc(e.source)} lists as moving ${e.pm_arcsec_per_year.toFixed(2)}″ a year`).join("; ") +
        `. ${exp.length === 1 ? "It" : "They"} may be too faint or too red in this colour band, or there may be too little time between these pictures.${deep} ` +
        (cool ? "Then" : st.depth === "single" ? `Try <button type="button" class="linklike" id="tryDeep">adding the exposures up per visit</button> and` : "Try another colour band and") + ` look near ` +
        exp.map((e) => `<button type="button" class="linklike" data-ra="${e.ra}" data-dec="${e.dec}" data-name="${esc(e.name)}">${esc(BX.fmtSexa(e.ra, e.dec))}</button>`).join(", ") + ".";
      const t = $("tryDeep"); if (t) t.addEventListener("click", () => BX.setDepth("visit"));
      const tc = $("tryCool"); if (tc) tc.addEventListener("click", () => { st.depth = "visit"; BX.reload({ band: 5, depth: "visit" }); $("viewer").scrollIntoView({ behavior: "smooth", block: "start" }); });
      for (const b of miss.querySelectorAll("[data-ra]")) b.addEventListener("click", () => { if (BX.addMark) BX.addMark(+b.dataset.ra, +b.dataset.dec); $("stage").scrollIntoView({ behavior: "smooth", block: "center" }); });
    }
    // apparent drifts that an older survey rules out: shown, so nobody wonders what the search looked at and dropped
    const gone = $("doodleDismissed"), dis = st.doodleState === "done" ? (st.dismissed || []) : [];
    gone.hidden = !dis.length;
    if (dis.length) gone.innerHTML = `<strong>Checked and set aside:</strong> ` + dis.map((x) => `an apparent drift of ${x.claimed_rate.toFixed(1)}″ a year near ${esc(BX.fmtSexa(x.ra, x.dec))}. ${x.survey === "WISE" ? "NASA's WISE telescope" : "ESA's Gaia"} already saw a source on that very spot in ${x.year}, so nothing travelled there since`).join("; ") + ".";
    // how the exposures were lined up, and by how much the star pattern disagreed
    const al = Object.values(st.align || {}), note = $("alignNote");
    note.hidden = !al.length;
    if (al.length) {
      const checked = al.filter((a) => a.stars >= 4), moved = al.filter((a) => a.method === "wcs+stars"), worst = Math.max(0, ...checked.map((a) => a.offset_arcsec));
      note.querySelector(".an-text").textContent = !checked.length
        ? "Lined up with the sky coordinates stored in each image file (WCS). Too few stars here for a second check on the star pattern."
        : moved.length
          ? `Lined up with each file's sky coordinates (WCS). ${moved.length} exposure${moved.length === 1 ? " was" : "s were"} off and shifted by up to ${worst.toFixed(1)}″ to match the star pattern.`
          : `Lined up with each file's sky coordinates (WCS) and checked on ${((lo, hi) => lo === hi ? lo : `${lo}–${hi}`)(Math.min(...checked.map((a) => a.stars)), Math.max(...checked.map((a) => a.stars)))} stars per exposure: largest leftover shift ${worst.toFixed(1)}″ (a SPHEREx pixel is 6.2″).`;
    }
    if (BX.hooks.boardExtra) BX.hooks.boardExtra();
    renderDoodleLayer(false);
  }
  BX.renderBoard = renderBoard;
  BX.hooks.reset = () => renderBoard();
  BX.hooks.doodles = () => { renderBoard(); renderDoodleLayer(true); };

  /** Live searches: ask the server to analyse the exposures that are on screen. */
  BX.hooks.framesReady = async () => {
    const ok = (st.singles.length ? st.singles : st.frames).filter((f) => f.z && !f.stack), token = st.token;   // always the single exposures
    if (ok.length < 2) { st.doodleState = "done"; renderBoard(); return; }
    let ids = ok.map((f) => f.id);
    if (ids.length > 48) { const keep = new Set([st.a, st.b].filter((i) => ids.includes(i))), stepSize = ids.length / (48 - keep.size); for (let x = 0; x < ids.length && keep.size < 48; x += stepSize) keep.add(ids[Math.floor(x)]); ids = ids.filter((i) => keep.has(i)); }
    st.doodleState = "loading"; renderBoard();
    try {
      const q = new URLSearchParams({ ra: st.target.ra, dec: st.target.dec, size: st.size, ids: ids.join(",") });
      const res = await BX.getJson(`${BX.API}/api/doodles?${q}`, 240000);
      if (token !== st.token) return;
      st.doodles = BX.knownFirst(res.doodles || []); st.align = res.align || {}; st.checked = res.checked || null; st.expected = res.expected || []; st.dismissed = res.dismissed || []; st.doodleState = "done"; BX.invalidate(true);   // the stars' brightness scale has arrived
    } catch (e) { if (token !== st.token) return; st.doodleState = "error"; st.doodleError = e.message; }
    renderBoard(); renderDoodleLayer(true); BX.invalidate();
  };

  /* ------------------------------------------------------------------ Object Card */
  const fmtNum = (v, n = 1) => v == null ? "?" : Number(v).toFixed(n);
  /* ------------------------------------------------------------------ spectrum: brightness at each wavelength */
  // where well-known gases glow (µm); drawn as marks when they fall inside the plotted range
  const SPEC_MARKS = [[1.083, "He"], [1.282, "H"], [1.875, "H"], [2.166, "H"], [2.66, "H₂O"], [3.29, "PAH"], [4.05, "H"], [4.26, "CO₂"], [4.67, "CO"]];
  const niceCeil = (v) => { const p = Math.pow(10, Math.floor(Math.log10(v))), m = v / p; return [1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10].find((q) => m <= q) * p; };
  function spectrumBlock(d, color) {
    const sp = d.spectrum; if (!sp || !sp.points || sp.points.length < 2) return "";
    const pts = sp.points, narrow = window.innerWidth < 720, W = narrow ? 340 : 560, H = narrow ? 204 : 214, L = 46, R = 12, T0 = 24, B = 52;
    let w0 = pts[0].wl, w1 = pts[pts.length - 1].wl; const pad = Math.max(0.012, (w1 - w0) * 0.06); w0 -= pad; w1 += pad;
    const big = sp.binned ? Math.max(...sp.binned.map((b) => b[1] + b[2])) * 1.9 : Math.max(...pts.map((q) => q.mjy)), inJy = big >= 1000, k = inJy ? 0.001 : 1, top = niceCeil(big * k * 1.05), unit = inJy ? "Jy" : "mJy";
    const X = (w) => L + (w - w0) / (w1 - w0) * (W - L - R), Y = (v) => T0 + (1 - v / top) * (H - T0 - B), f1 = (v) => v.toFixed(1);
    const yv = (v) => (v >= 100 ? v.toFixed(0) : v >= 10 ? String(+v.toFixed(1)) : String(+v.toPrecision(2)));
    let g = "";
    for (const v of [0, top / 2, top]) g += `<line class="${v ? "grid" : "ax"}" x1="${L}" x2="${W - R}" y1="${f1(Y(v))}" y2="${f1(Y(v))}"/><text x="${L - 6}" y="${f1(Y(v) + 3.5)}" text-anchor="end">${yv(v)}</text>`;
    g += `<line class="ax" x1="${L}" x2="${L}" y1="${T0}" y2="${H - B}"/><text x="${L - 6}" y="${T0 - 11}" text-anchor="end">${unit}</text>`;
    const step = [0.02, 0.05, 0.1, 0.2, 0.5, 1].find((q) => (w1 - w0) / q <= (narrow ? 5 : 7)) || 1;
    for (let w = Math.ceil(w0 / step) * step; w <= w1 + 1e-9; w += step) g += `<line class="ax" x1="${f1(X(w))}" x2="${f1(X(w))}" y1="${H - B}" y2="${H - B + 4}"/><text x="${f1(X(w))}" y="${H - B + 16}" text-anchor="middle">${w.toFixed(step < 0.1 ? 2 : 1)}</text>`;
    g += `<text x="${L - 6}" y="${H - B + 16}" text-anchor="end">µm</text>`;
    for (const [w, name] of SPEC_MARKS) if (w > w0 && w < w1) g += `<line class="mark" x1="${f1(X(w))}" x2="${f1(X(w))}" y1="${T0}" y2="${H - B}"/><text class="mark-t" x="${f1(X(w) + 4)}" y="${T0 + 9}">${name} ${w}</text>`;
    // one value per wavelength for the line; every single exposure as a dot
    const bins = []; for (const q of pts) { const last = bins[bins.length - 1]; if (last && q.wl - last.w[last.w.length - 1] < 0.006) { last.w.push(q.wl); last.f.push(q.mjy); } else bins.push({ w: [q.wl], f: [q.mjy] }); }
    const med = (a) => { const b = a.slice().sort((x, y) => x - y), m = b.length >> 1; return b.length % 2 ? b[m] : (b[m - 1] + b[m]) / 2; };
    if (sp.binned && sp.binned.length > 1) {           // a faint object: the line joins the middle value of groups of exposures, with its uncertainty
      g += `<polyline class="line strong" points="${sp.binned.map((b) => `${f1(X(b[0]))},${f1(Y(Math.min(top, b[1] * k)))}`).join(" ")}"/>`;
      for (const b of sp.binned) g += `<line class="err" x1="${f1(X(b[0]))}" x2="${f1(X(b[0]))}" y1="${f1(Y(Math.min(top, (b[1] + b[2]) * k)))}" y2="${f1(Y(Math.max(0, (b[1] - b[2]) * k)))}"/><rect class="bin" x="${f1(X(b[0]) - 3.5)}" y="${f1(Y(Math.min(top, b[1] * k)) - 3.5)}" width="7" height="7"><title>${b[0].toFixed(2)} µm · ${yv(b[1] * k)} ± ${yv(b[2] * k)} ${unit} (middle value of a group of exposures)</title></rect>`;
    } else g += `<polyline class="line" points="${bins.map((b) => `${f1(X(med(b.w)))},${f1(Y(med(b.f) * k))}`).join(" ")}"/>`;
    for (const q of pts) if (q.mjy * k <= top) g += `<circle class="pt${sp.binned ? " dim" : ""}" cx="${f1(X(q.wl))}" cy="${f1(Y(q.mjy * k))}" r="${sp.binned ? 2 : narrow ? 2.6 : 3}"><title>${q.wl.toFixed(3)} µm · ${yv(q.mjy * k)} ${unit}</title></circle>`;
    // where this slice sits in everything SPHEREx measures (0.75 to 5.0 µm)
    const LX = (w) => L + (w - 0.75) / 4.25 * (W - L - R), ly = H - 9;
    g += `<line class="loc" x1="${L}" x2="${W - R}" y1="${ly}" y2="${ly}"/><line class="loc-on" x1="${f1(LX(Math.max(0.75, pts[0].wl)))}" x2="${f1(Math.max(LX(Math.min(5, pts[pts.length - 1].wl)), LX(Math.max(0.75, pts[0].wl)) + 3))}" y1="${ly}" y2="${ly}"/>` +
      `<text x="${L - 6}" y="${ly + 3.5}" text-anchor="end">0.75</text><text x="${L}" y="${ly - 7}">${narrow ? "this slice of SPHEREx's 0.75 – 5.0 µm" : "this slice, out of all 102 SPHEREx colours (0.75 – 5.0 µm)"}</text>`;
    const rows = pts.map((q) => `<tr><td>${q.wl.toFixed(3)}</td><td>${q.mjy}</td><td>${esc(q.frame)}</td></tr>`).join("");
    return { html: `<section class="spectrum" style="--c:${color}"><h3>This colour band · every exposure</h3>` +
      `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Brightness of this object at ${pts.length} wavelengths between ${pts[0].wl.toFixed(2)} and ${pts[pts.length - 1].wl.toFixed(2)} micrometres">${g}</svg>` +
      `<p class="spec-hint">${esc(sp.hint || "")}</p>` +
      `<p class="muted">${d.simulated ? "Simulated object: these brightness values are made up. " : ""}Every SPHEREx exposure sees a spot of sky in one infrared colour, so each dot is one exposure. ` +
      `Brightness is in ${inJy ? "janskys" : "millijanskys"}, the unit astronomers use, measured in a small circle (${sp.aperture_arcsec}″ radius) and approximate: very bright objects overload the detector and read too low.</p></section>`,
      table: `<div class="scroll"><table><thead><tr><th>λ µm</th><th>flux mJy (approx.)</th><th>exposure</th></tr></thead><tbody>${rows}</tbody></table></div>` };
  }

  /* ------------------------------------------------------------------ full spectrum: all six colour bands of one visit */
  const FULL_MARKS = [[1.4, "H₂O"], [1.9, "H₂O"], [3.3, "CH₄"], [4.26, "CO₂"]];
  function fullSpectrumSvg(sp, color) {
    const pts = sp.points || [], narrow = window.innerWidth < 720, W = narrow ? 340 : 560, H = narrow ? 214 : 232, L = 46, R = 12, T0 = 30, B = 30;
    const w0 = 0.7, w1 = 5.05, line = sp.line || [];
    const ref = line.length ? line.map((p) => p[1]) : pts.map((p) => p.mjy), sorted = ref.slice().sort((a, b) => a - b);
    const big = Math.max(sorted[Math.max(0, Math.floor(sorted.length * 0.98) - 1)] || 1, ...pts.filter((p) => !p.ours).map((p) => p.mjy * 0.9), 1e-6);
    const inJy = big >= 1000, k = inJy ? 0.001 : 1, top = niceCeil(big * k * 1.1), unit = inJy ? "Jy" : "mJy";
    const X = (w) => L + (w - w0) / (w1 - w0) * (W - L - R), Y = (v) => T0 + (1 - Math.max(0, Math.min(top, v)) / top) * (H - T0 - B), f1 = (v) => v.toFixed(1);
    const yv = (v) => (v >= 100 ? v.toFixed(0) : v >= 10 ? String(+v.toFixed(1)) : String(+v.toPrecision(2)));
    let g = "";
    for (const v of [0, top / 2, top]) g += `<line class="${v ? "grid" : "ax"}" x1="${L}" x2="${W - R}" y1="${f1(Y(v))}" y2="${f1(Y(v))}"/><text x="${L - 6}" y="${f1(Y(v) + 3.5)}" text-anchor="end">${yv(v)}</text>`;
    g += `<line class="ax" x1="${L}" x2="${L}" y1="${T0}" y2="${H - B}"/><text x="${L - 6}" y="${T0 - 17}" text-anchor="end">${unit}</text><text x="${L - 6}" y="${H - B + 16}" text-anchor="end">µm</text>`;
    for (let w = 1; w <= 5; w += narrow ? 1 : 0.5) g += `<line class="ax" x1="${f1(X(w))}" x2="${f1(X(w))}" y1="${H - B}" y2="${H - B + 4}"/><text x="${f1(X(w))}" y="${H - B + 16}" text-anchor="middle">${w.toFixed(1)}</text>`;
    // the six colour bands: a bracket over each, filled where the object itself is seen
    for (const b of sp.bands || []) {
      const a = X(b.range_um[0]), z = X(b.range_um[1]);
      g += `<line class="${b.on_spot ? "loc-on" : "loc"}" x1="${f1(a)}" x2="${f1(z)}" y1="${T0 - 6}" y2="${T0 - 6}"/><text class="${b.on_spot ? "band-on" : ""}" x="${f1((a + z) / 2)}" y="${T0 - 11}" text-anchor="middle">${b.band}</text>`;
    }
    for (const [w, name] of FULL_MARKS) g += `<line class="mark" x1="${f1(X(w))}" x2="${f1(X(w))}" y1="${T0}" y2="${H - B}"/><text class="mark-t" x="${f1(X(w) + 3)}" y="${T0 + 9}">${name}</text>`;
    for (const p of pts) if (!p.ours) g += `<circle class="pt other" cx="${f1(X(p.wl))}" cy="${f1(Y(p.mjy * k))}" r="2"><title>${p.wl.toFixed(2)} µm · ${yv(Math.max(0, p.mjy) * k)} ${unit} · not the object itself</title></circle>`;
    let seg = [];                                  // the line stops wherever the object is not seen
    const flush = () => { if (seg.length > 1) g += `<polyline class="line strong" points="${seg.join(" ")}"/>`; seg = []; };
    line.forEach((p, i) => { if (i && p[0] - line[i - 1][0] > 0.45) flush(); seg.push(`${f1(X(p[0]))},${f1(Y(p[1] * k))}`); });
    flush();
    const dim = line.length && line.length < pts.filter((p) => p.ours).length;
    for (const p of pts) if (p.ours && p.mjy * k <= top * 1.02) g += `<circle class="pt${dim ? " dim" : ""}" cx="${f1(X(p.wl))}" cy="${f1(Y(p.mjy * k))}" r="${dim ? 2 : 2.2}"><title>${p.wl.toFixed(2)} µm · ${yv(Math.max(0, p.mjy) * k)} ${unit}</title></circle>`;
    return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Brightness of this object from 0.75 to 5 micrometres, ${pts.length} measurements">${g}</svg>`;
  }
  const FULL_HEAD = `Full spectrum · 0.75 to 5 <span class="asis">µm</span>, all six colour bands`;
  const WAITING = `<p class="spec-hint" id="fullSpecWait"><span class="spinner small"></span>Measuring… Blink X is reading about a hundred exposures from NASA's archive. Allow up to a minute.</p>`;
  /** A measured spectrum: the chart, a plain reading of it, how it was made, and the numbers to take away. */
  function fullSpecBody(sp, color, changes) {
    if (!sp.points || !sp.points.length) return `<p class="spec-hint">${esc(sp.hint || "No spectrum could be measured here.")}</p>`;
    const anyOther = sp.points.some((p) => !p.ours);
    const steps = changes ? " This star changes brightness, and the colour bands were photographed on different days of the visit: a step from one band to the next can be a change in time, not in colour." : "";
    return fullSpectrumSvg(sp, color) + `<p class="spec-hint">${esc((sp.hint || "") + steps)}</p>` +
      `<p class="muted">Each dot is one exposure. The numbered bars on top are SPHEREx's six colour bands${anyOther ? ": bright where the object itself is seen. Hollow dots are light that is not its own" : ""}. ` +
      `${sp.visit ? `${sp.visit.exposures} exposures, ${esc(sp.visit.first)} to ${esc(sp.visit.last)}. ` : ""}Brightness in a small circle (${sp.aperture_arcsec || 9.2}″ radius), approximate. ` +
      `${changes ? "" : "The bands are photographed on different days of the visit, so a small step between two of them can be a change in time. "}The dashed marks show where water, methane and carbon dioxide act.</p>` +
      `<div class="actions"><button class="btn ghost" type="button" id="fullSpecCsv">Save these numbers (CSV)</button></div>`;
  }
  function spectrumCsv(sp, what) {
    const pos = sp.position || {};
    return [`# Blink X: SPHEREx spectrum of ${what}`,
      `# position RA ${pos.ra != null ? pos.ra : ""} Dec ${pos.dec != null ? pos.dec : ""} (degrees, ICRS)`,
      `# one visit: ${sp.visit ? sp.visit.first + " to " + sp.visit.last : ""}; brightness summed in a circle of ${sp.aperture_arcsec || 9.2} arcsec radius, no aperture correction`,
      `# on_object = 0: nothing sits on the spot in that colour band, so the value is sky or a neighbour's light`,
      "wavelength_um,brightness_mJy,noise_mJy,band,exposure,on_object",
      ...sp.points.map((p) => [p.wl, p.mjy, p.err, p.band, p.frame, p.ours ? 1 : 0].join(","))].join("\n");
  }
  function wireFullSpec(sp, what) {
    const btn = $("fullSpecCsv"); if (!btn || !sp) return;
    btn.addEventListener("click", () => {
      const a = document.createElement("a"), name = String(what).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "spot";
      a.href = URL.createObjectURL(new Blob([spectrumCsv(sp, what)], { type: "text/csv" })); a.download = `blinkx-spectrum-${name}.csv`;
      document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(a.href), 4000);
    });
  }
  const nameOf = (d) => (d.known && d.known.name) || d.id;
  const measuring = new WeakSet();                 // doodles whose full spectrum is on its way (kept off the doodle itself: doodles are exported as they are)
  function fullSpectrumBlock(d, color) {
    const sp = d.full_spectrum, can = (d.type === "arrow" || d.type === "pulse") && !d.simulated && !(st.example && st.example.simulated);
    if (!sp && !can) return "";
    const head = `<section class="spectrum fullspec" id="fullSpec" style="--c:${color}"><h3>${FULL_HEAD}</h3>`;
    if (measuring.has(d)) return head + WAITING + `</section>`;
    if (!sp) return head + `<p class="spec-hint">The chart further down shows one colour band. SPHEREx photographs the same spot in five more.</p>` +
      `<div class="actions"><button class="btn" type="button" id="fullSpecBtn">Measure the full spectrum</button></div><p class="muted" id="fullSpecNote">Reads about a hundred exposures from NASA's archive: allow up to a minute.</p></section>`;
    return head + fullSpecBody(sp, color, d.type === "pulse") + `</section>`;
  }
  async function measureFullSpectrum(d, color) {
    if (measuring.has(d) || d.full_spectrum) return;
    const last = d.points[d.points.length - 1], first = d.points[0], m = d.motion || {}, q = new URLSearchParams();
    if (d.type === "arrow" && m.rate_arcsec_per_year && m.pa_deg != null) {       // follow the drift: position at the last sighting, speed east and north
      const pa = m.pa_deg * Math.PI / 180;
      q.set("ra", last.ra.toFixed(5)); q.set("dec", last.dec.toFixed(5)); q.set("t0", last.t.toFixed(2));
      q.set("pm_e", (m.rate_arcsec_per_year * Math.sin(pa)).toFixed(2)); q.set("pm_n", (m.rate_arcsec_per_year * Math.cos(pa)).toFixed(2));
    } else { q.set("ra", first.ra.toFixed(5)); q.set("dec", first.dec.toFixed(5)); }
    const redraw = () => { const el = $("fullSpec"); if (el && st.pickedDoodle === d.id) { el.outerHTML = fullSpectrumBlock(d, color); wireFullSpec(d.full_spectrum, nameOf(d)); if ($("fullSpecBtn")) $("fullSpecBtn").addEventListener("click", () => measureFullSpectrum(d, color)); } };
    measuring.add(d); redraw();
    try { d.full_spectrum = await BX.getJson(`${BX.API}/api/spectrum?${q}`, 300000); measuring.delete(d); redraw(); }
    catch (e) {
      measuring.delete(d); redraw();
      const note = $("fullSpecNote"), btn = $("fullSpecBtn");
      if (btn && st.pickedDoodle === d.id) btn.textContent = "Try again";
      if (note && st.pickedDoodle === d.id) note.textContent = `That did not work just now (${e.message || "no answer"}). NASA's archive may be slow: try once more.`;
    }
  }

  /* ------------------------------------------------------------------ the spectrum of any spot (the centre, or a mark) */
  const spotSpectra = new Map();
  const sepArcsec = (ra1, dec1, ra2, dec2) => Math.hypot((ra1 - ra2) * Math.cos(rad(dec1)), dec1 - dec2) * 3600;
  function openSpectrum(ra, dec, label) {
    if (st.example && st.example.simulated) { BX.toast("This example is made up, so there is no real sky to measure here."); return; }
    const own = (st.doodles || []).find((d) => (d.type === "arrow" || d.type === "pulse") && !d.simulated && d.points.some((p) => sepArcsec(p.ra, p.dec, ra, dec) < 6));
    if (own) {                                                 // a doodle sits here: its card has the spectrum, and follows the object if it drifts
      openCard(own.id);
      if (!own.full_spectrum) measureFullSpectrum(own, (TYPES[own.type] || TYPES.spark).color);
      setTimeout(() => { const el = $("fullSpec"); if (el) el.scrollIntoView({ block: "start" }); }, 80);
      return;
    }
    const key = `${ra.toFixed(4)}_${dec.toFixed(4)}`, ex = st.example;
    if (!spotSpectra.has(key) && ex && ex.spectrum && sepArcsec(ex.target.ra, ex.target.dec, ra, dec) < 3) spotSpectra.set(key, { sp: ex.spectrum });
    if (!spotSpectra.has(key)) spotSpectra.set(key, {});
    const spot = spotSpectra.get(key);
    st.pickedDoodle = null; st.pickedSpot = key;
    const draw = () => {
      if (st.pickedSpot !== key) return;
      const state = spot.sp ? fullSpecBody(spot.sp) : spot.error
        ? `<p class="spec-hint">That did not work just now (${esc(spot.error)}). NASA's archive may be slow.</p><div class="actions"><button class="btn" type="button" id="fullSpecBtn">Try again</button></div>` : WAITING;
      $("cardBody").classList.add("spot");
      $("cardBody").innerHTML =
        `<header class="card-head spot-head"><div><p class="kind">Spectrum · the light of one spot, spread out by colour</p>` +
        `<h2>${esc(BX.fmtSexa(ra, dec))} <span>${esc(label)}</span></h2></div></header>` +
        `<p class="explain-text">Every SPHEREx exposure sees this spot in one infrared colour. Blink X takes the exposures of one visit from all six detectors and measures the brightness on the spot in each of them.</p>` +
        `<section class="spectrum fullspec" id="fullSpec"><h3>${FULL_HEAD}</h3>${state}</section>` +
        `<p class="disclaimer">A quick look, not a calibrated measurement: no correction for the light that falls outside the small circle, and close neighbours add theirs.</p>`;
      wireFullSpec(spot.sp, label);
      if ($("fullSpecBtn")) $("fullSpecBtn").addEventListener("click", measure);
    };
    async function measure() {
      if (spot.busy) return;
      spot.busy = true; spot.error = null; draw();
      try { spot.sp = await BX.getJson(`${BX.API}/api/spectrum?${new URLSearchParams({ ra: ra.toFixed(5), dec: dec.toFixed(5), snap: 1 })}`, 300000); }
      catch (e) { spot.error = e.message || "no answer"; }
      spot.busy = false; draw();
    }
    draw();
    const dlg = $("card"); if (dlg.showModal && !dlg.open) dlg.showModal(); else dlg.setAttribute("open", "");
    renderBoard();
    if (!spot.sp && !spot.busy) measure();
  }
  BX.openSpectrum = openSpectrum;

  /* ------------------------------------------------------------------ light curve: brightness at each visit */
  function lightCurveBlock(d, color) {
    const b = d.brightness; if (!b || !b.curve || b.curve.length < 4) return "";
    const narrow = window.innerWidth < 720, W = narrow ? 340 : 560, H = narrow ? 190 : 186, L = 46, R = 12, T0 = 22, B = narrow ? 48 : 34;
    const visits = [...new Set(b.curve.map((q) => q[2]))].sort((p, q) => p - q), col = (W - L - R) / visits.length;
    const vals = b.curve.map((q) => q[1]), top = Math.max(1.5, Math.ceil(Math.max(...vals) * 10 + 1) / 10), bot = Math.max(0, Math.min(0.5, Math.floor(Math.min(...vals) * 10 - 1) / 10));
    const Y = (v) => T0 + (1 - (v - bot) / (top - bot)) * (H - T0 - B), f1 = (v) => v.toFixed(1);
    const mjdDate = (m) => new Date((m - 40587) * 86400000).toISOString();
    let g = `<line class="ax" x1="${L}" x2="${L}" y1="${T0}" y2="${H - B}"/><line class="ax" x1="${L}" x2="${W - R}" y1="${H - B}" y2="${H - B}"/>`;
    for (const v of [bot, 1, top]) g += `<line class="grid" x1="${L}" x2="${W - R}" y1="${f1(Y(v))}" y2="${f1(Y(v))}"/><text x="${L - 6}" y="${f1(Y(v) + 3.5)}" text-anchor="end">${v === 1 ? "1.0" : v.toFixed(1)}</text>`;
    g += `<text x="${L - 6}" y="${T0 - 9}" text-anchor="end">× usual</text>`;
    visits.forEach((v, i) => {
      const pts = b.curve.filter((q) => q[2] === v), x0 = L + col * i, t0 = pts[0][0], t1 = pts[pts.length - 1][0], span = Math.max(t1 - t0, 1e-6);
      const level = pts.map((q) => q[1]).sort((p, q) => p - q), mid = level.length % 2 ? level[level.length >> 1] : (level[(level.length >> 1) - 1] + level[level.length >> 1]) / 2;
      for (const q of pts) g += `<circle class="pt dim" cx="${f1(x0 + col * (0.25 + 0.5 * (q[0] - t0) / span))}" cy="${f1(Y(q[1]))}" r="${narrow ? 2.2 : 2.6}"><title>${mjdDate(q[0]).slice(0, 16).replace("T", " ")} UTC · ${q[1].toFixed(2)} × its usual brightness</title></circle>`;
      g += `<line class="line strong" x1="${f1(x0 + col * 0.15)}" x2="${f1(x0 + col * 0.85)}" y1="${f1(Y(mid))}" y2="${f1(Y(mid))}"/>`;
      g += `<text x="${f1(x0 + col / 2)}" y="${H - B + 15}" text-anchor="middle">${BX.monthYear(mjdDate(t0))}</text><text class="lc-n" x="${f1(x0 + col / 2)}" y="${H - B + 28}" text-anchor="middle">${narrow ? `${mid.toFixed(2)}×` : `${pts.length} exposures · ${mid.toFixed(2)}×`}</text>` +
        (narrow ? `<text x="${f1(x0 + col / 2)}" y="${H - B + 41}" text-anchor="middle">${pts.length} exposures</text>` : "");
    });
    return `<section class="spectrum lightcurve" style="--c:${color}"><h3>Brightness at each visit</h3>` +
      `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Brightness of this object at ${visits.length} visits">${g}</svg>` +
      `<p class="muted">Each dot is one exposure; the bar is the middle value of a visit. 1.0 is this object's own usual brightness, measured against the steady stars around it, ` +
      `after its colour trend is taken out (every exposure has a different infrared colour).</p></section>`;
  }

  function openCard(id) {
    const d = st.doodles.find((x) => x.id === id); if (!d) return;
    st.pickedDoodle = id; st.pickedSpot = null;
    const T = TYPES[d.type] || TYPES.spark, m = d.motion || {}, b = d.brightness || {}, first = d.points[0], last = d.points[d.points.length - 1];
    const rows = [];
    if (m.dist_arcsec != null) rows.push(["Moved", `${fmtNum(m.dist_arcsec)}″ = ${fmtNum(m.dist_spherex_px)} SPHEREx pixels, toward the ${m.direction}`]);
    if (d.type === "arrow" && m.rate_arcsec_per_year) rows.push(["Speed", `${fmtNum(m.rate_arcsec_per_year)}″ a year`]);
    else if (m.rate_arcsec_per_hour) rows.push(["Speed", `${fmtNum(m.rate_arcsec_per_hour, m.rate_arcsec_per_hour < 10 ? 1 : 0)}″ an hour`]);
    if (m.jump_arcsec) rows.push(["Jump", `${fmtNum(m.jump_arcsec, 0)}″ back and forth` + (m.distance_au ? ` → roughly ${fmtNum(m.distance_au, 0)} times the Earth–Sun distance` : "")]);
    if (d.tail_direction) rows.push(["Tail points", `toward the ${d.tail_direction}`]);
    if (b.change_pct) rows.push(["Brightness", `${b.change} by ${fmtNum(b.change_pct, 0)}%`]);
    if (d.deep) rows.push(["Found in", `${d.deep.visits} deep pictures, each one a visit's exposures added together (${d.deep.exposures} exposures in all). Ordinary stars shift by ${fmtNum(d.deep.star_scatter_arcsec, 2)}″ between them.`]);
    rows.push(["Seen", (d.deep ? `in ${d.sightings} visits: ` : `${d.sightings} time${d.sightings === 1 ? "" : "s"}: `) + (d.deep ? BX.fmtDate(first.date, false) : BX.fmtDate(first.date)) + (d.sightings > 1 ? ` → ${d.deep ? BX.fmtDate(last.date, false) : BX.fmtDate(last.date)}` : "")]);
    rows.push(["Where", `${BX.fmtSexa(first.ra, first.dec)}`]);
    rows.push(["How sure", `${Math.round((d.confidence || 0) * 100)}% <span class="muted">(a rule-of-thumb score from how often and how clearly it was seen)</span>`]);
    rows.push(["Checked in", esc((d.checked || []).join(", ") || "no catalogue could be reached")]);
    const sci = d.points.map((p) => `<tr><td>${esc((p.date || "").replace("T", " "))}</td><td>${p.ra.toFixed(5)}</td><td>${p.dec >= 0 ? "+" : ""}${p.dec.toFixed(5)}</td><td>${p.x.toFixed(1)}, ${p.y.toFixed(1)}</td><td>${p.wavelength_um ? p.wavelength_um.toFixed(3) : ""}</td><td>${p.peak_sigma}</td><td>${p.n}</td></tr>`).join("");
    const spec = spectrumBlock(d, T.color) || { html: "", table: "" };
    $("cardBody").classList.remove("spot");
    $("cardBody").innerHTML =
      `<header class="card-head" style="--c:${T.color}"><div class="big">${glyph(d, 96)}</div><div><p class="kind">${esc(T.label)} · ${esc(T.what)}</p>` +
      `<h2>${esc(d.id)} <span>“${esc(d.nickname)}”</span></h2>${statusChip(d)}</div></header>` +
      `<p class="explain-text">${esc(d.explain || "")}</p>` +
      `<dl class="card-facts">${rows.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join("")}</dl>` + lightCurveBlock(d, T.color) + fullSpectrumBlock(d, T.color) + spec.html +
      (d.status !== "known" ? `<p class="disclaimer">This is a candidate, not a discovery. Image flaws, reflections of bright stars and objects that shine in only one infrared colour can all look like this.</p>` : "") +
      `<details class="sci-table"><summary>Numbers for scientists</summary><div class="scroll"><table><thead><tr><th>UTC (mid-group)</th><th>RA °</th><th>Dec °</th><th>x, y (grid px)</th><th>λ µm</th><th>peak / noise</th><th>exposures</th></tr></thead><tbody>${sci}</tbody></table></div>${spec.table}` +
      `<p class="muted">Field centre RA ${d.field.ra}°, Dec ${d.field.dec}°, ${d.field.size_deg}° wide, ${d.field.pixscale_arcsec}″ per grid pixel (a SPHEREx detector pixel is 6.15″).` +
      (d.known && d.known.sep_arcsec != null ? ` Catalogue position differs by ${d.known.sep_arcsec}″.` : "") + (m.fit_rms_arcsec != null ? ` Straight-line fit scatter ${m.fit_rms_arcsec}″.` : "") + `</p></details>` +
      `<div class="actions"><button class="btn primary" type="button" id="cardBlink">${d.deep ? "Blink first vs last visit, added up" : d.sightings > 1 ? "Blink first vs last sighting" : "Show the picture it is in"}</button>` +
      `<button class="btn ghost" type="button" id="cardCopy">Copy coordinates</button></div>`;
    if ($("fullSpecBtn")) $("fullSpecBtn").addEventListener("click", () => measureFullSpectrum(d, T.color));
    wireFullSpec(d.full_spectrum, nameOf(d));
    $("cardBlink").addEventListener("click", () => {
      if (d.deep) {                                            // seen only when a visit's exposures are added together
        BX.setDepth("visit");
        const holds = (id) => st.frames.find((f) => f.stack && f.stack.ids.includes(id));
        const sa = holds(first.frame), sb = holds(last.frame);
        if (sa && sb && sa !== sb) { st.a = sa.id; st.b = sb.id; BX.afterPairChange(); BX.setMode("blink"); BX.setPlaying(true); }
        else BX.toast(st.stackWait ? "The pictures are still arriving; the visits will be added up in a moment." : "Those visits are not among the pictures loaded here.");
        closeCard(); $("stage").scrollIntoView({ behavior: "smooth", block: "center" });
        return;
      }
      if (st.depth !== "single") BX.setDepth("single");         // sightings are single exposures
      const fa = BX.byId(first.frame), fb = BX.byId(last.frame);
      if (fa) st.a = fa.id; if (fb && fb !== fa) st.b = fb.id;
      if (fa || fb) { BX.afterPairChange(); BX.setMode("blink"); BX.setPlaying(true); }
      else BX.toast("Those exposures are not among the pictures loaded here.");
      closeCard(); $("stage").scrollIntoView({ behavior: "smooth", block: "center" });
    });
    $("cardCopy").addEventListener("click", async () => {
      const txt = `${d.id} (${T.label}${d.known ? ", " + d.known.name : ", candidate"}): ` + d.points.map((p) => `${p.date}Z RA ${p.ra.toFixed(5)} Dec ${p.dec.toFixed(5)}`).join("; ");
      try { await navigator.clipboard.writeText(txt); BX.toast("Coordinates copied."); } catch (_) { window.prompt("Copy:", txt); }
    });
    const dlg = $("card"); if (dlg.showModal && !dlg.open) dlg.showModal(); else dlg.setAttribute("open", "");
    renderBoard();
  }
  function closeCard() { const dlg = $("card"); if (dlg.close && dlg.open) dlg.close(); else dlg.removeAttribute("open"); }
  BX.openCard = openCard;

  /* ------------------------------------------------------------------ legend, intro, tooltips */
  function renderLegend() {
    const demo = (type, extra) => ({ type, peak_sigma: 300, motion: { pa_deg: 300, rate_arcsec_per_year: 6, rate_arcsec_per_hour: 60, jump_arcsec: 500 }, brightness: { change: "brightened" }, ...extra });
    $("legendBody").innerHTML = Object.entries(TYPES).map(([k, T]) =>
      `<div class="legend-item"><span class="g">${glyph(demo(k), 60)}</span><div><strong style="color:${T.color}">${esc(T.label)}</strong> — ${esc(T.what)}<br><span class="muted">${esc(T.why)}</span></div></div>`).join("") +
      `<p class="legend-note"><strong>Reading any doodle:</strong> its <em>length</em> is how fast it goes, its <em>angle</em> is the direction on the sky (north is up, east is left), its <em>colour</em> is the kind of object, and a <em>thicker line</em> means a brighter object.</p>`;
  }

  function wireTips() {
    const bubble = $("tipBubble"); let owner = null;
    const hide = () => { bubble.hidden = true; owner = null; };
    const show = (el) => {
      bubble.textContent = el.dataset.tip; bubble.hidden = false; owner = el;
      const r = el.getBoundingClientRect(), bw = Math.min(300, window.innerWidth - 24);
      bubble.style.width = bw + "px";
      bubble.style.left = clamp(r.left + r.width / 2 - bw / 2, 12, window.innerWidth - bw - 12) + "px";
      const top = r.bottom + 8; bubble.style.top = (top + bubble.offsetHeight > window.innerHeight - 8 ? Math.max(8, r.top - bubble.offsetHeight - 8) : top) + "px";
    };
    document.addEventListener("click", (e) => { const t = e.target.closest("[data-tip]"); if (t) { e.preventDefault(); owner === t ? hide() : show(t); } else hide(); });
    document.addEventListener("mouseover", (e) => { const t = e.target.closest("[data-tip]"); if (t) show(t); });
    document.addEventListener("mouseout", (e) => { if (e.target.closest("[data-tip]")) hide(); });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") hide(); });
    window.addEventListener("scroll", hide, { passive: true });
  }

  function wireIntro() {
    const el = $("intro"); let seen = false;
    try { seen = localStorage.getItem("blinkx.intro") === "1"; } catch (_) { /* private mode */ }
    el.classList.toggle("compact", seen);
    $("introClose").addEventListener("click", () => { el.classList.add("compact"); try { localStorage.setItem("blinkx.intro", "1"); } catch (_) { /* ignore */ } });
    $("introOpen").addEventListener("click", () => el.classList.remove("compact"));
    $("step1").addEventListener("click", () => { $("q").focus(); $("q").scrollIntoView({ behavior: "smooth", block: "center" }); });
    $("step2").addEventListener("click", () => $("stage").scrollIntoView({ behavior: "smooth", block: "center" }));
    $("step3").addEventListener("click", () => $("doodlePanel").scrollIntoView({ behavior: "smooth", block: "start" }));
  }

  $("showDoodles").addEventListener("change", (e) => { st.showDoodles = e.target.checked; renderDoodleLayer(e.target.checked); });
  $("cardClose").addEventListener("click", closeCard);
  $("card").addEventListener("click", (e) => { if (e.target === $("card")) closeCard(); });     // click on the backdrop
  $("card").addEventListener("close", () => { st.pickedDoodle = null; st.pickedSpot = null; renderBoard(); });
  renderLegend(); wireTips(); wireIntro(); renderBoard();
})();
