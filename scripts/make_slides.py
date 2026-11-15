"""Write frontend/slides/index.html: seven slides built from the website's own design pieces
(mast, eyebrow, display headline, section numbers, numbered rows, step cells, tab bar, readout bar).

    python scripts/make_slides.py

Then print frontend/slides/index.html to PDF from a browser (1280 x 720 px pages, background graphics on)
to refresh frontend/slides/blinkx-slides.pdf. The pictures in frontend/slides/img/ are screenshots of the tool."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
G = json.load(open(ROOT / "scripts" / "slide_glyphs.json"))  # the five doodle shapes, copied from the page's own legend
glyph = {}
for it in G["items"]:
    svg = re.sub(r'\s(width|height|role|aria-label|class)="[^"]*"', "", it["svg"])
    svg = re.sub(r"(\d+\.\d{2})\d+", r"\1", svg)  # shorter numbers
    glyph[it["name"]] = svg.replace("<svg", '<svg aria-hidden="true"', 1)
T = G["types"]

NAV = ["Challenge", "Tool", "Doodles", "Tested", "Spectra", "Data"]


def mast(active=None):
    if active is None:
        nav = '<span>NASA Space Apps Challenge 2026</span><span>Planet X and SPHEREx</span><span class="btn">Project demo · 7 slides</span>'
    else:
        nav = "".join(f'<span{" class=on" if n == active else ""}>{n}</span>' for n in NAV)
    return f'<header class="mast"><p class="brand">BLINK <b>X</b></p><nav class="nav">{nav}</nav></header>'


def bar(no):
    return ('<footer class="bar"><div class="cell"><span class="k">Team</span><span class="v">KhoFra</span></div>'
            '<div class="cell"><span class="k">Challenge</span><span class="v">Planet X and SPHEREx</span></div>'
            '<div class="cell"><span class="k">Data</span><span class="v">NASA SPHEREx · IRSA</span></div>'
            '<div class="cell grow"><span class="k">Try it</span><span class="v ir">khozhijon.github.io/blinkx</span></div>'
            '<div class="cell"><span class="k">Slides made with</span><span class="v">AI assistant (Claude)</span></div>'
            f'<div class="cell"><span class="k">Slide</span><span class="v">{no:02d} / 07</span></div></footer>')


def head(no, title):
    return f'<div class="sec-head"><span class="sec-no">{no:02d}</span><h2>{title}</h2></div>'


def rows(items, on=None):
    return '<div class="rows">' + "".join(f'<div class="row{" on" if i == on else ""}"><strong>{a}</strong><span>{b}</span></div>' for i, (a, b) in enumerate(items)) + "</div>"


def plate(src, alt, cap, label=None):
    lab = f'<b>{label}</b> ' if label else ""
    return f'<figure><div class="plate"><img src="img/{src}" alt="{alt}"></div><figcaption>{lab}{cap}</figcaption></figure>'


doodles = "".join(
    f'<div class="dd" style="--c:{T[k]["color"]}"><span class="g">{glyph[T[k]["label"]]}</span><strong>{T[k]["label"]}</strong><span>{what}</span></div>'
    for k, what in (("arrow", "a nearby star or brown dwarf, sliding steadily"), ("spark", "an asteroid passing through"), ("tail", "a comet"),
                    ("pulse", "a star that changes brightness"), ("zigzag", "the wobble a very distant planet would show")))

tested = [
    ("Barnard's Star", "Arrow: drifting <b class=mono>10.0 ± 1.2″</b> a year, toward the north", "10.39″ a year"),
    ("Epsilon Indi B", "Arrow: <b class=mono>4.6 ± 0.4″</b> a year. Its spectrum shows a brown dwarf's water and methane", "4.68″ a year"),
    ("WISE 0855", "Arrow, found only by adding each visit's exposures together: <b class=mono>8.2 ± 0.6″</b> a year", "8.15″ a year"),
    ("RW Aurigae", "Pulse: <b class=mono>59%</b> brighter in September 2026 than a year before", "young variable star"),
    ("R Draconis", "No doodle: the star overloads the detector, and the tool says it cannot tell", "pulsing red giant"),
]
tested_html = '<div class="rows wide">' + "".join(
    f'<div class="row{" on" if i == 2 else ""}"><strong>{a}</strong><span>{b}</span><em>{c}</em></div>' for i, (a, b, c) in enumerate(tested)) + "</div>"

CSS = r'''
    :root { --void: #050506; --plate: #0b0b0c; --plate-2: #131211; --rule: #26221d; --rule-2: #40382f; --bone: #efe9dd; --bone-2: #aaa294; --bone-3: #746d61; --ir: #ff5a1f; --ir-ink: #150703;
      --f-display: "Instrument Serif", "Iowan Old Style", "Palatino Linotype", Georgia, serif; --f-body: "IBM Plex Sans", "Helvetica Neue", Arial, sans-serif; --f-mono: "IBM Plex Mono", ui-monospace, "SF Mono", Menlo, Consolas, monospace; }
    * { box-sizing: border-box; }
    html, body { margin: 0; background: #000; color: var(--bone); font-family: var(--f-body); -webkit-font-smoothing: antialiased; }
    p, h1, h2, figure { margin: 0; }
    .top { max-width: 1280px; margin: 0 auto; padding: 14px 16px; display: flex; flex-wrap: wrap; gap: 8px 20px; justify-content: space-between; font: 500 11px/1.4 var(--f-mono); letter-spacing: .14em; text-transform: uppercase; color: var(--bone-2); }
    .top a { color: var(--bone); text-decoration-color: var(--ir); text-underline-offset: 3px; }
    .deck { display: grid; gap: 16px; padding: 0 0 32px; justify-content: center; }
    /* Every slide is 16:9 and scales as one piece: sizes inside are in em, and 1em is 1/80 of the slide's width (16px at 1280). */
    .slide { width: min(100vw, 1280px); aspect-ratio: 16 / 9; container-type: inline-size; background: var(--void); position: relative; overflow: hidden; outline: 1px solid var(--rule); }
    .in { font-size: 1.25cqw; position: absolute; inset: 0; display: grid; grid-template-rows: 3.5em minmax(0, 1fr) 3.6em; }
    .mono { font-family: var(--f-mono); font-variant-numeric: tabular-nums; font-weight: 400; }
    /* the website's header */
    .mast { display: flex; align-items: center; gap: 2em; padding: 0 3.1em; border-bottom: 1px solid var(--rule); background: rgba(5, 5, 6, .94); position: relative; z-index: 2; }
    .brand { font: 500 .9em/1 var(--f-mono); letter-spacing: .42em; color: var(--bone); } .brand b { color: var(--ir); font-weight: 500; }
    .nav { margin-left: auto; display: flex; align-items: center; gap: 1.9em; font: 500 .69em/1 var(--f-mono); letter-spacing: .14em; text-transform: uppercase; color: var(--bone-3); }
    .nav .on { color: var(--bone); } .nav .on::before { content: ""; display: inline-block; width: .5em; height: .5em; background: var(--ir); margin-right: .8em; }
    .nav .btn { border: 1px solid var(--rule-2); padding: .95em 1.1em; color: var(--bone); }
    /* the readout bar under the sky map */
    .bar { display: flex; align-items: stretch; border-top: 1px solid var(--rule-2); background: rgba(5, 5, 6, .86); position: relative; z-index: 2; }
    .bar .cell { display: grid; gap: .38em; align-content: center; padding: 0 1.5em; border-right: 1px solid var(--rule); min-width: 0; }
    .bar .cell:first-child { padding-left: 3.1em; } .bar .cell:last-child { border-right: 0; padding-right: 3.1em; } .bar .grow { flex: 1; }
    .bar .k { font: 500 .62em/1 var(--f-mono); letter-spacing: .14em; text-transform: uppercase; color: var(--bone-3); }
    .bar .v { font: 400 .8em/1.25 var(--f-mono); font-variant-numeric: tabular-nums; color: var(--bone); white-space: nowrap; } .bar .v.ir { color: var(--ir); }
    /* a section, with its small orange number */
    .body { padding: 2.2em 3.1em 1.7em; display: flex; flex-direction: column; min-height: 0; }
    .sec-head { display: flex; align-items: baseline; gap: 1em; margin-bottom: 1.5em; }
    .sec-no { font: 500 .78em/1 var(--f-mono); letter-spacing: .1em; color: var(--ir); transform: translateY(-.7em); }
    .sec-head h2 { font: 400 3.4em/1 var(--f-display); letter-spacing: -.01em; } .sec-head h2 em { font-style: italic; color: var(--ir); }
    .cols { display: grid; gap: 2.8em; flex: 1; min-height: 0; align-items: center; }
    /* numbered rows, as in the lists of targets */
    .rows { display: grid; border-top: 1px solid var(--rule); counter-reset: row; }
    .row { display: grid; grid-template-columns: 2.7em minmax(0, 1fr); gap: .15em 0; align-items: baseline; padding: .82em 0; border-bottom: 1px solid var(--rule); counter-increment: row; }
    .row::before { content: counter(row, decimal-leading-zero); font: 500 .7em var(--f-mono); letter-spacing: .1em; color: var(--bone-3); grid-row: span 2; }
    .row strong { font: 400 1.72em/1.12 var(--f-display); color: var(--bone); grid-column: 2; }
    .row span { font-size: 1.05em; color: var(--bone-2); grid-column: 2; line-height: 1.42; } .row span b { color: var(--bone); font-weight: 500; }
    .row.on::before, .row.on strong { color: var(--ir); }
    .rows.wide .row { grid-template-columns: 2.7em 12.5em minmax(0, 1fr) 11.5em; gap: 0 1em; padding: .92em 0; }
    .rows.wide .row::before { grid-row: auto; } .rows.wide .row strong, .rows.wide .row span { grid-column: auto; }
    .rows.wide .row span { font-size: 1.1em; color: var(--bone); } .rows.wide .row b.mono { font-size: .95em; }
    .rows.wide .row em { font: 400 .82em/1.3 var(--f-mono); font-style: normal; color: var(--bone-2); text-align: right; }
    /* step cells, as in "Pick a patch of sky / Watch it change / Read the doodle" */
    .steps { display: grid; border-top: 1px solid var(--rule); border-bottom: 1px solid var(--rule); }
    .steps.h { grid-template-columns: repeat(3, 1fr); } .steps.h > div + div { border-left: 1px solid var(--rule); } .steps.v > div + div { border-top: 1px solid var(--rule); }
    .steps > div { display: grid; gap: .42em; align-content: start; padding: 1.15em 1.4em 1.25em; } .steps.v > div { padding-left: 0; }
    .steps .num { font: 500 .7em var(--f-mono); letter-spacing: .14em; color: var(--ir); }
    .steps strong { font: 400 1.8em/1.1 var(--f-display); color: var(--bone); }
    .steps span:not(.num) { font-size: 1.05em; color: var(--bone-2); line-height: 1.42; } .steps span b { color: var(--bone); font-weight: 500; }
    /* the tab bar of the five views */
    .tabs { display: flex; gap: 2em; border-bottom: 1px solid var(--rule); font: 500 .7em/1 var(--f-mono); letter-spacing: .16em; text-transform: uppercase; color: var(--bone-3); margin-bottom: 1em; }
    .tabs span { padding: 0 0 1em; } .tabs .on { color: var(--bone); box-shadow: inset 0 -2px 0 var(--ir); }
    /* a picture in the instrument's frame */
    .plate { position: relative; border: 1px solid var(--rule-2); background: var(--plate); } .plate img { display: block; width: 100%; height: auto; }
    .plate::before, .plate::after { content: ""; position: absolute; width: 1.1em; height: 1.1em; border: 0 solid var(--bone-2); }
    .plate.crop img { aspect-ratio: 2 / 1; object-fit: cover; object-position: 50% 62%; }
    .plate::before { left: -.5em; top: -.5em; border-width: 1px 0 0 1px; } .plate::after { right: -.5em; bottom: -.5em; border-width: 0 1px 1px 0; }
    figcaption { font: 400 .76em/1.5 var(--f-mono); color: var(--bone-2); margin-top: 1em; } figcaption b { font-weight: 500; letter-spacing: .14em; text-transform: uppercase; color: var(--bone-3); margin-right: .5em; }
    .label { font: 500 .7em/1.3 var(--f-mono); letter-spacing: .14em; text-transform: uppercase; color: var(--bone-2); }
    .tag { display: inline-block; font: 500 .62em/1.2 var(--f-mono); letter-spacing: .12em; text-transform: uppercase; padding: .35em .6em; border: 1px solid var(--bone-2); color: var(--bone); vertical-align: .15em; } .tag.c { color: var(--ir); border-color: var(--ir); }
    .proof { font: 400 .8em/1.6 var(--f-mono); letter-spacing: .02em; color: var(--bone-2); } .title .proof, .title .eyebrow { color: var(--bone); text-shadow: 0 0 .9em rgba(5,5,6,.9); } .proof i { display: inline-block; width: .42em; height: .42em; background: var(--ir); margin: 0 .8em .08em 0; } .proof b { color: var(--bone); font-weight: 400; }
    .cta { display: inline-flex; align-items: center; gap: 1em; padding: 1.25em 1.5em; background: var(--ir); color: var(--ir-ink); font: 500 .84em/1 var(--f-mono); letter-spacing: .16em; text-transform: uppercase; white-space: nowrap; }
    .cta svg { width: 1.3em; height: 1.3em; fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
    .text-btn { font: 500 .74em/1 var(--f-mono); letter-spacing: .12em; text-transform: uppercase; color: var(--bone); border-bottom: 1px solid var(--bone-2); padding: .4em 0; white-space: nowrap; }
    /* slide 1: the landing page */
    .title .sky { position: absolute; inset: 0; background: #000 url(img/sky.jpg) center / cover no-repeat; }
    .title .sky::after { content: ""; position: absolute; inset: 0; background: linear-gradient(90deg, rgba(5,5,6,.88) 0%, rgba(5,5,6,.66) 36%, rgba(5,5,6,.2) 62%, rgba(5,5,6,0) 78%), linear-gradient(0deg, rgba(5,5,6,.8) 0%, rgba(5,5,6,0) 30%), linear-gradient(180deg, rgba(5,5,6,.78) 0%, rgba(5,5,6,0) 15%); }
    .title .in { grid-template-rows: 3.5em minmax(0, 1fr) 5em; } .title .mast { background: none; border-bottom-color: transparent; }
    .title .body { justify-content: flex-end; padding-bottom: 2.3em; position: relative; z-index: 1; }
    .eyebrow { font: 500 .72em/1.5 var(--f-mono); letter-spacing: .16em; text-transform: uppercase; color: var(--bone-2); } .eyebrow i { display: inline-block; width: .45em; height: .45em; background: var(--ir); margin: 0 .9em .1em; }
    .display { font: 400 6.9em/.92 var(--f-display); letter-spacing: -.02em; margin: .14em 0 .22em; } .display em { font-style: italic; color: var(--ir); }
    .lede { font-size: 1.28em; line-height: 1.45; max-width: 30em; }
    .cta-row { display: flex; align-items: center; gap: 1.6em; margin: 1.7em 0 1.1em; }
    .title .bar .v { font-size: .92em; white-space: normal; } .title .bar .k { font-size: .64em; }
    .qr { position: absolute; right: 3.1em; bottom: 2.3em; width: 8.6em; z-index: 1; } .qr img { display: block; width: 100%; border: .45em solid var(--bone); background: var(--bone); }
    .qr p { font: 500 .62em var(--f-mono); letter-spacing: .14em; text-transform: uppercase; margin-top: .8em; color: var(--bone-2); text-align: center; }
    /* slide 4: the five doodles */
    .dds { display: grid; border-top: 1px solid var(--rule); } .dd { display: grid; grid-template-columns: 3.3em 7.6em minmax(0, 1fr); align-items: center; gap: 0 .6em; padding: .28em 0; border-bottom: 1px solid var(--rule); }
    .dd .g { display: grid; place-items: center; } .dd svg { width: 2.9em; height: 2.9em; display: block; }
    .dd strong { font: 400 1.6em/1.1 var(--f-display); color: var(--c); } .dd span:last-child { font-size: 1.02em; color: var(--bone-2); line-height: 1.35; }
    /* slide 6: two charts, each with its reading beside it */
    .spectra { display: grid; gap: 1.5em; } .spectra figure { display: grid; grid-template-columns: minmax(0, 1fr) 13em; gap: 1.5em; align-items: center; }
    .spectra figcaption { margin: 0; } .spectra figcaption strong { display: block; font: 400 2.2em/1.05 var(--f-display); color: var(--bone); margin-bottom: .3em; letter-spacing: 0; }
    /* slide 7 */
    .sources { display: grid; gap: .55em; margin-top: 1.5em; } .sources p:last-child { font: 400 .86em/1.7 var(--f-mono); color: var(--bone); }
    .side { display: grid; gap: 1.2em; justify-items: start; } .phone { width: 9.4em; }
    @page { size: 1280px 720px; margin: 0; }
    @media print {
      html, body { background: var(--void); } .top { display: none; } .deck { display: block; padding: 0; }
      .slide { width: 1280px; height: 720px; aspect-ratio: auto; outline: 0; break-after: page; break-inside: avoid; }
      * { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
    }
'''

ARROW = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m7 7 10 10"/><path d="M17 7v10H7"/></svg>'

slides = []
slides.append(f'''
    <section class="slide title" aria-label="Slide 1 of 7: title">
      <div class="sky"></div>
      <div class="in">
        {mast()}
        <div class="body">
          <p class="eyebrow">NASA SPHEREx <i></i> the whole sky in 102 infrared colours <i></i> every six months</p>
          <h1 class="display">The sky moves.<br><em>Catch it.</em></h1>
          <p class="lede">Blink X lines up real NASA SPHEREx pictures of any spot in the sky, taken months apart, so anyone can see what moved or changed.</p>
          <div class="cta-row"><span class="cta">khozhijon.github.io/blinkx {ARROW}</span><span class="text-btn">Free · in any browser · on a phone</span></div>
          <p class="proof"><i></i>Tested on NASA's five challenge objects. It found <b>WISE 0855, the coldest brown dwarf known</b>, by itself.</p>
          <p class="proof" style="margin-top:.35em"><i></i>Slides and code written with an AI coding assistant (Claude). Every picture is a real screenshot of NASA data.</p>
          <div class="qr"><img src="img/qr.png" alt="QR code for khozhijon.github.io/blinkx"><p>Open the tool</p></div>
        </div>
        <footer class="bar"><div class="cell"><span class="k">Team</span><span class="v">KhoFra</span></div>
          <div class="cell"><span class="k">Team members</span><span class="v">Khozhiakbar Khakimov Furkatzhonovich<br>Francia Constanza Coyotl Cortes</span></div>
          <div class="cell"><span class="k">Challenge</span><span class="v ir">Planet X and SPHEREx</span></div>
          <div class="cell grow"><span class="k">Event</span><span class="v">NASA Space Apps Challenge 2026 · Cambridge, MA</span></div></footer>
      </div>
    </section>''')

slides.append(f'''
    <section class="slide" aria-label="Slide 2 of 7: the challenge">
      <div class="in">
        {mast("Challenge")}
        <div class="body">
          {head(1, "The whole sky, again <em>every six months</em>")}
          <div class="cols" style="grid-template-columns: .86fr 1fr">
            {rows([("A sky that repeats", "NASA's SPHEREx photographs the entire sky every six months, in 102 infrared colours."),
                   ("Something always moves", "Asteroids, comets, nearby stars. Perhaps a planet nobody has seen."),
                   ("But nobody can look", "Each picture is a 62 MB science file that only a specialist can open."),
                   ("The challenge", "Show SPHEREx pictures of any coordinates, and make changes over time easy to see.")], on=3)}
            {plate("side-barnard.jpg", "Two SPHEREx pictures of Barnard's Star, thirteen months apart", "Barnard's Star in August 2025 (A) and September 2026 (B): real SPHEREx pictures, lined up by Blink X. The star has moved 11″ north.", "Side by side")}
          </div>
        </div>
        {bar(2)}
      </div>
    </section>''')

slides.append(f'''
    <section class="slide" aria-label="Slide 3 of 7: the tool">
      <div class="in">
        {mast("Tool")}
        <div class="body">
          {head(2, "Type a name or coordinates. <em>Blink.</em>")}
          <div class="cols" style="grid-template-columns: .74fr 1.26fr">
            <div class="steps v">
              <div><span class="num">01</span><strong>Pick a patch of sky</strong><span>A star, a galaxy or coordinates. Blink X finds <b>every SPHEREx exposure</b> of that spot.</span></div>
              <div><span class="num">02</span><strong>Watch it change</strong><span>Real NASA pictures from different dates, lined up. Every date is read from the image file.</span></div>
              <div><span class="num">03</span><strong>Read the doodle</strong><span>Everything that moved or changed becomes a simple drawing you can share.</span></div>
            </div>
            <figure>
              <div class="tabs"><span>Blink</span><span>Swipe</span><span class="on">Side by side</span><span>Difference</span><span>Time-lapse</span></div>
              <div class="plate crop"><img src="img/viewer-comet.jpg" alt="The Blink X viewer showing comet 3I/ATLAS in two exposures"></div>
              <figcaption><b>On screen</b> Interstellar comet 3I/ATLAS, 14 December 2025: two exposures three hours apart. The green doodle was drawn by the tool.</figcaption>
            </figure>
          </div>
        </div>
        {bar(3)}
      </div>
    </section>''')

slides.append(f'''
    <section class="slide" aria-label="Slide 4 of 7: Sky Doodles">
      <div class="in">
        {mast("Doodles")}
        <div class="body">
          {head(3, "Sky Doodles: the tool finds <em>what changed</em>")}
          <div class="cols" style="grid-template-columns: 1fr .6fr .66fr; gap: 2.2em">
            <div>
              <div class="dds">{doodles}</div>
              <p class="proof" style="margin-top:1.3em"><i></i>Each doodle has an <b>Object Card</b>: speed with its error, direction, and a check against JPL Horizons, IMCCE SkyBoT and SIMBAD.</p>
              <p class="proof" style="margin-top:.7em"><i></i><span class="tag">Known</span> has a catalogue name. Everything else is a <span class="tag c">Candidate</span>, never a “discovery”.</p>
            </div>
            {plate("wise-stage.jpg", "WISE 0855 in added-up SPHEREx exposures, with its arrow doodle", "WISE 0855, the coldest brown dwarf known: too faint for one exposure, found by adding each visit's exposures together.", "Found")}
            {plate("wise-card.jpg", "The Object Card of WISE 0855", "Named from SIMBAD. Catalogue: 8.15″ a year. These pictures: 8.2 ± 0.6.", "Its card")}
          </div>
        </div>
        {bar(4)}
      </div>
    </section>''')

slides.append(f'''
    <section class="slide" aria-label="Slide 5 of 7: tested on the challenge's five objects">
      <div class="in">
        {mast("Tested")}
        <div class="body">
          {head(4, "Tested on the challenge's <em>five objects</em>")}
          <div class="cols" style="grid-template-columns: 1fr; align-content: center; gap: 1.5em">
            <div>
              <p class="label" style="display:flex;justify-content:space-between;padding:0 0 .9em 2.7em"><span>What Blink X reports by itself</span><span>Catalogue</span></p>
              {tested_html}
            </div>
            <p class="proof"><i></i>Also found by itself on real data: the interstellar comet <b>3I/ATLAS</b>, 175″ an hour and glowing where carbon dioxide does (4.26 µm), and the asteroids <b>Vesta</b> and <b>Psyche</b>.</p>
          </div>
        </div>
        {bar(5)}
      </div>
    </section>''')

slides.append(f'''
    <section class="slide" aria-label="Slide 6 of 7: spectra on the fly">
      <div class="in">
        {mast("Spectra")}
        <div class="body">
          {head(5, "One click: the <em>whole spectrum</em> of any spot")}
          <div class="cols" style="grid-template-columns: .52fr 1fr; gap: 2.6em">
            {rows([("100 exposures", "From all six SPHEREx detectors, measured on the spot: 0.75 to 5 µm, on the fly."),
                   ("It follows the object", "A star or brown dwarf that drifts is tracked along its drift."),
                   ("Honest dots", "Light that is not the object's own is drawn hollow. The numbers download as CSV.")])}
            <div class="spectra">
              <figure><div class="plate"><img src="img/spectrum-eps.png" alt="Spectrum of Epsilon Indi B from 0.75 to 5 micrometres"></div><figcaption><strong>Epsilon Indi B</strong>Dips where water (1.4 and 1.9 µm) and methane (3.3 µm) absorb: the fingerprint of a brown dwarf.</figcaption></figure>
              <figure><div class="plate"><img src="img/spectrum-wise.png" alt="Spectrum of WISE 0855"></div><figcaption><strong>WISE 0855</strong>Its own light only beyond 3.8 µm, about 0.6 mJy. The hollow dots are a neighbouring star's.</figcaption></figure>
            </div>
          </div>
        </div>
        {bar(6)}
      </div>
    </section>''')

slides.append(f'''
    <section class="slide" aria-label="Slide 7 of 7: built on NASA's open data, and what comes next">
      <div class="in">
        {mast("Data")}
        <div class="body">
          {head(6, "Built on <em>NASA's open data</em>")}
          <div class="cols" style="grid-template-columns: 1fr 10.4em; gap: 2.6em">
            <div>
              <div class="steps h">
                <div><span class="num">01</span><strong>How it works</strong><span>NASA/IPAC's IRSA archive says which SPHEREx images cover a spot. Blink X reads <b>only the bytes it needs</b> from NASA's open copy on AWS.</span></div>
                <div><span class="num">02</span><strong>Never stuck</strong><span>Our record of all <b>101,101 SPHEREx pointings</b> finds 99.9% of the exposures, even when the archive's search is down.</span></div>
                <div><span class="num">03</span><strong>What comes next</strong><span>A shared list where volunteers flag candidates for astronomers. Each new SPHEREx release adds <b>another date</b> to every spot.</span></div>
              </div>
              <div class="sources">
                <p class="label">NASA and space-agency data behind every picture and check</p>
                <p>NASA SPHEREx Level-2 images · NASA/IPAC IRSA · AWS Open Data · JPL Horizons · NASA WISE · ESA Gaia DR3 · CDS SIMBAD and Aladin Lite · IMCCE SkyBoT</p>
              </div>
              <p class="proof" style="margin-top:1.2em"><i></i>Open source (MIT), 34 automatic tests. Code and slides written with an AI coding assistant (Claude). <b>No picture, date or measurement is AI-generated.</b></p>
            </div>
            <div class="side">
              <figure class="phone"><div class="plate"><img src="img/phone.jpg" alt="Blink X on a phone"></div><figcaption><b>On a phone</b></figcaption></figure>
            </div>
          </div>
        </div>
        {bar(7)}
      </div>
    </section>''')

html = f'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Blink X — project slides (Team KhoFra, NASA Space Apps 2026), made with an AI assistant</title>
  <meta name="description" content="Seven slides about Blink X, a public tool that shows NASA SPHEREx images of any spot in the sky over time. NASA Space Apps Challenge 2026, team KhoFra.">
  <meta name="author" content="Khozhiakbar Khakimov Furkatzhonovich, Francia Constanza Coyotl Cortes (Team KhoFra)">
  <meta name="ai-assistance" content="These slides and the project's code were written with an AI coding assistant (Claude, by Anthropic). Every picture is a real screenshot of the tool showing NASA data; none is AI-generated.">
  <link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' fill='%23050506'/%3E%3Ccircle cx='16' cy='16' r='9' fill='none' stroke='%23efe9dd' stroke-width='1.5'/%3E%3Cpath d='M16 2v8M16 22v8M2 16h8M22 16h8' stroke='%23efe9dd' stroke-width='1.5'/%3E%3Ccircle cx='20' cy='12' r='3' fill='%23ff5a1f'/%3E%3C/svg%3E">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&family=Instrument+Serif:ital@0;1&display=swap">
  <style>{CSS}  </style>
</head>
<body>
  <div class="top"><span>Blink X · seven slides · Team KhoFra · NASA Space Apps 2026</span><span><a href="blinkx-slides.pdf">PDF</a> · <a href="../">Open the tool ↗</a></span></div>
  <main class="deck">
{"".join(slides)}

  </main>
</body>
</html>
'''
(ROOT / "frontend/slides/index.html").write_text(html)
print("written", len(html), "bytes;", html.count('<section class="slide'), "slides")
