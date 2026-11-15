/* Blink X — sharing and science tools (Tier 2):
 *   Sky Code  : one short string that stores the field, the two epochs, the band and the doodles
 *   Exports   : JSON, CSV and the doodle map as SVG / PNG
 *   Tracking Board filters, Scientist view (raw numbers, FITS metadata)
 */
(() => {
  "use strict";
  const BX = window.BX, { st, $, esc } = BX, TYPES = BX.TYPES;
  const TYPE_CODE = { zigzag: "z", arrow: "a", spark: "s", tail: "t", pulse: "p" }, CODE_TYPE = Object.fromEntries(Object.entries(TYPE_CODE).map(([k, v]) => [v, k]));

  /* ------------------------------------------------------------------ Sky Code */
  const toB64u = (bytes) => { let s = ""; for (const b of bytes) s += String.fromCharCode(b); return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, ""); };
  const fromB64u = (str) => { const bin = atob(str.replace(/-/g, "+").replace(/_/g, "/")); const out = new Uint8Array(bin.length); for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i); return out; };
  async function pipe(bytes, stream) {
    const w = stream.writable.getWriter(); w.write(bytes); w.close();
    return new Uint8Array(await new Response(stream.readable).arrayBuffer());
  }

  function snapshot() {
    const r5 = (v) => Math.round(v * 1e5) / 1e5;
    return {
      v: 1, x: st.example ? st.example.slug : 0, t: st.target.name || "", f: [r5(st.target.ra), r5(st.target.dec), st.size, st.band], p: [st.a, st.b], m: st.mode, ...(st.depth && st.depth !== "single" ? { k: st.depth } : {}),
      d: st.doodles.map((d) => {
        const a = d.points[0], b = d.points[d.points.length - 1], m = d.motion || {};
        const rate = d.type === "arrow" ? m.rate_arcsec_per_year : d.type === "zigzag" ? m.jump_arcsec : m.rate_arcsec_per_hour;
        return [d.id, TYPE_CODE[d.type], d.known ? d.known.name : 0, Math.round((d.confidence || 0) * 100), r5(a.ra), r5(a.dec), r5(b.ra), r5(b.dec), rate ? Math.round(rate * 10) / 10 : 0, m.pa_deg == null ? -1 : Math.round(m.pa_deg)];
      }),
    };
  }
  async function makeSkyCode() {
    const bytes = new TextEncoder().encode(JSON.stringify(snapshot()));
    if (typeof CompressionStream === "function") {
      try { return "SKY2." + toB64u(await pipe(bytes, new CompressionStream("deflate-raw"))); } catch (_) { /* fall through to the plain form */ }
    }
    return "SKY1." + toB64u(bytes);
  }
  async function readSkyCode(code) {
    const m = /^(SKY[12])\.([A-Za-z0-9_-]+)$/.exec(String(code).trim());
    if (!m) throw new Error("That does not look like a Sky Code. It should start with SKY1. or SKY2.");
    let bytes = fromB64u(m[2]);
    if (m[1] === "SKY2") {
      if (typeof DecompressionStream !== "function") throw new Error("This browser is too old to open a SKY2 code.");
      bytes = await pipe(bytes, new DecompressionStream("deflate-raw"));
    }
    const o = JSON.parse(new TextDecoder().decode(bytes));
    if (!o || o.v !== 1 || !Array.isArray(o.f) || o.f.length < 4) throw new Error("This Sky Code is damaged or from a newer version.");
    return o;
  }
  const skyUrl = (code) => location.origin + location.pathname + "?sky=" + code;

  async function openSky(code) {
    let o;
    try { o = await readSkyCode(code); } catch (e) { BX.setStatus(e.message, true); BX.toast(e.message, 5000); return false; }
    st.fromCode = { code: String(code).trim(), doodles: (o.d || []).map((r) => ({ id: r[0], type: CODE_TYPE[r[1]] || "spark", known: r[2] || null, confidence: r[3] / 100 })) };
    const opts = { band: o.f[3], size: o.f[2], a: o.p && o.p[0], b: o.p && o.p[1], mode: o.m, depth: o.k };
    if (o.x) await BX.loadExample(o.x, opts);
    else await BX.loadLive({ ra: +o.f[0], dec: +o.f[1], name: o.t || "" }, opts);
    refreshShare();
    return true;
  }
  BX.openSky = openSky;

  let codeTimer = null;
  function refreshShare() {
    clearTimeout(codeTimer);
    codeTimer = setTimeout(async () => {
      if (!st.target || !st.frames.length) { $("skyCode").textContent = ""; return; }
      const code = await makeSkyCode();
      st.skyCode = code; $("skyCode").textContent = code;
      $("skyLen").textContent = `${code.length} characters`;
      const fc = st.fromCode, note = $("codeNote");
      if (fc && st.doodleState === "done") {
        const mine = new Set(st.doodles.map((d) => d.id)), theirs = fc.doodles.map((d) => d.id), same = theirs.length === mine.size && theirs.every((i) => mine.has(i));
        note.hidden = false; note.className = "code-note " + (same ? "ok" : "warn");
        note.textContent = same ? `Opened from a Sky Code. The search found the same ${theirs.length} doodle${theirs.length === 1 ? "" : "s"} that the code lists${theirs.length ? ": " + theirs.join(", ") : ""}.`
          : `Opened from a Sky Code that lists ${theirs.join(", ") || "no doodles"}; the search here found ${[...mine].join(", ") || "none"}. The archive or the method may have changed since the code was made.`;
      } else note.hidden = true;
    }, 150);
  }

  /* ------------------------------------------------------------------ exports */
  function download(name, mime, data) {
    const blob = data instanceof Blob ? data : new Blob([data], { type: mime });
    const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = name;
    document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(a.href), 4000);
  }
  const slug = () => (st.target.name || "sky").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "sky";

  function exportObject() {
    return {
      made_with: "Blink X (NASA Space Apps 2026, team KhoFra)", url: skyUrl(st.skyCode || ""), sky_code: st.skyCode || null, exported_utc: new Date().toISOString(),
      note: "Doodles are produced by automatic change detection on NASA SPHEREx Level-2 images. 'candidate' means not matched to a catalogue; it is not a discovery claim." + (st.example && st.example.simulated ? " THIS FIELD IS SIMULATED, NOT REAL DATA." : ""),
      simulated: !!(st.example && st.example.simulated),
      field: { name: st.target.name || null, ra_deg: st.target.ra, dec_deg: st.target.dec, size_deg: st.size, band: st.band, grid_pixels: st.n, pixscale_arcsec: st.size * 3600 / st.n, spherex_pixel_arcsec: 6.15 },
      compared: { a: st.a, b: st.b, exposures: st.depth === "visit" ? "added together per visit (median)" : st.depth === "all" ? "all added together (median)" : "single exposures" },
      epochs: (st.singles && st.singles.length ? st.singles : st.frames).map((f) => ({ id: f.id, date_obs_utc: f.date_obs, mjd: f.mjd, wavelength_um: f.wavelength_um, bandwidth_um: f.bandwidth_um, exposure_s: f.exptime, collection: f.collection, detector_pixel: f.pixel, sky_mjy_sr: f.sky, noise_mjy_sr: f.sigma, fits_url: f.irsa_url || null, alignment: st.align[f.id] || null })),
      catalogues_answered: st.checked, doodles: st.doodles,
    };
  }
  function exportCsv() {
    const cols = ["id", "nickname", "type", "status", "known_name", "known_source", "confidence", "epoch_index", "date_utc", "mjd", "ra_deg", "dec_deg", "x_px", "y_px", "wavelength_um", "peak_over_noise", "exposures_in_group", "frame_id",
      "displacement_arcsec", "displacement_spherex_px", "direction_deg_east_of_north", "direction", "rate_arcsec_per_hour", "rate_arcsec_per_year", "jump_arcsec", "brightness_change", "brightness_change_pct"];
    const q = (v) => v == null ? "" : /[",\n]/.test(String(v)) ? `"${String(v).replace(/"/g, '""')}"` : String(v);
    const rows = [cols.join(",")];
    for (const d of st.doodles) d.points.forEach((p, k) => {
      const m = d.motion || {}, b = d.brightness || {};
      rows.push([d.id, d.nickname, d.type, d.status, d.known && d.known.name, d.known && d.known.source, d.confidence, k + 1, p.date, p.t, p.ra, p.dec, p.x, p.y, p.wavelength_um, p.peak_sigma, p.n, p.frame,
        m.dist_arcsec, m.dist_spherex_px, m.pa_deg, m.direction, m.rate_arcsec_per_hour, m.rate_arcsec_per_year, m.jump_arcsec, b.change, b.change_pct].map(q).join(","));
    });
    return rows.join("\n") + "\n";
  }

  /** The doodle map: the picture on screen, the doodles drawn on it, and a key. One self-contained SVG. */
  function doodleMapSvg() {
    const n = st.n, u = n / 128, S = 640, pad = 24, listW = 400, W = S + listW + 3 * pad, rowsH = 74, H = Math.max(S + 150, 120 + st.doodles.length * rowsH + 90);
    const f = BX.shown()[0], img = $("cv0").toDataURL("image/png");
    const overlay = $("ov0").innerHTML + BX.doodleSvg(u, n, false);
    const tx = (s) => esc(String(s == null ? "" : s));
    let list = "";
    st.doodles.forEach((d, k) => {
      const y = 110 + k * rowsH, T = TYPES[d.type] || TYPES.spark, m = d.motion || {};
      const line = d.type === "arrow" ? `${m.rate_arcsec_per_year}″/yr toward ${m.direction}` : d.type === "zigzag" ? `jumps ${m.jump_arcsec}″ between visits` : m.dist_arcsec ? `${m.dist_arcsec}″ toward ${m.direction}, ${m.rate_arcsec_per_hour}″/h` : (d.brightness && d.brightness.change_pct ? `${d.brightness.change} ${d.brightness.change_pct}%` : "seen once");
      list += `<g transform="translate(${S + 2 * pad},${y})"><rect width="${listW}" height="${rowsH - 10}" fill="#000" stroke="#26221d"/><g transform="translate(6,4)">${BX.glyph(d, 56)}</g>` +
        `<text x="72" y="24" fill="#efe9dd" font-size="16" font-weight="500">${tx(d.id)} · ${tx(d.nickname)}</text><text x="72" y="43" fill="${T.color}" font-size="13">${tx(T.label)}: ${tx(line)}</text>` +
        `<text x="72" y="59" fill="${d.status === "known" ? "#efe9dd" : "#ff5a1f"}" font-size="12">${d.status === "known" ? "Known: " + tx(d.known.name) + " (" + tx(d.known.source) + ")" : d.status === "unchecked" ? "Not checked against catalogues" : "Candidate (not a discovery)"}</text></g>`;
    });
    if (!st.doodles.length) list = `<text x="${S + 2 * pad}" y="130" fill="#aaa294" font-size="14">No doodles in this field.</text>`;
    const A = BX.byId(st.a), B = BX.byId(st.b), sim = st.example && st.example.simulated;
    return `<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" font-family="'IBM Plex Mono', ui-monospace, Menlo, monospace">` +
      `<rect width="${W}" height="${H}" fill="#050506"/><text x="${pad}" y="40" fill="#efe9dd" font-size="30" font-family="'Instrument Serif', Georgia, serif">Sky Doodles — ${tx(st.target.name || "sky position")}</text>` +
      `<text x="${pad}" y="60" fill="#aaa294" font-size="13">RA ${st.target.ra.toFixed(4)}°, Dec ${st.target.dec >= 0 ? "+" : ""}${st.target.dec.toFixed(4)}° · field ${(st.size * 60).toFixed(0)}′ · ${st.frames.length} exposures · north up, east left${sim ? " · SIMULATED, NOT REAL DATA" : ""}</text>` +
      `<image x="${pad}" y="80" width="${S}" height="${S}" preserveAspectRatio="none" href="${img}" xlink:href="${img}"/>` +
      `<svg x="${pad}" y="80" width="${S}" height="${S}" viewBox="0 0 ${n} ${n}" preserveAspectRatio="none"><style>text{font-family:'IBM Plex Mono',ui-monospace,Menlo,monospace;font-weight:500;paint-order:stroke;stroke:rgba(0,0,0,.8);stroke-width:${0.7 * u}px}</style>${overlay}</svg>` +
      `<rect x="${pad}" y="80" width="${S}" height="${S}" fill="none" stroke="#40382f"/>` + list +
      `<text x="${S + 2 * pad}" y="96" fill="#aaa294" font-size="13">length = speed · angle = direction · colour = type · thickness = brightness</text>` +
      `<text x="${pad}" y="${S + 104}" fill="#aaa294" font-size="12">Picture: ${tx(f ? BX.fmtDate(f.date_obs) + " · " + BX.fmtWl(f) : "")}${A && B ? " · compared " + tx(BX.fmtDate(A.date_obs)) + " with " + tx(BX.fmtDate(B.date_obs)) : ""}</text>` +
      `<text x="${pad}" y="${S + 122}" fill="#aaa294" font-size="12">${sim ? "Simulated field" : "NASA SPHEREx Level-2 images via NASA/IPAC IRSA"} · made with Blink X · ${tx(location.origin + location.pathname)}</text>` +
      (st.skyCode && st.skyCode.length < 260 ? `<text x="${pad}" y="${S + 140}" fill="#746d61" font-size="10">Sky Code ${tx(st.skyCode)}</text>` : "") + `</svg>`;
  }
  function svgToPng(svg) {
    return new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = () => { const c = document.createElement("canvas"); c.width = img.width * 2; c.height = img.height * 2; const ctx = c.getContext("2d"); ctx.scale(2, 2); ctx.drawImage(img, 0, 0); c.toBlob((b) => b ? resolve(b) : reject(new Error("no image")), "image/png"); };
      img.onerror = () => reject(new Error("The browser could not draw the map."));
      img.src = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(svg);
    });
  }
  Object.assign(BX, { makeSkyCode, readSkyCode, exportObject, exportCsv, doodleMapSvg });

  /* ------------------------------------------------------------------ Tracking Board: filters and the numbers table */
  st.filter = { type: "all", visit: "all" };
  function visitLabels() { return BX.visitsOf(st.singles && st.singles.length ? st.singles : st.frames).map((v, i) => ({ i, label: v.label, ids: new Set(v.frames.map((f) => f.id)) })); }
  BX.doodleVisible = (d) => {
    if (st.filter.type !== "all" && d.type !== st.filter.type) return false;
    if (st.filter.visit !== "all") { const v = visitLabels()[+st.filter.visit]; if (v && !d.points.some((p) => (p.frames || [p.frame]).some((id) => v.ids.has(id)))) return false; }
    return true;
  };
  function renderFilters() {
    const box = $("boardFilters"), ds = st.doodles;
    box.hidden = ds.length < 2 && st.filter.type === "all" && st.filter.visit === "all";
    const counts = {}; for (const d of ds) counts[d.type] = (counts[d.type] || 0) + 1;
    const vis = visitLabels();
    box.innerHTML = `<span class="muted">Show</span>` +
      [["all", `All (${ds.length})`], ...Object.keys(TYPES).filter((k) => counts[k]).map((k) => [k, `${TYPES[k].label} (${counts[k]})`])]
        .map(([k, label]) => `<button type="button" class="fchip" data-type="${k}" aria-pressed="${st.filter.type === k}" ${k !== "all" ? `style="--c:${TYPES[k].color}"` : ""}>${esc(label)}</button>`).join("") +
      (vis.length > 1 ? `<label class="inline">seen in <select id="visitFilter"><option value="all">any visit</option>${vis.map((v) => `<option value="${v.i}" ${String(v.i) === String(st.filter.visit) ? "selected" : ""}>${esc(v.label)}</option>`).join("")}</select></label>` : "");
    for (const b of box.querySelectorAll(".fchip")) b.addEventListener("click", () => { st.filter.type = b.dataset.type; BX.renderBoard(); BX.schedule(); });
    const sel = $("visitFilter"); if (sel) sel.addEventListener("change", () => { st.filter.visit = sel.value; BX.renderBoard(); BX.schedule(); });
  }
  function renderBoardTable() {
    const el = $("boardTable"); if (!el) return;
    const ds = st.doodles.filter(BX.doodleVisible), f = (v, n = 2) => v == null ? "" : Number(v).toFixed(n);
    el.innerHTML = !ds.length ? "" : `<table><thead><tr><th>ID</th><th>Type</th><th>Status</th><th>Epochs</th><th>First seen (UTC)</th><th>Last seen (UTC)</th><th>RA° first</th><th>Dec° first</th><th>Shift ″</th><th>Shift px</th><th>PA °</th><th>″/h</th><th>″/yr</th><th>Δ bright %</th><th>Peak/noise</th><th>Conf.</th></tr></thead><tbody>` +
      ds.map((d) => { const a = d.points[0], b = d.points[d.points.length - 1], m = d.motion || {}, br = d.brightness || {};
        return `<tr data-id="${esc(d.id)}"><td><button type="button" class="linklike">${esc(d.id)}</button></td><td>${esc(d.type)}</td><td>${esc(d.status === "known" ? d.known.name : d.status)}</td><td>${d.epochs}</td><td>${esc((a.date || "").replace("T", " "))}</td><td>${esc((b.date || "").replace("T", " "))}</td>` +
          `<td>${a.ra.toFixed(5)}</td><td>${a.dec.toFixed(5)}</td><td>${f(m.dist_arcsec)}</td><td>${f(m.dist_spherex_px)}</td><td>${f(m.pa_deg, 1)}</td><td>${f(m.rate_arcsec_per_hour, 3)}</td><td>${f(m.rate_arcsec_per_year, 2)}</td><td>${f(br.change_pct, 0)}</td><td>${f(d.peak_sigma, 0)}</td><td>${f(d.confidence)}</td></tr>`; }).join("") + `</tbody></table>`;
    for (const b of el.querySelectorAll(".linklike")) b.addEventListener("click", () => BX.openCard(b.closest("tr").dataset.id));
  }

  /* ------------------------------------------------------------------ Scientist view */
  function renderSci() {
    const el = $("sciFrames"); if (!el) return;
    if (!document.body.classList.contains("sci") || !st.frames.length) { el.innerHTML = ""; return; }
    const stats = st.example ? st.example.detect_stats : null, ck = st.checked || {};
    const yes = (v) => v === true ? "answered" : v === false ? "no answer" : "not needed";
    $("sciStats").textContent = `Grid ${st.n}×${st.n} px, ${(st.size * 3600 / st.n).toFixed(2)}″ per pixel (SPHEREx detector pixel 6.15″). ` +
      (stats ? `Detection: ${stats.frames} exposures, about ${stats.sources} sources each, ${stats.anchors} anchor stars, ${stats.visits} visit(s), ${stats.bursts} group(s) of exposures. ` : "") +
      `Catalogues: SkyBoT ${yes(ck.skybot)}, SIMBAD ${yes(ck.simbad)}, JPL Horizons track ${ck.horizons ? "used" : "not used"}.`;
    el.innerHTML = `<table><thead><tr><th>#</th><th>Exposure</th><th>DATE-OBS (UTC)</th><th>MJD mid</th><th>λ µm</th><th>Δλ µm</th><th>Detector px</th><th>Exp s</th><th>PSF ″</th><th>Sky MJy/sr</th><th>Noise MJy/sr</th><th>Repaired %</th><th>Star shift ″ (dx, dy)</th><th>Stars</th><th>Release</th></tr></thead><tbody>` +
      (st.singles && st.singles.length ? st.singles : st.frames).map((f, i) => { const a = st.align[f.id] || {};
        return `<tr class="${f.id === st.a ? "is-a" : f.id === st.b ? "is-b" : ""}"><td>${i + 1}</td><td>${f.irsa_url ? `<a href="${esc(f.irsa_url)}" target="_blank" rel="noopener">${esc(f.id)}</a>` : esc(f.id)}</td><td>${esc((f.date_obs || "").replace("T", " "))}</td><td>${f.mjd.toFixed(5)}</td>` +
          `<td>${f.wavelength_um ? f.wavelength_um.toFixed(4) : ""}</td><td>${f.bandwidth_um ? f.bandwidth_um.toFixed(4) : ""}</td><td>${f.pixel ? f.pixel.map((v) => v.toFixed(0)).join(", ") : ""}</td><td>${f.exptime ? f.exptime.toFixed(1) : ""}</td><td>${f.psf_fwhm_arcsec ? f.psf_fwhm_arcsec.toFixed(2) : ""}</td>` +
          `<td>${f.sky != null ? f.sky.toFixed(4) : ""}</td><td>${f.sigma != null ? Number(f.sigma).toPrecision(3) : ""}</td><td>${f.masked_fraction != null ? (f.masked_fraction * 100).toFixed(1) : ""}</td><td>${a.dx_arcsec != null ? a.dx_arcsec.toFixed(2) + ", " + a.dy_arcsec.toFixed(2) : ""}</td><td>${a.stars != null ? a.stars : ""}</td><td>${esc(f.collection || "")}</td></tr>`; }).join("") + `</tbody></table>`;
  }
  function setSci(on) {
    document.body.classList.toggle("sci", on); $("sciBtn").setAttribute("aria-pressed", String(on));
    try { localStorage.setItem("blinkx.sci", on ? "1" : "0"); } catch (_) { /* private mode */ }
    renderSci(); renderBoardTable();
  }

  /* ------------------------------------------------------------------ wiring */
  const prevBoardExtra = BX.hooks.boardExtra;
  BX.hooks.boardExtra = () => { if (prevBoardExtra) prevBoardExtra(); renderFilters(); renderBoardTable(); renderSci(); refreshShare(); };
  const copy = async (text, ok) => { try { await navigator.clipboard.writeText(text); BX.toast(ok); } catch (_) { window.prompt("Copy:", text); } };
  $("copyCode").addEventListener("click", () => st.skyCode && copy(st.skyCode, "Sky Code copied. Paste it anywhere; anyone can open it here."));
  $("copyCodeUrl").addEventListener("click", () => st.skyCode && copy(skyUrl(st.skyCode), "Link copied. It opens this exact view."));
  $("openCodeForm").addEventListener("submit", (e) => { e.preventDefault(); const v = $("openCode").value.trim(); if (v) openSky(v.includes("sky=") ? decodeURIComponent(v.split("sky=")[1].split("&")[0]) : v).then((ok) => { if (ok) { $("openCode").value = ""; $("viewer").scrollIntoView({ behavior: "smooth", block: "start" }); } }); });
  $("dlPng").addEventListener("click", async () => { try { download(`blinkx-doodles-${slug()}.png`, "image/png", await svgToPng(doodleMapSvg())); } catch (e) { BX.toast(e.message); } });
  $("dlSvg").addEventListener("click", () => download(`blinkx-doodles-${slug()}.svg`, "image/svg+xml", doodleMapSvg()));
  $("dlJson").addEventListener("click", () => download(`blinkx-doodles-${slug()}.json`, "application/json", JSON.stringify(exportObject(), null, 1)));
  $("dlCsv").addEventListener("click", () => download(`blinkx-doodles-${slug()}.csv`, "text/csv", exportCsv()));
  $("sciBtn").addEventListener("click", () => setSci(!document.body.classList.contains("sci")));
  for (const id of ["selA", "selB", "swapBtn"]) $(id).addEventListener("change", refreshShare);
  document.querySelector(".tabs").addEventListener("click", refreshShare);
  let sci = false; try { sci = localStorage.getItem("blinkx.sci") === "1"; } catch (_) { /* ignore */ }
  setSci(sci);
})();
