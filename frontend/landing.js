/* Blink X — landing: the real sky is the hero.
 *
 * A zoomable all-sky map drawn by Aladin Lite (free, CDS) from the SPHEREx all-sky cube that
 * NASA/IPAC IRSA publishes as a HiPS: 102 wavelengths, one slider. If the viewer or the map
 * cannot load, a real SPHEREx exposure from the saved examples is shown instead.
 */
const BX = window.BX, $ = (id) => document.getElementById(id);
const ALADIN = "https://cdn.jsdelivr.net/npm/aladin-lite@3.8.2/dist/aladin.js";
const HIPS = "https://irsa.ipac.caltech.edu/data/hips/SPHEREx/spherex_allsky_cube";
const reduce = !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
const landing = $("landing"), mast = $("mast");
let aladin = null, layer = null, waves = [], touched = false, exploring = false, targets = null;

// Aladin Lite reports its start-up to a CDS server; when that server is down the rejected request
// is harmless, so it should not surface as a page error.
window.addEventListener("unhandledrejection", (e) => { if (/Failed to fetch|NetworkError|Load failed/i.test(String(e.reason && e.reason.message || e.reason))) e.preventDefault(); });

/* ------------------------------------------------------------------ chrome */
const onScroll = () => mast.classList.toggle("solid", window.scrollY > landing.offsetHeight - 90);
window.addEventListener("scroll", onScroll, { passive: true }); onScroll();
const go = (id) => { const el = $(id); if (el) el.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" }); };
$("startBtn").addEventListener("click", () => go(BX.st.frames.length ? "viewer" : "targets"));

const p2 = (v) => String(v).padStart(2, "0");
function showCoords(ra, dec) {
  const t = Math.round((((ra % 360) + 360) % 360) / 15 * 3600), a = Math.round(Math.abs(dec) * 3600);
  $("skyRa").textContent = `${p2(Math.floor(t / 3600) % 24)}h ${p2(Math.floor((t % 3600) / 60))}m ${p2(t % 60)}s`;
  $("skyDec").textContent = `${dec < 0 ? "−" : "+"}${p2(Math.floor(a / 3600))}° ${p2(Math.floor((a % 3600) / 60))}′ ${p2(a % 60)}″`;
}
const showFov = (f) => { $("skyFov").textContent = f >= 10 ? `${f.toFixed(0)}°` : f >= 1 ? `${f.toFixed(1)}°` : `${(f * 60).toFixed(0)}′`; };
function showWave(i) { $("skyWl").textContent = waves[i] ? `${waves[i].toFixed(2)} µm · ${i + 1} of ${waves.length}` : `slice ${i + 1}`; }

/* ------------------------------------------------------------------ fallback: a real SPHEREx exposure */
function fallback(why) {
  if (aladin) return;
  const cv = $("skyFallback"), draw = () => {
    const f = BX.byId(BX.st.a) || BX.st.frames.find((x) => x.z); if (!f || !f.z) return false;
    const src = BX.frameCanvas(f, 1), w = landing.clientWidth, h = landing.clientHeight, s = Math.max(w, h);
    cv.width = w; cv.height = h; const ctx = cv.getContext("2d"); ctx.imageSmoothingEnabled = true;
    ctx.drawImage(src, (w - s) / 2, (h - s) / 2, s, s);
    cv.hidden = false; $("sky").hidden = true;
    showCoords(BX.st.target.ra, BX.st.target.dec); showFov(BX.st.size);
    $("skyWl").textContent = f.wavelength_um ? `${f.wavelength_um.toFixed(2)} µm` : "";
    $("skySrc").textContent = `SPHEREx exposure of ${BX.st.target.name || "this field"} (the all-sky map ${why})`;
    return true;
  };
  if (!draw()) { const t = setInterval(() => { if (aladin || draw()) clearInterval(t); }, 500); setTimeout(() => clearInterval(t), 20000); }
}

/* ------------------------------------------------------------------ the map */
function setExplore(on) {
  exploring = on; touched = touched || on;
  landing.classList.toggle("exploring", on);
  $("exploreBtn").querySelector("span").textContent = on ? "Done exploring" : "Explore the sky map";
  $("huntHere").hidden = !on;
  if (targets) { try { on ? targets.show() : targets.hide(); } catch (_) { /* older builds */ } }
}

async function start() {
  const giveUp = setTimeout(() => fallback("is taking too long to load"), 9000);
  try {
    const canvas = document.createElement("canvas");
    if (!canvas.getContext("webgl2")) throw new Error("no WebGL2");
    const { default: A } = await import(ALADIN);
    await A.init;
    const wide = landing.clientWidth > 720;
    aladin = A.aladin("#sky", {
      survey: HIPS, target: wide ? "281.0 -24.0" : "270.0 -27.0", fov: wide ? 78 : 44, cooFrame: "ICRSd", backgroundColor: "rgb(0, 0, 0)",
      showReticle: false, showZoomControl: false, showFullscreenControl: false, showLayersControl: false, showGotoControl: false, showShareControl: false,
      showFrame: false, showCooGrid: false, showProjectionControl: false, showContextMenu: false, showSettingsControl: false, showStatusBar: false,
      showCooLocation: false, showFov: false, showSimbadPointerControl: false, showCooGridControl: false,
    });
    clearTimeout(giveUp);
    $("skyFallback").hidden = true; $("sky").hidden = false;
    // the layer learns that it is a 102-slice cube only after its properties file has arrived
    await new Promise((res) => { let k = 0; const t = setInterval(() => { layer = aladin.getBaseImageLayer(); if ((layer && layer.cubeDepth > 1) || ++k > 45) { clearInterval(t); res(); } }, 200); });
    $("skySrc").textContent = "SPHEREx all-sky map, DR1 (NASA/IPAC IRSA), drawn with Aladin Lite";
    BX.sky = aladin; BX.skyLayer = layer;

    // wavelengths of the 102 slices, from the map's own properties file
    try {
      const txt = await (await fetch(`${HIPS}/properties`)).text();
      const m = /data_cube_crval3_arr\s*=\s*(.+)/.exec(txt); if (m) waves = m[1].trim().split(/\s+/).map(Number).filter((v) => v > 0);
    } catch (_) { /* the slider still works, without labels */ }
    const slider = $("skyWlSlider"), depth = (layer && layer.cubeDepth) || waves.length || 102;
    slider.max = depth - 1; slider.disabled = !(layer && layer.setSliceNumber);
    const setSlice = (i) => { try { layer.setSliceNumber(i); } catch (_) { /* older builds */ } showWave(i); };
    if (!slider.disabled) { setSlice(+slider.value); slider.addEventListener("input", () => { touched = true; setSlice(+slider.value); }); }
    else $("skyWl").textContent = "all wavelengths";

    // live readout
    const tick = () => { const rd = aladin.getRaDec(), fv = aladin.getFov(); showCoords(rd[0], rd[1]); showFov(Array.isArray(fv) ? fv[0] : fv); };
    tick(); setInterval(() => { if (window.scrollY < landing.offsetHeight) tick(); }, 250);

    // the example targets, pinned on the real sky
    try {
      const list = (await (await fetch("examples/index.json")).json()).filter((e) => !e.simulated && e.ra != null);
      const seen = new Set(), uniq = list.filter((e) => { const k = `${e.ra.toFixed(1)}_${e.dec.toFixed(1)}`; if (seen.has(k)) return false; seen.add(k); return true; });
      const cat = A.catalog({ name: "Targets", sourceSize: 18, color: "#ff5a1f", shape: "circle", displayLabel: true, labelColumn: "label", labelColor: "#efe9dd", labelFont: "12px IBM Plex Mono, monospace" });
      aladin.addCatalog(cat);
      cat.addSources(uniq.map((e) => A.source(e.ra, e.dec, { label: e.label, slug: e.slug })));
      targets = cat; if (cat.hide) cat.hide();                 // the pins appear when someone starts exploring
      aladin.on("objectClicked", (o) => { const slug = o && o.data && o.data.slug; if (slug) { BX.st.fromCode = null; BX.loadExample(slug); go("viewer"); } });
    } catch (_) { /* pins are a bonus */ }

    // slow drift, so the sky is alive; stops for good the moment someone touches it
    if (!reduce) setInterval(() => {
      if (touched || document.hidden || window.scrollY > landing.offsetHeight * 0.6) return;
      const rd = aladin.getRaDec(); aladin.gotoRaDec(rd[0] + 0.006, rd[1]);
    }, 60);

    $("exploreBtn").hidden = false;
  } catch (e) {
    clearTimeout(giveUp); fallback("could not be loaded here");
  }
}

$("exploreBtn").addEventListener("click", () => setExplore(!exploring));
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && exploring) setExplore(false); });
$("huntHere").addEventListener("click", () => {
  if (!aladin) return;
  const rd = aladin.getRaDec(); setExplore(false); BX.st.fromCode = null;
  BX.loadLive({ ra: +rd[0].toFixed(5), dec: +rd[1].toFixed(5), name: "" }, { band: 2, size: 0.2, mode: "blink" });
  go("viewer");
});

// the page itself (and the saved example) come first; the sky map loads right after
if (document.readyState === "complete") start(); else window.addEventListener("load", () => setTimeout(start, 50));
