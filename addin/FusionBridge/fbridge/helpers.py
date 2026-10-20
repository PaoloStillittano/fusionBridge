"""Modeling helpers, available as `h` inside `f360 exec`.

Conventions
- Lengths: numbers are mm; strings are Fusion expressions ("wall*2", "3 mm", "d/2").
- Angles: numbers are degrees; strings are expressions ("30 deg").
- Sketch points: (x, y) are sketch coordinates in mm. (x, y, z) are model coordinates
  in mm, projected into the sketch (use these on xz / yz planes and on faces).
  line() and spline() also accept existing SketchPoints, e.g. other_line.endSketchPoint.
- +Z is the print direction; the bed is the XY plane.
Everything returns the native Fusion object, so you can drop down to the raw API at any point.
"""
import math

import adsk.core
import adsk.fusion

_OPS = {
    'new': adsk.fusion.FeatureOperations.NewBodyFeatureOperation,
    'join': adsk.fusion.FeatureOperations.JoinFeatureOperation,
    'cut': adsk.fusion.FeatureOperations.CutFeatureOperation,
    'intersect': adsk.fusion.FeatureOperations.IntersectFeatureOperation,
    'component': adsk.fusion.FeatureOperations.NewComponentFeatureOperation,
}
_DIRS = {'+x': (1, 0, 0), '-x': (-1, 0, 0), '+y': (0, 1, 0), '-y': (0, -1, 0),
         '+z': (0, 0, 1), '-z': (0, 0, -1), 'x': (1, 0, 0), 'y': (0, 1, 0), 'z': (0, 0, 1)}


# ---------------------------------------------------------------- context & values

def app():
    return adsk.core.Application.get()


def design():
    d = adsk.fusion.Design.cast(app().activeProduct)
    if d is None:
        raise RuntimeError('No active Fusion design')
    return d


def root():
    return design().rootComponent


def _comp(c):
    return c if c is not None else root()


def length(v):
    """ValueInput for a length: number = mm, string = expression."""
    if isinstance(v, adsk.core.ValueInput):
        return v
    if isinstance(v, str):
        return adsk.core.ValueInput.createByString(v)
    return adsk.core.ValueInput.createByReal(float(v) / 10.0)


def angle(v):
    """ValueInput for an angle: number = degrees, string = expression."""
    if isinstance(v, adsk.core.ValueInput):
        return v
    if isinstance(v, str):
        return adsk.core.ValueInput.createByString(v)
    return adsk.core.ValueInput.createByReal(math.radians(float(v)))


def mm(cm_value):
    """Fusion internal length (cm) -> mm."""
    return cm_value * 10.0


def pt(x, y, z=0.0):
    """Model-space Point3D from mm."""
    return adsk.core.Point3D.create(x / 10.0, y / 10.0, z / 10.0)


def items(x):
    """Normalize a single object, list, ObjectCollection or Fusion collection to a list."""
    if x is None:
        return []
    if isinstance(x, (list, tuple)):
        return list(x)
    if hasattr(x, 'count') and hasattr(x, 'item') and not isinstance(x, adsk.fusion.Sketch):
        return [x.item(i) for i in range(x.count)]
    return [x]


def coll(objs):
    c = adsk.core.ObjectCollection.create()
    for o in items(objs):
        c.add(o)
    return c


def param(name, expr, unit='mm', comment=''):
    """Create or update a user parameter. expr: number (in `unit`) or expression string."""
    if isinstance(expr, (int, float)):
        expr = ('%s %s' % (format(expr, '.10g'), unit)) if unit else format(expr, '.10g')
    ups = design().userParameters
    p = ups.itemByName(name)
    if p:
        p.expression = expr
        if comment:
            p.comment = comment
        return p
    return ups.add(name, adsk.core.ValueInput.createByString(expr), unit, comment)


# ---------------------------------------------------------------- planes, axes, sketches

def plane(p='xy', comp=None):
    if isinstance(p, str):
        c = _comp(comp)
        return {'xy': c.xYConstructionPlane, 'xz': c.xZConstructionPlane,
                'yz': c.yZConstructionPlane}[p.lower()]
    return p


def axis(a='z', comp=None):
    if isinstance(a, str):
        c = _comp(comp)
        return {'x': c.xConstructionAxis, 'y': c.yConstructionAxis,
                'z': c.zConstructionAxis}[a.lower().lstrip('+')]
    return a


