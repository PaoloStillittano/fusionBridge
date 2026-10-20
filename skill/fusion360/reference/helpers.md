# `h` helper reference

Lengths: number = mm, string = Fusion expression (`'wall*2'`, `'3 mm'`). Angles: number = deg.
Points: `(x, y)` sketch mm, `(x, y, z)` model mm (projected into the sketch).
All functions return native Fusion objects.

## Values & context
| Function | Notes |
|---|---|
| `h.param(name, expr, unit='mm', comment='')` | create/update a user parameter. Avoid names that are units (`m`, `t`, `in`, `ft`, `deg`) |
| `h.length(v)`, `h.angle(v)` | -> `ValueInput` |
| `h.pt(x, y, z=0)` | model `Point3D` from mm |
| `h.mm(cm)` | internal cm -> mm |
| `h.items(x)`, `h.coll(x)` | list / `ObjectCollection` from anything |
| `h.design()`, `h.root()`, `h.app()` | context |

## Planes, sketches
| Function | Notes |
|---|---|
| `h.plane('xy'\|'xz'\|'yz')`, `h.axis('x'\|'y'\|'z')` | construction planes/axes of root (or `comp=`) |
| `h.offset_plane(base='xy', dist, name=)` | offset construction plane |
| `h.sketch(on='xy', name=, project=False)` | `on`: plane name, construction plane or planar face (e.g. `h.top_face(body)`). Face edges are not projected unless `project=True` |
| `h.to_sketch(sk, x, y, z)` | model mm -> sketch (x, y) mm |

## Sketch geometry
| Function | Notes |
|---|---|
| `h.rect(sk, w, h, center=(0,0))` | center rectangle |
| `h.rect2(sk, p1, p2)` | two corners |
| `h.circle(sk, d, center)` | **diameter** |
| `h.poly(sk, pts, close=True)` | connected polyline |
| `h.polygon(sk, n, d, center, flats=False, rotation=0)` | regular polygon; `flats=True`: d is across flats (hex nuts) |
| `h.slot(sk, length, width, center, rotation=0)` | obround slot, length end to end |
| `h.line(sk, p1, p2)`, `h.arc(sk, p1, mid, p2)` | `line` accepts SketchPoints (`l.endSketchPoint`) to connect curves |
| `h.spline(sk, pts, closed=False)` | fitted spline through points (SketchPoints allowed) |
| `h.text(sk, s, height, center, width=None, font=None, bold=False)` | `SketchText`, extrude it directly |
| `h.profiles(sk)`, `h.profile(sk, 'largest'\|'smallest'\|i)` | pick profiles |

## Features
`op`: `'new' | 'join' | 'cut' | 'intersect' | 'component'`.

| Function | Notes |
|---|---|
| `h.extrude(prof, dist, op='new', symmetric=False, reverse=False, taper=None, bodies=None, name=)` | `prof`: profile, list, whole sketch, or SketchText. Negative dist = other side. `bodies=` limits a cut/join |
| `h.revolve(prof, axis_='z', deg=360, op=, name=)` | axis must lie in the sketch plane (sketch line or construction axis) |
| `h.loft(sections, op=, solid=True)` | profiles or sketches (largest profile), bottom to top |
| `h.sweep(prof, path_curve, op=)` | path = sketch curve |
| `h.fillet(edges, r)`, `h.chamfer(edges, d)` | edges: one, list or collection |
| `h.shell(target, thickness, inside=True)` | target = faces to remove (open box) or body (hollow) |
| `h.combine(target, tools, op='cut', keep_tools=False)` | boolean between bodies |
| `h.move(bodies, dx, dy, dz)`, `h.rotate(bodies, deg, axis_='z', origin=(0,0,0))` | |
| `h.mirror(entities, plane_='yz')` | bodies or features |
| `h.pattern_circular(entities, count, axis_='z', total_deg=360)` | |
| `h.pattern_rect(entities, n1, d1, dir1='x', n2=1, d2=0, dir2='y')` | d = spacing |

Feature -> body: `f.bodies.item(0)`. Rename: `body.name = 'lid'`.

## Bodies & selection
| Function | Notes |
|---|---|
| `h.bodies()`, `h.body(name=None)` | all bodies / by name / last root body |
| `h.bbox(entity)` | `{'min','max','size'}` in mm |
| `h.edges(body, where=fn)`, `h.faces(body, where=fn)` | filter with a lambda |
| `h.faces_facing(body, '+z')` | planar faces by normal (`'+x'`, `'-z'`, `(x,y,z)`) |
| `h.top_face(body)`, `h.bottom_face(body)` | highest/lowest planar face |
| `h.edges_at_z(body, z)`, `h.top_edges(body)`, `h.bottom_edges(body)` | edges lying at a height |
| `h.edges_along(body, 'z')` | straight edges parallel to an axis (box corners) |
| `h.circular_edges(body, d=None)` | holes/bosses, optionally by diameter |
| `h.normal(face)` | (x, y, z) |

Custom selections: `h.edges(b, lambda e: h.bbox(e)['min'][0] > 10)`.
