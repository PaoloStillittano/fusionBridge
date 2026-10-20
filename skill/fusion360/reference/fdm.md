# FDM design rules (Bambu Lab A1)

Tables below assume the default setup: **0.4 nozzle, PLA**. For 0.2 nozzle, PETG and the
smooth plate see [Printer options](#printer-options) at the end.

Starting values: tolerances depend on printer, material and slicer. When a fit matters,
put the clearance in a user parameter (`h.param('clr', 0.25)`) so it can be calibrated,
and suggest a small test print of the critical feature first.

## Walls and features
| Thing | Value |
|---|---|
| Wall thickness | multiples of the line width: 0.8 / 1.2 / 1.6 / 2.0 mm. Structural parts >= 2 mm |
| Top/bottom skins | >= 0.8 mm (4 layers at 0.2) |
| Smallest feature / pin | 0.8 mm (thin), 2 mm+ if it must survive handling |
| Layer height | 0.2 mm typical: vertical dimensions as multiples of 0.2 print most accurately |
| Embossed/engraved text | height >= 5 mm, depth/relief 0.6-1 mm, bold sans font. On top faces, not on the bed face |

## Fits (clearance per side unless noted)
| Fit | Clearance |
|---|---|
| Press fit | 0.05-0.1 mm |
| Snug / friction (lids) | 0.15-0.2 mm |
| Sliding / rotating | 0.25-0.3 mm |
| Print-in-place moving parts | 0.3-0.5 mm gap |
| Holes | print ~0.1-0.2 mm smaller than modeled: model +0.2 mm on the diameter |

## Fasteners (metric)
| Size | Clearance hole | Tap for self-tapping screw | Heat-set insert hole (typical) | Hex nut across flats (+0.3 for the trap) | Head counterbore |
|---|---|---|---|---|---|
| M2 | 2.4 | 1.8 | 3.2 x 4 deep | 4.0 | 4.2 |
| M2.5 | 2.9 | 2.2 | 3.6 x 4.5 | 5.0 | 5.0 |
| M3 | 3.4 | 2.6 | 4.0-4.2 x 5.5 | 5.5 | 6.0 (cap head 5.5 + 0.5) |
| M4 | 4.5 | 3.4 | 5.6 x 7 | 7.0 | 8.0 |
| M5 | 5.5 | 4.3 | 6.4 x 8 | 8.0 | 9.5 |
Insert hole sizes vary by brand: put them in parameters. Boss around an insert: >= 2 mm wall.
Nut traps: `h.polygon(sk, 6, 5.5 + 0.3, flats=True)`.

## Overhangs, bridges, orientation
- Overhangs up to ~45 deg from vertical print without support. `f360 fdm` reports anything steeper.
- Bridges (flat ceilings) up to ~10 mm print fine, longer ones sag.
- Edges on the bed: **chamfer 0.4-0.8 mm** (avoids elephant foot, helps removal). Don't fillet
  bottom edges: the lower part of a fillet is an overhang. Fillets are fine on vertical edges
  and top edges.
- Horizontal holes (axis parallel to the bed): teardrop shape (45 deg peak on top) or
  accept a slightly sagged top; for d <= 5 mm it's usually fine.
- Ceilings of horizontal holes/slots: a 45 deg chamfer instead of a flat ceiling.
- Strength: layers are the weak plane. Orient so loads run *along* layers, not pulling them
  apart (e.g. a hook printed lying flat, not standing up). Clips/snap-fits: flex in the XY plane.
- Large flat parts warp: round the corners on the bed (fillet the vertical corner edges), add a brim.

## Snap fits (cantilever)
- Length >= 5x thickness, thickness 1.2-2 mm, hook depth 0.5-1 mm, 30-45 deg lead-in.
- PETG/PLA: PETG forgives much more. Print with the beam in the XY plane.

## Enclosures
- Walls 1.6-2.4 mm, lid lip/groove with 0.2 mm clearance per side.
- Screw bosses: outer d = 2.5x screw d, tie them to the walls with ribs.
- Ventilation slots on top: width <= 2 mm or bridges become a problem.
- Cable/connector cutouts: +0.5 mm per side over the nominal connector size.

## Before export
1. `f360 fdm --bed <printer>`: no `No flat face on the bed`, overhangs either intended
   (supports) or redesigned.
2. `f360 tree`: every body `solid: true`, no `feature_problems`.
3. Export `.3mf` (keeps units, best for Bambu/Prusa/Orca) or `.stl` binary; `--each` for
   multi-part prints. Tell the user which orientation the part was modeled in.

## Printer options

### Nozzle: 0.4 (default) vs 0.2
| | 0.4 | 0.2 |
|---|---|---|
| Line width | ~0.42 | ~0.22 |
| Walls | 0.8 / 1.2 / 1.6 / 2.0 | 0.4 / 0.6 / 0.8 / 1.2 |
| Smallest feature | 0.8 | 0.4 |
| Layer height | 0.2 (0.12-0.28) | 0.1 (0.06-0.14) |
| Text | >= 5 mm high, 0.6-1 relief | >= 2.5 mm high, 0.3-0.5 relief |
| Clearances | tables above | about 0.05 mm less per side (sliding 0.15-0.2) |
| Print time | 1x | ~3-4x: only for small parts (roughly < 50 mm) |

Suggest the 0.2 only when the part needs it: features < 0.8 mm, text < 5 mm, miniatures,
small precise mechanisms. Never mix: a part designed for 0.2 can fail with 0.4 (walls too thin).

### Material: PLA (default) vs PETG
| | PLA | PETG |
|---|---|---|
| Choose for | indoor, rigid, precise, aesthetic | outdoor/UV, heat (softens ~75 deg C vs ~55 for PLA: car, near motors/electronics), water, impact, parts that flex |
| Clearances | tables above | +0.05 mm per side (prints slightly fatter, strings) |
| Overhangs / bridges | 45 deg, bridges <= 10 mm | keep <= 40 deg, bridges <= 8 mm |
| Snap fits / clips | brittle: thicker beam, small deflection | forgiving: preferred material |
| Supports | easy to remove | bond hard to the part: design them out |

Suggest PETG when the function needs it (with the reason); otherwise PLA.

### Plate: textured PEI (default) vs smooth PEI
The plate doesn't change the geometry, only the bottom finish and therefore the orientation.
- **Textured**: matte textured bottom, hides first-layer flaws, easy release. Good default, also for PETG.
- **Smooth**: glossy, flat bottom. Choose it when the face on the bed is the **visible** one
  (tags, signs, logos, flat decorative faces): orient the part with that face down.
  Details on that face must be **engraved** (0.4-0.6 mm), not embossed.
  With PETG use glue stick as a release agent (PETG can bond too strongly to smooth PEI).