def offset_plane(base='xy', dist=0, comp=None, name=None):
    c = _comp(comp)
    inp = c.constructionPlanes.createInput()
    inp.setByOffset(plane(base, c), length(dist))
    cp = c.constructionPlanes.add(inp)
    if name:
        cp.name = name
    return cp


def sketch(on='xy', name=None, comp=None, project=False):
    """New sketch on 'xy' | 'xz' | 'yz', a construction plane or a planar BRepFace.
    On a face, its edges are projected only if project=True (they add extra profiles)."""
    c = _comp(comp)
    target = plane(on, c)
    if isinstance(target, adsk.fusion.BRepFace) and not project:
        sk = c.sketches.addWithoutEdges(target)
    else:
        sk = c.sketches.add(target)
    if name:
        sk.name = name
    return sk


def _sp(sk, p):
    """Sketch-space Point3D from (x, y) sketch mm or (x, y, z) model mm.
    An existing SketchPoint is passed through (connects curves)."""
    if isinstance(p, adsk.fusion.SketchPoint):
        return p
    if len(p) == 3:
        q = sk.modelToSketchSpace(pt(*p))
        return adsk.core.Point3D.create(q.x, q.y, 0)
    return adsk.core.Point3D.create(p[0] / 10.0, p[1] / 10.0, 0)


def to_sketch(sk, x, y, z):
    """Model mm -> sketch (x, y) mm."""
    q = sk.modelToSketchSpace(pt(x, y, z))
    return (q.x * 10.0, q.y * 10.0)


# ---------------------------------------------------------------- sketch geometry

def rect(sk, w, h, center=(0, 0)):
    c = _sp(sk, center)
    corner = adsk.core.Point3D.create(c.x + w / 20.0, c.y + h / 20.0, 0)
    return sk.sketchCurves.sketchLines.addCenterPointRectangle(c, corner)


def rect2(sk, p1, p2):
    """Rectangle from two opposite corners."""
    return sk.sketchCurves.sketchLines.addTwoPointRectangle(_sp(sk, p1), _sp(sk, p2))


def circle(sk, d, center=(0, 0)):
    """Circle by DIAMETER."""
    return sk.sketchCurves.sketchCircles.addByCenterRadius(_sp(sk, center), d / 20.0)


def poly(sk, pts_, close=True):
    """Connected polyline through points; closed by default."""
    lines = sk.sketchCurves.sketchLines
    out = []
    for i in range(len(pts_) - 1):
        start = out[-1].endSketchPoint if out else _sp(sk, pts_[i])
        out.append(lines.addByTwoPoints(start, _sp(sk, pts_[i + 1])))
    if close and len(out) > 1:
        out.append(lines.addByTwoPoints(out[-1].endSketchPoint, out[0].startSketchPoint))
    return out


def polygon(sk, n, d, center=(0, 0), flats=False, rotation=0.0):
    """Regular n-gon. d = circumscribed diameter, or across-flats if flats=True (nut traps)."""
    r = d / 2.0 / math.cos(math.pi / n) if flats else d / 2.0
    cx, cy = center[0], center[1]
    a0 = math.radians(rotation)
    return poly(sk, [(cx + r * math.cos(a0 + 2 * math.pi * i / n),
                      cy + r * math.sin(a0 + 2 * math.pi * i / n)) for i in range(n)])


def arc(sk, p1, mid, p2):
    """Arc through three points."""
    return sk.sketchCurves.sketchArcs.addByThreePoints(_sp(sk, p1), _sp(sk, mid), _sp(sk, p2))


def line(sk, p1, p2):
    return sk.sketchCurves.sketchLines.addByTwoPoints(_sp(sk, p1), _sp(sk, p2))


def spline(sk, pts_, closed=False):
    """Fitted spline through points."""
    c = adsk.core.ObjectCollection.create()
    for p in pts_:
        c.add(_sp(sk, p))
    s = sk.sketchCurves.sketchFittedSplines.add(c)
    if closed:
        s.isClosed = True
    return s


def slot(sk, length_, width, center=(0, 0), rotation=0.0):
    """Obround slot; length_ is overall length (end to end)."""
    r = width / 2.0
    half = max(length_ / 2.0 - r, 0.0)
    a = math.radians(rotation)
    ux, uy = math.cos(a), math.sin(a)
    nx, ny = -uy, ux
    cx, cy = center[0], center[1]

    def p(s, t):
        return (cx + ux * s + nx * t, cy + uy * s + ny * t)

    line(sk, p(-half, r), p(half, r))
    line(sk, p(half, -r), p(-half, -r))
    arc(sk, p(half, r), p(half + r, 0), p(half, -r))
    arc(sk, p(-half, -r), p(-half - r, 0), p(-half, r))


