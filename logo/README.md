# Aperture — brand identity

## The concept

An aperture is a mechanism that controls how much light gets through. Aperture the product
controls how much credit access gets through — and the whole thesis is that the gate should open
wider without breaking.

The mark is **four blades pinwheeled around a square opening**. Not a camera iris, which is the
obvious and overused reading of the name, but a mechanical shutter reduced to its essential
geometry: four identical elements, offset, leaving a gap at every corner and a clear square of
negative space at the centre.

The four blades are not decorative. They are the product's architecture — **risk, affordability,
evidence coverage, manipulation** — four independent assessments arranged around a single
opening, none of them touching, converging on one decision. The negative space in the middle is
what the system produces: the decision, and the applicants who get through it.

**One blade is teal; three are ink.** The teal blade is the one that moves — the marginal
applicant a bureau model cannot see, admitted because the gate opened rather than because a rule
was weakened.

## Geometry

Everything sits on a **4-unit grid** inside a 100×100 artboard.

| | |
|---|---|
| Blade | 36 × 12 units, fully rounded caps (rx 6) |
| Blade rotation | 0°, 90°, 180°, 270° about centre |
| Corner gap | 4 units — one grid unit |
| Central opening | 20 × 20 units |
| Mark bounding box | 60 × 60 units, optically centred |
| Wordmark cap height | 30 units — exactly half the mark height |
| Mark-to-wordmark gap | 22 units |

The half-height relationship between cap height and mark is what keeps the lockup balanced at any
size. Do not adjust one without the other.

## Colour

| Role | Name | HEX | Use |
|---|---|---|---|
| Primary | Aperture Ink | `#0F1D2E` | Blades, wordmark, dark surfaces |
| Accent | Aperture Teal | `#109E77` | The single moving blade, light backgrounds |
| Accent (dark bg) | Aperture Teal Light | `#2FBE95` | The moving blade on ink |
| Neutral | Mist | `#F2F5F4` | Blades and wordmark on ink |

Two colours only. Ink is a desaturated navy rather than black — black reads flat and cheap in
fintech; navy carries institutional weight without looking like a bank from 1994. The teal is
pulled toward green rather than cyan: growth and money, not tech-startup gradient.

## Typography

The wordmark is **custom-drawn vector artwork**, not a licensed or system typeface. Every letter
is constructed on the same grid as the symbol, from the same two primitives the blades use: a
straight segment and a true circular arc. There is no font file to license, embed or lose.

**The concept.** In type design, *aperture* is the technical term for the opening between a
letter's terminal and its body — the gap in a c, an s, an e. So the wordmark is drawn with
deliberately **wide open apertures**: the `e` terminal is cut at −44°, well short of closing, and
the `r` arm stops at 52° rather than curling in. The brand name describes its own letterforms.
That is the tie to the symbol — not a decorative flourish, but the same idea (a controlled
opening) expressed in two different mediums.

**Construction**

| | |
|---|---|
| Cap height | 30 units — exactly half the symbol height |
| x-height | 22 units (0.74 of cap) — tall, modern, keeps colour even |
| Stroke | 4.85 units, monoline — identical on stems, bowls and diagonals |
| Bowl | True circle, radius 8.6 — no optical ellipses |
| Terminals | Flat cut, perpendicular to the stroke |
| Joins | Mitred at the `A` apex only |

**Custom details, kept restrained**

- **`A`** — low crossbar at 33% of cap height, sharp mitred apex. Technical rather than
  classical; it keeps the counter open and wide, matching the letters that follow.
- **`e`** — horizontal bar on the exact centre line, terminal cut short and high.
- **`r`** — quarter-arc arm that stops before it turns down, leaving air under it.
- **`t`** — full-height ascender with an asymmetric crossbar and a quarter-circle tail, the only
  curve in the wordmark that isn't part of a full circle.

Monoline throughout means the wordmark holds its colour beside the symbol's solid pill blades
instead of competing with them. Nothing is a font default; nothing is decorative.

## Files

| File | Use |
|---|---|
| `aperture-logo.svg` / `.png` | Primary lockup, light backgrounds |
| `aperture-logo-dark.svg` / `.png` | Lockup for dark backgrounds |
| `aperture-logo-mono.svg` | Single-colour lockup — print, embossing, fax-grade contexts |
| `aperture-icon.svg` / `.png` | Transparent app icon, 1024px PNG |
| `aperture-icon-dark.svg`, `aperture-icon-mono.svg` | Icon variants |
| `aperture-favicon.svg` | Squircle tile, ink background — favicon and social avatar |
| `aperture-favicon-512/64/32.png` | Rasterised tiles |

PNGs have transparent backgrounds except the favicon tiles, which carry the ink squircle.

## Rules

- **Clear space** on all sides equals one blade width (12 units, 20% of mark height).
- **Minimum size:** lockup 96px wide; icon 16px. Below 96px, use the icon alone.
- Never recolour individual blades beyond the specified two-tone. Never make all four teal.
- Never rotate the mark. The pinwheel offset is directional and reads as broken when tilted.
- Never add a stroke, shadow, gradient or glow.
- Never stack the wordmark under the mark — the horizontal lockup is the only lockup.
- On photography or busy backgrounds, use the favicon tile, not the transparent icon.
