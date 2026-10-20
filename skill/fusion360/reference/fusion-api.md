# Raw Fusion API: patterns and gotchas

Use the raw API when `h` doesn't cover something. Check signatures with
`f360 api <Class>.<member>` (docs from the running Fusion) and search with `f360 api --search`.
Online: "Fusion API Reference Manual" on help.autodesk.com.

## Units
- Internal lengths are **cm**, angles **radians**, whatever the document units.
- `adsk.core.ValueInput.createByReal(0.3)` = 3 mm. `createByString('3 mm')` is unit-safe and
  can reference parameters (`'wall + 0.2 mm'`).
- `body.volume` cm^3, `body.area` cm^2, `boundingBox` cm.

## Common objects
```python
root.sketches, root.features, root.bRepBodies, root.constructionPlanes, root.occurrences
f = root.features
f.extrudeFeatures, f.revolveFeatures, f.loftFeatures, f.sweepFeatures, f.holeFeatures,
f.filletFeatures, f.chamferFeatures, f.shellFeatures, f.combineFeatures, f.moveFeatures,
f.mirrorFeatures, f.circularPatternFeatures, f.rectangularPatternFeatures, f.threadFeatures,
f.draftFeatures, f.splitBodyFeatures, f.offsetFacesFeatures, f.thickenFeatures
```
Pattern: `inp = feats.createInput(...)`, set options on `inp`, `feats.add(inp)`.

## Sketch constraints and dimensions (when you need a robust parametric sketch)
```python
lines = h.rect(sk, 40, 20)
gc, dims = sk.geometricConstraints, sk.sketchDimensions
gc.addHorizontal(lines[0]); gc.addVertical(lines[1])
d = dims.addDistanceDimension(lines[0].startSketchPoint, lines[0].endSketchPoint,
        adsk.fusion.DimensionOrientations.HorizontalDimensionOrientation, h.pt(0, -15))
d.parameter.expression = 'width'
```

## Components (multi-part designs: box + lid, assemblies)
```python
occ = root.occurrences.addNewComponent(adsk.core.Matrix3D.create())
lid = occ.component; lid.name = 'lid'
sk = h.sketch('xy', comp=lid)      # helpers accept comp=
```
Bodies from occurrences are proxies (world coordinates) and are listed by `h.bodies()`.

## Holes and threads
- For FDM, a plain cut cylinder (with clearance from fdm.md) is usually better than
  `holeFeatures`. Modeled threads only for >= M8; smaller: heat-set inserts or self-tapping.
- `threadFeatures`: `f360 api ThreadFeatures` and `ThreadDataQuery` for sizes; set
  `isModeled = True` to get real geometry for printing.

## Timeline
- `design.timeline` count/items; `markerPosition`; `f360 rollback N` deletes from N on.
- `feature.healthState` / `timelineObject.errorOrWarningMessage` explain failures; they come
  back in `feature_problems` after `exec`.

## Typical errors
- `RuntimeError: 3 : invalid argument` -> wrong type (Point3D vs SketchPoint, a list
  instead of an ObjectCollection) or a value in mm passed where cm was expected.
- `... No target body found to cut or intersect` -> the cut doesn't touch the body: check
  extrude direction (`reverse=True`) and the sketch plane offset.
- Fillet/chamfer `compute failed` -> radius too big for an adjacent face, or edges that
  produce an impossible blend. Reduce, split into several features, or fillet before shelling.
- Loft fails -> sections with different numbers of curves/vertices in incompatible order;
  try splines or fewer sections, or rails.
- An empty `profiles` -> the sketch isn't closed (gaps) or curves overlap.