def text(sk, s, height, center=(0, 0), width=None, font=None, bold=False):
    """Single-line text centred on `center`. Extrude it with h.extrude(text_obj, depth)."""
    texts = sk.sketchTexts
    inp = texts.createInput2(s, height / 10.0)
    w = width if width is not None else height * max(len(s), 1) * 0.8
    c = _sp(sk, center)
    half_h = height * 0.7 / 10.0  # text box a bit taller than the glyphs
    p1 = adsk.core.Point3D.create(c.x - w / 20.0, c.y - half_h, 0)
    p2 = adsk.core.Point3D.create(c.x + w / 20.0, c.y + half_h, 0)
    inp.setAsMultiLine(p1, p2, adsk.core.HorizontalAlignments.CenterHorizontalAlignment,
                       adsk.core.VerticalAlignments.MiddleVerticalAlignment, 0)
    if font:
        inp.fontName = font
    if bold:
        inp.textStyle = adsk.fusion.TextStyles.TextStyleBold
    return texts.add(inp)


def profiles(sk):
    return [sk.profiles.item(i) for i in range(sk.profiles.count)]


def profile(sk, which='largest'):
    """Pick a profile: 'largest' | 'smallest' | index. A plate with holes = 'largest'."""
    ps = profiles(sk)
    if not ps:
        raise ValueError('Sketch %r has no closed profiles' % sk.name)
    if isinstance(which, int):
        return ps[which]
    area = lambda p: p.areaProperties().area
    return max(ps, key=area) if which == 'largest' else min(ps, key=area)


# ---------------------------------------------------------------- features

def _op(op):
    return _OPS[op] if isinstance(op, str) else op


def _owner(obj, comp):
    if comp is not None:
        return comp
    first = items(obj)[0] if not isinstance(obj, adsk.fusion.Sketch) else obj
    for attr in ('parentComponent', 'parentSketch', 'body'):
        o = getattr(first, attr, None)
        if o is None:
            continue
        if isinstance(o, adsk.fusion.Component):
            return o
        return _owner(o, None)
    return root()


def _profile_input(prof):
    if isinstance(prof, adsk.fusion.Sketch):
        ps = profiles(prof)
    else:
        ps = items(prof)
    return ps[0] if len(ps) == 1 else coll(ps)


def extrude(prof, dist, op='new', symmetric=False, reverse=False, taper=None,
            bodies=None, comp=None, name=None):
    """Extrude profile(s) / a whole sketch / a SketchText.
    Negative numeric dist or reverse=True extrudes the other way. symmetric: dist is total."""
    c = _owner(prof, comp)
    feats = c.features.extrudeFeatures
    inp = feats.createInput(_profile_input(prof), _op(op))
    if symmetric:
        inp.setSymmetricExtent(length(dist), True)
    else:
        if isinstance(dist, (int, float)) and dist < 0:
            dist, reverse = -dist, not reverse
        ext = adsk.fusion.DistanceExtentDefinition.create(length(dist))
        direction = (adsk.fusion.ExtentDirections.NegativeExtentDirection if reverse
                     else adsk.fusion.ExtentDirections.PositiveExtentDirection)
        if taper is not None:
            inp.setOneSideExtent(ext, direction, angle(taper))
        else:
            inp.setOneSideExtent(ext, direction)
    if bodies is not None:
        inp.participantBodies = items(bodies)
    f = feats.add(inp)
    if name:
        f.name = name
    return f


def revolve(prof, axis_='z', deg=360, op='new', comp=None, name=None):
    """axis_: 'x'|'y'|'z', a construction axis or a sketch line in the profile's plane."""
    c = _owner(prof, comp)
    feats = c.features.revolveFeatures
    inp = feats.createInput(_profile_input(prof), axis(axis_, c), _op(op))
    inp.setAngleExtent(False, angle(deg))
    f = feats.add(inp)
    if name:
        f.name = name
    return f


def loft(sections, op='new', solid=True, comp=None, name=None):
    """sections: profiles (or sketches -> largest profile), bottom to top."""
    secs = [profile(s) if isinstance(s, adsk.fusion.Sketch) else s for s in sections]
    c = _owner(secs[0], comp)
    feats = c.features.loftFeatures
    inp = feats.createInput(_op(op))
    for s in secs:
        inp.loftSections.add(s)
    inp.isSolid = solid
    f = feats.add(inp)
    if name:
        f.name = name
    return f


