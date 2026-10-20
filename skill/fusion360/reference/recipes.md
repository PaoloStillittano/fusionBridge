# Recipes

Starting points, not templates: adapt dimensions, then verify with `f360 shot` and `f360 tree`.
Each block is one `f360 exec` step. All parts sit on Z=0 in their print orientation.

## L-bracket with screw holes (mechanical)

```python
h.param('thick', 4); h.param('hole', 4.5, comment='M4 clearance')
# L profile drawn in model coords on the XZ plane, extruded 30 mm across
sk = h.sketch('xz', name='L_profile')
h.poly(sk, [(0, 0, 0), (40, 0, 0), (40, 0, 4), (4, 0, 4), (4, 0, 40), (0, 0, 40)])
br = h.extrude(sk, 30, name='bracket').bodies.item(0)
br.name = 'bracket'
bb = h.bbox(br); yc = (bb['min'][1] + bb['max'][1]) / 2   # extrude side depends on plane normal
result = bb
```

```python
br = h.body('bracket'); bb = h.bbox(br); yc = (bb['min'][1] + bb['max'][1]) / 2
# holes in the base: sketch on XY, symmetric cut so the direction doesn't matter
sk = h.sketch('xy', name='base_holes'); h.circle(sk, 4.5, center=(26, yc))
h.extrude(h.profiles(sk), 20, op='cut', symmetric=True, bodies=[br])
# holes in the upright: sketch on YZ with model coords
sk = h.sketch('yz', name='upright_holes'); h.circle(sk, 4.5, center=(0, yc, 26))
h.extrude(h.profiles(sk), 20, op='cut', symmetric=True, bodies=[br])
# inner corner fillet (stress relief), then bottom chamfer
inner = [e for e in h.edges_along(br, 'y')
         if abs(h.bbox(e)['min'][0] - 4) < 0.01 and abs(h.bbox(e)['min'][2] - 4) < 0.01]
h.fillet(inner, 3)
h.chamfer(h.bottom_edges(br), 0.5)
```
Print tip: lying on its side (layers along both legs) is much stronger than standing as an L.

## Box with a press-fit lid (enclosure)

```python
h.param('wall', 2); h.param('clr', 0.2, comment='lid clearance per side')
L, W, H, R = 80, 60, 40, 4
sk = h.sketch('xy', name='box_outline'); h.rect(sk, L, W)
box = h.extrude(sk, H).bodies.item(0); box.name = 'box'
h.fillet(h.edges_along(box, 'z'), R)
h.shell(h.top_face(box), 'wall')                 # remove the top face, walls inward
h.chamfer(h.bottom_edges(box), 0.6)
```

```python
L, W, R, wall, clr = 80, 60, 4, 2, 0.2
X = L + 15                                        # lid printed next to the box
sk = h.sketch('xy', name='lid_plate'); h.rect(sk, L, W, center=(X, 0))
lid = h.extrude(sk, 2).bodies.item(0); lid.name = 'lid'
h.fillet(h.edges_along(lid, 'z'), R)
sk = h.sketch(h.top_face(lid), name='lid_lip')
h.rect(sk, L - 2 * (wall + clr), W - 2 * (wall + clr), center=(X, 0, 2))
h.extrude(h.profile(sk), 3, op='join', bodies=[lid])
lip_edges = [e for e in h.edges_along(lid, 'z') if h.bbox(e)['min'][2] > 2 - 0.01]
h.fillet(lip_edges, R - wall - clr)
```
Then `f360 shot -v iso,iso_bottom`, `f360 fdm`, `f360 export out/box.3mf --each`.
(The lid is printed lip-up; flip it in the slicer if you prefer the lip down.)

## Revolved vase (aesthetic)

```python
sk = h.sketch('xz', name='vase_profile')             # model coords (x, 0, z)
base = h.line(sk, (0, 0, 0), (35, 0, 0))
wall = h.spline(sk, [base.endSketchPoint, (44, 0, 35), (30, 0, 85), (24, 0, 115), (31, 0, 140)])
top = h.line(sk, wall.endSketchPoint, (0, 0, 140))
axis_line = h.line(sk, top.endSketchPoint, base.startSketchPoint)
vase = h.revolve(h.profile(sk), axis_line, 360, name='vase').bodies.item(0); vase.name = 'vase'
h.shell(h.top_face(vase), 1.6)
```
Alternative: keep it solid and print in the slicer's "spiral vase" mode (single wall, no shell).
Iterate on the shape: change the spline points, `f360 rollback`, rerun, compare shots
`-v front,iso --style shaded`.

## Twisted lofted planter (aesthetic)

```python
secs = []
for i, (z, d, rot) in enumerate([(0, 60, 0), (45, 78, 20), (90, 58, 40), (120, 70, 60)]):
    pl = h.plane('xy') if z == 0 else h.offset_plane('xy', z, name='sec%d' % i)
    sk = h.sketch(pl, name='sec%d' % i)
    h.polygon(sk, 6, d, rotation=rot)
    secs.append(h.profile(sk))
pot = h.loft(secs, name='planter').bodies.item(0); pot.name = 'planter'
h.shell(h.top_face(pot), 2)
```
Check overhangs: `f360 fdm` (the sections must not lean out more than ~45 deg).

## Name tag with raised text

```python
sk = h.sketch('xy', name='tag'); h.slot(sk, 60, 20); h.circle(sk, 5, center=(-22, 0))
tag = h.extrude(h.profile(sk, 'largest'), 3).bodies.item(0); tag.name = 'tag'
h.chamfer(h.bottom_edges(tag), 0.4)
sk = h.sketch(h.top_face(tag), name='label')
txt = h.text(sk, 'HELLO', 8, center=(5, 0, 3), bold=True)
h.extrude(txt, 0.8, op='join', bodies=[tag])
```

## Tuning a finished part

```bash
f360 params                                   # see what's parametric
f360 params --set clr '0.3 mm' --set wall '2.4 mm'
f360 shot -o shots/after.png -v iso
```