def sweep(prof, path_curve, op='new', comp=None, name=None):
    c = _owner(prof, comp)
    path = c.features.createPath(path_curve)
    feats = c.features.sweepFeatures
    inp = feats.createInput(_profile_input(prof), path, _op(op))
    f = feats.add(inp)
    if name:
        f.name = name
    return f


def fillet(edges_, r, tangent_chain=True):
    es = items(edges_)
    if not es:
        raise ValueError('fillet: no edges selected')
    feats = es[0].body.parentComponent.features.filletFeatures
    inp = feats.createInput()
    try:
        inp.edgeSetInputs.addConstantRadiusEdgeSet(coll(es), length(r), tangent_chain)
    except AttributeError:
        inp.addConstantRadiusEdgeSet(coll(es), length(r), tangent_chain)
    return feats.add(inp)


def chamfer(edges_, d, tangent_chain=True):
    es = items(edges_)
    if not es:
        raise ValueError('chamfer: no edges selected')
    feats = es[0].body.parentComponent.features.chamferFeatures
    try:
        inp = feats.createInput2()
        inp.chamferEdgeSets.addEqualDistanceChamferEdgeSet(coll(es), length(d), tangent_chain)
    except AttributeError:
        inp = feats.createInput(coll(es), tangent_chain)
        inp.setToEqualDistance(length(d))
    return feats.add(inp)


def shell(target, thickness, inside=True):
    """target: faces to remove (open shell) or a body (closed hollow)."""
    objs = items(target)
    first = objs[0]
    body = first if isinstance(first, adsk.fusion.BRepBody) else first.body
    feats = body.parentComponent.features.shellFeatures
    inp = feats.createInput(coll(objs), False)
    if inside:
        inp.insideThickness = length(thickness)
    else:
        inp.outsideThickness = length(thickness)
    return feats.add(inp)


def combine(target, tools, op='cut', keep_tools=False):
    feats = target.parentComponent.features.combineFeatures
    inp = feats.createInput(target, coll(tools))
    inp.operation = _op(op)
    inp.isKeepToolBodies = keep_tools
    return feats.add(inp)


def _move(bodies_, matrix):
    objs = items(bodies_)
    feats = objs[0].parentComponent.features.moveFeatures
    inp = feats.createInput2(coll(objs))
    inp.defineAsFreeMove(matrix)
    return feats.add(inp)


def move(bodies_, dx=0.0, dy=0.0, dz=0.0):
    m = adsk.core.Matrix3D.create()
    m.translation = adsk.core.Vector3D.create(dx / 10.0, dy / 10.0, dz / 10.0)
    return _move(bodies_, m)


def rotate(bodies_, deg, axis_='z', origin=(0, 0, 0)):
    m = adsk.core.Matrix3D.create()
    m.setToRotation(math.radians(deg), adsk.core.Vector3D.create(*_DIRS[axis_]), pt(*origin))
    return _move(bodies_, m)


def mirror(entities, plane_='yz', comp=None):
    objs = items(entities)
    c = comp or objs[0].parentComponent
    feats = c.features.mirrorFeatures
    inp = feats.createInput(coll(objs), plane(plane_, c))
    return feats.add(inp)


def pattern_circular(entities, count, axis_='z', total_deg=360, comp=None):
    """entities: bodies or features."""
    objs = items(entities)
    c = comp or objs[0].parentComponent
    feats = c.features.circularPatternFeatures
    inp = feats.createInput(coll(objs), axis(axis_, c))
    inp.quantity = adsk.core.ValueInput.createByReal(count)
    inp.totalAngle = angle(total_deg)
    inp.isSymmetric = False
    return feats.add(inp)


def pattern_rect(entities, n1, d1, dir1='x', n2=1, d2=0, dir2='y', comp=None):
    """d1/d2 are spacing between instances."""
    objs = items(entities)
    c = comp or objs[0].parentComponent
    feats = c.features.rectangularPatternFeatures
    inp = feats.createInput(coll(objs), axis(dir1, c), adsk.core.ValueInput.createByReal(n1),
                            length(d1), adsk.fusion.PatternDistanceType.SpacingPatternDistanceType)
    if n2 > 1:
        inp.setDirectionTwo(axis(dir2, c), adsk.core.ValueInput.createByReal(n2), length(d2))
    return feats.add(inp)


# ---------------------------------------------------------------- bodies & selection

def bodies(comp=None):
    """All bodies (root + occurrences as proxies), or the bodies of one component."""
    if comp is not None:
        return items(comp.bRepBodies)
    r = root()
    out = items(r.bRepBodies)
    for occ in items(r.allOccurrences):
        out.extend(items(occ.bRepBodies))
    return out


def mesh_bodies(comp=None):
    """Mesh bodies, including occurrence proxies in world coordinates."""
    if comp is not None:
        return items(comp.meshBodies)
    r = root()
    out = items(r.meshBodies)
    for occ in items(r.allOccurrences):
        out.extend(items(occ.meshBodies))
    return out


def body(name=None):
    """Body by name, or the last body of the root component."""
    if name is None:
        bs = items(root().bRepBodies)
        if not bs:
            raise ValueError('No bodies in the root component')
        return bs[-1]
    for b in bodies():
        if b.name == name:
            return b
    raise ValueError('No body %r. Bodies: %s' % (name, [b.name for b in bodies()]))


def bbox(entity):
    """Bounding box in mm: {'min': [x,y,z], 'max': [...], 'size': [...]}."""
    bb = entity.boundingBox
    lo = [mm(bb.minPoint.x), mm(bb.minPoint.y), mm(bb.minPoint.z)]
    hi = [mm(bb.maxPoint.x), mm(bb.maxPoint.y), mm(bb.maxPoint.z)]
    return {'min': lo, 'max': hi, 'size': [hi[i] - lo[i] for i in range(3)]}


def edges(body_, where=None):
    return [e for e in items(body_.edges) if where is None or where(e)]


def faces(body_, where=None):
    return [f for f in items(body_.faces) if where is None or where(f)]


def normal(face):
    ok, n = face.evaluator.getNormalAtPoint(face.pointOnFace)
    return (n.x, n.y, n.z)


def _unit(d):
    v = _DIRS[d] if isinstance(d, str) else d
    ln = math.sqrt(sum(c * c for c in v))
    return tuple(c / ln for c in v)


def faces_facing(body_, direction='+z', tol_deg=1.0):
    """Planar faces whose outward normal points along direction ('+z', '-x', (x,y,z)...)."""
    d = _unit(direction)
    cos_tol = math.cos(math.radians(tol_deg))

    def ok(f):
        if not isinstance(f.geometry, adsk.core.Plane):
            return False
        n = normal(f)
        return sum(n[i] * d[i] for i in range(3)) >= cos_tol
    return faces(body_, ok)


def top_face(body_):
    fs = faces_facing(body_, '+z')
    if not fs:
        raise ValueError('No upward planar face on %s' % body_.name)
    return max(fs, key=lambda f: f.centroid.z)


def bottom_face(body_):
    fs = faces_facing(body_, '-z')
    if not fs:
        raise ValueError('No downward planar face on %s' % body_.name)
    return min(fs, key=lambda f: f.centroid.z)


def edges_at_z(body_, z, tol=0.01):
    """Edges lying entirely at height z (mm)."""
    def ok(e):
        bb = e.boundingBox
        return abs(mm(bb.minPoint.z) - z) <= tol and abs(mm(bb.maxPoint.z) - z) <= tol
    return edges(body_, ok)


def bottom_edges(body_):
    return edges_at_z(body_, bbox(body_)['min'][2])


def top_edges(body_):
    return edges_at_z(body_, bbox(body_)['max'][2])


def edges_along(body_, direction='z', tol_deg=1.0):
    """Straight edges parallel to an axis/direction (e.g. vertical edges of a box)."""
    d = _unit(direction)
    cos_tol = math.cos(math.radians(tol_deg))

    def ok(e):
        if not isinstance(e.geometry, adsk.core.Line3D):
            return False
        a, b = e.startVertex.geometry, e.endVertex.geometry
        v = (b.x - a.x, b.y - a.y, b.z - a.z)
        ln = math.sqrt(sum(c * c for c in v)) or 1.0
        return abs(sum(v[i] * d[i] for i in range(3))) / ln >= cos_tol
    return edges(body_, ok)


def circular_edges(body_, d=None, tol=0.05):
    """Circular edges (holes, bosses), optionally only those with diameter d (mm)."""
    def ok(e):
        g = e.geometry
        if not isinstance(g, (adsk.core.Circle3D, adsk.core.Arc3D)):
            return False
        return d is None or abs(g.radius * 20.0 - d) <= tol
    return edges(body_, ok)
