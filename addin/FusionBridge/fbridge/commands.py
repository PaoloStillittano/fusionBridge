"""Bridge commands. Run on Fusion's main thread; each takes a dict and returns a dict.

All lengths in responses are mm (Fusion works internally in cm).
"""
import contextlib
import importlib
import inspect
import io
import math
import os
import re
import sys
import traceback
import uuid

import adsk.core
import adsk.fusion

from . import VERSION, fdm, helpers, mesh_io


def _app():
    return adsk.core.Application.get()


def _design(required=True):
    d = adsk.fusion.Design.cast(_app().activeProduct)
    if d is None and required:
        raise RuntimeError('No active Fusion design: open one or run `f360 new`.')
    return d


def _timeline(d):
    if d is None or d.designType != adsk.fusion.DesignTypes.ParametricDesignType:
        return None
    return d.timeline


def _jsonable(x):
    if x is None or isinstance(x, (bool, int, float, str)):
        return x
    if isinstance(x, dict):
        return {str(k): _jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple, set)):
        return [_jsonable(v) for v in x]
    return str(x)


def _health(item):
    states = adsk.fusion.FeatureHealthStates
    names = {}
    for attr, label in (('Healthy', 'ok'), ('Warning', 'warning'), ('Error', 'error'),
                        ('Suppressed', 'suppressed'), ('Unknown', 'unknown')):
        value = getattr(states, attr + 'FeatureHealthState', None)
        if value is not None:
            names[value] = label
    try:
        return names.get(item.healthState, str(item.healthState))
    except Exception:
        return None


def _timeline_items(tl, start=0):
    out = []
    for i in range(start, tl.count):
        item = tl.item(i)
        entry = {'index': i, 'name': item.name, 'health': _health(item)}
        try:
            entry['type'] = item.entity.objectType.split('::')[-1]
        except Exception:
            pass
        if item.isSuppressed:
            entry['suppressed'] = True
        if item.isRolledBack:
            entry['rolled_back'] = True
        if entry['health'] in ('warning', 'error'):
            try:
                entry['message'] = item.errorOrWarningMessage
            except Exception:
                pass
        out.append(entry)
    return out


def _rollback_to(d, n):
    tl = d.timeline
    tl.markerPosition = n
    tl.deleteAllAfterMarker()


def _all_bodies(d):
    return helpers.bodies() + helpers.mesh_bodies()


def _is_mesh(b):
    return isinstance(b, adsk.fusion.MeshBody)


def _solid(b):
    return b.isClosed if _is_mesh(b) else b.isSolid


def _triangle_mesh(b, quality='NormalQualityTriangleMesh'):
    if _is_mesh(b):
        return b.displayMesh
    calc = b.meshManager.createMeshCalculator()
    calc.setQuality(getattr(adsk.fusion.TriangleMeshQualityOptions, quality))
    return calc.calculate()


def _select_bodies(d, names):
    bs = _all_bodies(d)
    if not names:
        return [b for b in bs if b.isVisible]
    by_name = {}
    for b in bs:
        by_name.setdefault(b.name, []).append(b)
    missing = [n for n in names if n not in by_name]
    if missing:
        raise ValueError('Unknown bodies %s. Bodies: %s' % (missing, sorted(by_name)))
    ambiguous = [n for n in names if len(by_name[n]) != 1]
    if ambiguous:
        raise ValueError('Ambiguous body names: %s. Rename bodies before selecting them.' % ambiguous)
    return [by_name[n][0] for n in names]


def _body_info(b):
    mesh = _is_mesh(b)
    info = {'name': b.name, 'kind': 'mesh' if mesh else 'brep', 'solid': _solid(b),
            'visible': b.isVisible, 'bbox_mm': helpers.bbox(b)}
    if mesh:
        info['triangles'] = b.displayMesh.triangleCount
        info['oriented'] = b.isOriented
    else:
        info.update(faces=b.faces.count, edges=b.edges.count)
    try:
        info['component'] = b.parentComponent.name
        info['volume_mm3'] = round(b.volume * 1000.0, 2)
        info['area_mm2'] = round(b.area * 100.0, 2)
        info['material'] = b.material.name if b.material else None
    except Exception:
        pass
    info['bbox_mm'] = {k: [round(v, 3) for v in vals] for k, vals in info['bbox_mm'].items()}
    return info


def _parameter_info(p, d):
    # The numeric value must use the declared unit, not Fusion's internal cm/radians.
    factor = d.unitsManager.evaluateExpression('1 ' + p.unit, p.unit) if p.unit else 1.0
    value = p.value / factor
    return {'name': p.name, 'expression': p.expression, 'unit': p.unit,
            'value': value, 'internal_value': p.value, 'comment': p.comment}


def _safe_name(s):
    return re.sub(r'[^A-Za-z0-9_.-]+', '_', s).strip('_') or 'body'


# ---------------------------------------------------------------- commands

def cmd_ping(args):
    app = _app()
    d = _design(False)
    doc = app.activeDocument
    return {'bridge_version': VERSION, 'fusion_version': app.version,
            'document': doc.name if doc else None,
            'document_id': str(doc.creationId) if doc else None,
            'design_type': None if d is None else
            ('parametric' if _timeline(d) is not None else 'direct'),
            'units': d.unitsManager.defaultLengthUnits if d else None}


def cmd_new(args):
    app = _app()
    app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
    d = _design()
    d.designType = adsk.fusion.DesignTypes.ParametricDesignType
    units = {'mm': adsk.fusion.DistanceUnits.MillimeterDistanceUnits,
             'cm': adsk.fusion.DistanceUnits.CentimeterDistanceUnits,
             'in': adsk.fusion.DistanceUnits.InchDistanceUnits}[args.get('units', 'mm')]
    d.fusionUnitsManager.distanceDisplayUnits = units
    return {'document': app.activeDocument.name, 'units': args.get('units', 'mm')}


def cmd_save(args):
    app = _app()
    doc = app.activeDocument
    if doc is None:
        raise RuntimeError('No active document')
    name = args.get('name')
    if doc.isSaved and not name:
        doc.save(args.get('description', ''))
    else:
        if not name:
            raise ValueError('First save needs a name: f360 save NAME')
        doc.saveAs(name, app.data.activeProject.rootFolder, args.get('description', ''), '')
    return {'document': doc.name, 'project': app.data.activeProject.name}


def cmd_exec(args):
    """Run Python code in Fusion. Namespace: adsk, app, ui, design, root, h (helpers), math.
    Set `result = ...` to return a value. On error, the timeline is rolled back to where it
    was before the run (unless rollback_on_error is false)."""
    app = _app()
    d = _design(False)
    tl = _timeline(d)
    start = tl.count if tl is not None else None
    can_rollback = tl is not None and tl.markerPosition == tl.count
    doc = app.activeDocument

    ns = {'__name__': '__f360_exec__', 'adsk': adsk, 'app': app, 'ui': app.userInterface,
          'design': d, 'root': d.rootComponent if d else None, 'h': helpers, 'math': math,
          'result': None}
    out = io.StringIO()
    error = tb = None
    try:
        code = compile(args.get('code', ''), args.get('filename', '<exec>'), 'exec')
        with contextlib.redirect_stdout(out):
            exec(code, ns)
    except Exception as e:
        etype, evalue, etb = sys.exc_info()
        error = '%s: %s' % (type(e).__name__, e)
        # drop the frame of this function so the traceback starts in the user's code
        tb = ''.join(traceback.format_exception(etype, evalue, etb.tb_next if etb else None))

    res = {'ok': error is None, 'stdout': out.getvalue(), 'result': _jsonable(ns.get('result'))}
    try:
        same_doc = doc is not None and doc.isValid and app.activeDocument == doc
    except Exception:  # the script closed or replaced the document
        same_doc = False
    if tl is not None and same_doc:
        res['timeline'] = {'before': start, 'after': tl.count}
        problems = [i for i in _timeline_items(tl, start) if i['health'] in ('warning', 'error')]
        if problems:
            res['feature_problems'] = problems
        if error and can_rollback and args.get('rollback_on_error', True) and tl.count > start:
            _rollback_to(d, start)
            res['rolled_back'] = True
            res['timeline']['after'] = tl.count
    if error:
        res['error'] = error
        res['traceback'] = tb
    return res


def cmd_rollback(args):
    d = _design()
    tl = _timeline(d)
    if tl is None:
        raise RuntimeError('Rollback needs a parametric design (timeline)')
    n = int(args['to'])
    if not 0 <= n <= tl.count:
        raise ValueError('to must be between 0 and %d' % tl.count)
    _rollback_to(d, n)
    return {'timeline_count': tl.count}


def cmd_tree(args):
    d = _design()
    r = d.rootComponent
    tl = _timeline(d)
    sketches = []
    comps = [r] + [o.component for o in helpers.items(r.allOccurrences)]
    seen = set()
    for c in comps:
        if c.name in seen:
            continue
        seen.add(c.name)
        for sk in helpers.items(c.sketches):
            sketches.append({'name': sk.name, 'component': c.name, 'profiles': sk.profiles.count,
                             'curves': sk.sketchCurves.count,
                             'fully_constrained': sk.isFullyConstrained,
                             'visible': sk.isVisible})
    params = []
    for p in helpers.items(d.userParameters):
        params.append(_parameter_info(p, d))
    return {
        'document': _app().activeDocument.name,
        'document_id': str(_app().activeDocument.creationId),
        'units': d.unitsManager.defaultLengthUnits,
        'design_type': 'parametric' if tl is not None else 'direct',
        'components': [{'name': o.name, 'component': o.component.name}
                       for o in helpers.items(r.allOccurrences)],
        'bodies': [_body_info(b) for b in _all_bodies(d)],
        'sketches': sketches,
        'user_parameters': params,
        'timeline': _timeline_items(tl) if tl is not None else None,
    }


def cmd_params(args):
    d = _design()
    for spec in args.get('set', []):
        helpers.param(spec['name'], spec['expression'], spec.get('unit', 'mm'),
                      spec.get('comment', ''))
    params = [_parameter_info(p, d) for p in helpers.items(d.userParameters)]
    res = {'user_parameters': params}
    tl = _timeline(d)
    if tl is not None:
        problems = [i for i in _timeline_items(tl) if i['health'] in ('warning', 'error')]
        if problems:
            res['feature_problems'] = problems
    return res


_VIEWS = {  # view direction (from target to eye), up vector; +Z up
    'iso': ((1, -1, 1), (0, 0, 1)),
    'iso_back': ((-1, 1, 1), (0, 0, 1)),
    'iso_bottom': ((1, -1, -1), (0, 0, 1)),
    'front': ((0, -1, 0), (0, 0, 1)),
    'back': ((0, 1, 0), (0, 0, 1)),
    'right': ((1, 0, 0), (0, 0, 1)),
    'left': ((-1, 0, 0), (0, 0, 1)),
    'top': ((0, 0, 1), (0, 1, 0)),
    'bottom': ((0, 0, -1), (0, 1, 0)),
}
_STYLES = {
    'shaded': 'ShadedVisualStyle',
    'edges': 'ShadedWithVisibleEdgesOnlyVisualStyle',
    'hidden': 'ShadedWithHiddenEdgesVisualStyle',
    'wire': 'WireframeVisualStyle',
}


def _scene_center_radius(d):
    lo, hi = None, None
    for b in (_all_bodies(d) if d else []):
        if not b.isVisible:
            continue
        bb = b.boundingBox
        p, q = (bb.minPoint.x, bb.minPoint.y, bb.minPoint.z), (bb.maxPoint.x, bb.maxPoint.y, bb.maxPoint.z)
        lo = p if lo is None else tuple(min(lo[i], p[i]) for i in range(3))
        hi = q if hi is None else tuple(max(hi[i], q[i]) for i in range(3))
    if lo is None:
        return (0.0, 0.0, 0.0), 5.0
    center = tuple((lo[i] + hi[i]) / 2 for i in range(3))
    radius = max(math.sqrt(sum((hi[i] - lo[i]) ** 2 for i in range(3))) / 2, 0.5)
    return center, radius


def cmd_screenshot(args):
    app = _app()
    vp = app.activeViewport
    if vp is None:
        raise RuntimeError('No active viewport')
    views = args.get('views') or ['iso']
    unknown = [v for v in views if v != 'current' and v not in _VIEWS]
    if unknown:
        raise ValueError('Unknown views %s. Use: %s, current' % (unknown, ', '.join(_VIEWS)))
    path = os.path.abspath(os.path.expanduser(args['path']))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    stem, ext = os.path.splitext(path)
    width, height = int(args.get('width', 1280)), int(args.get('height', 960))

    center, radius = _scene_center_radius(_design(False))
    orig_cam, orig_style = vp.camera, vp.visualStyle
    files = []
    try:
        style = args.get('style')
        if style:
            vp.visualStyle = getattr(adsk.core.VisualStyles, _STYLES[style])
        for view in views:
            if view != 'current':
                (dx, dy, dz), up = _VIEWS[view]
                ln = math.sqrt(dx * dx + dy * dy + dz * dz)
                dist = radius * 4
                cam = vp.camera
                cam.isSmoothTransition = False
                cam.cameraType = (adsk.core.CameraTypes.PerspectiveCameraType if args.get('perspective')
                                  else adsk.core.CameraTypes.OrthographicCameraType)
                cam.target = adsk.core.Point3D.create(*center)
                cam.eye = adsk.core.Point3D.create(center[0] + dx / ln * dist, center[1] + dy / ln * dist,
                                                   center[2] + dz / ln * dist)
                cam.upVector = adsk.core.Vector3D.create(*up)
                vp.camera = cam
                vp.fit()
            vp.refresh()
            adsk.doEvents()
            out = path if len(views) == 1 else '%s_%s%s' % (stem, view, ext or '.png')
            if not vp.saveAsImageFile(out, width, height):
                raise RuntimeError('saveAsImageFile failed for %s' % out)
            files.append(out)
    finally:
        if args.get('restore', True):
            vp.camera = orig_cam
            vp.visualStyle = orig_style
    return {'files': files}


def cmd_export(args):
    app = _app()
    d = _design()
    em = d.exportManager
    path = os.path.abspath(os.path.expanduser(args['path']))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    stem, ext = os.path.splitext(path)
    fmt = ext.lower().lstrip('.')
    if fmt not in ('stl', '3mf', 'step', 'stp', 'f3d'):
        raise ValueError('Unsupported format %r: use .stl, .3mf, .step or .f3d' % ext)
    refine = {'low': adsk.fusion.MeshRefinementSettings.MeshRefinementLow,
              'medium': adsk.fusion.MeshRefinementSettings.MeshRefinementMedium,
              'high': adsk.fusion.MeshRefinementSettings.MeshRefinementHigh}[args.get('refine', 'high')]
    names = args.get('bodies') or []
    each = args.get('each', False)

    if fmt in ('step', 'stp', 'f3d'):
        if names:
            raise ValueError('%s export works on the whole design, not single bodies' % fmt.upper())
        if fmt in ('step', 'stp') and any(_is_mesh(b) and b.isVisible for b in _all_bodies(d)):
            raise ValueError('STEP cannot preserve mesh bodies; use 3MF/STL for printing or F3D for the design')
        temporary = '%s.%s%s' % (stem, uuid.uuid4().hex, ext)
        try:
            opts = (em.createSTEPExportOptions(temporary, d.rootComponent) if fmt != 'f3d'
                    else em.createFusionArchiveExportOptions(temporary, d.rootComponent))
            if not em.execute(opts) or not os.path.isfile(temporary) or os.path.getsize(temporary) == 0:
                raise RuntimeError('Export did not produce a nonempty file')
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.remove(temporary)
        return {'files': [path]}

    if each:
        targets = [('%s_%s%s' % (stem, _safe_name(b.name), ext), b) for b in _select_bodies(d, names)]
        paths = [p for p, _ in targets]
        if len(set(paths)) != len(paths):
            raise ValueError('Body names collide after filename normalization; rename before exporting')
    elif len(names) == 1:
        targets = [(path, _select_bodies(d, names)[0])]
    elif names:
        raise ValueError('Several bodies in one mesh file: use --each, or hide the others and export '
                         'without --bodies')
    else:
        targets = [(path, d.rootComponent)]

    files = []
    for out, geom in targets:
        mesh_targets = [geom] if _is_mesh(geom) else []
        if isinstance(geom, adsk.fusion.Component):
            visible = _select_bodies(d, None)
            if any(_is_mesh(b) for b in visible):
                mesh_targets = visible
        if mesh_targets:
            coords, indices = [], []
            mesh_quality = {'low': 'LowQualityTriangleMesh', 'medium': 'NormalQualityTriangleMesh',
                            'high': 'HighQualityTriangleMesh'}[args.get('refine', 'high')]
            for b in mesh_targets:
                mesh = _triangle_mesh(b, mesh_quality)
                offset = len(coords) // 3
                coords.extend(v * 10.0 for v in mesh.nodeCoordinatesAsDouble)
                indices.extend(i + offset for i in mesh.nodeIndices)
            mesh_io.export(out, coords, indices, geom.name)
            files.append(out)
            continue
        out_stem, out_ext = os.path.splitext(out)
        temporary = '%s.%s%s' % (out_stem, uuid.uuid4().hex, out_ext)
        try:
            if fmt == 'stl':
                opts = em.createSTLExportOptions(geom, temporary)
                opts.isBinaryFormat = True
                opts.sendToPrintUtility = False
            else:
                opts = em.createC3MFExportOptions(geom, temporary)
            try:
                opts.meshRefinement = refine
            except Exception:
                pass
            if not em.execute(opts) or not os.path.isfile(temporary) or os.path.getsize(temporary) == 0:
                raise RuntimeError('Export did not produce a nonempty file for %s' % out)
            os.replace(temporary, out)
        finally:
            if os.path.exists(temporary):
                os.remove(temporary)
        files.append(out)
    return {'files': files}


def cmd_fdm(args):
    d = _design()
    quality = {'low': 'LowQualityTriangleMesh', 'normal': 'NormalQualityTriangleMesh',
               'high': 'HighQualityTriangleMesh'}[args.get('quality', 'normal')]
    overhang = float(args.get('overhang', 45))
    bed = args.get('bed')
    mode = args.get('mode', 'plate')
    if mode not in ('plate', 'part'):
        raise ValueError('mode must be plate or part')
    bed_z = float(args.get('bed_z', 0)) if mode == 'plate' else None
    reports = []
    combined_coords, combined_indices = [], []
    for b in _select_bodies(d, args.get('bodies')):
        mesh = _triangle_mesh(b, quality)
        coords = [c * 10.0 for c in mesh.nodeCoordinatesAsDouble]
        try:
            normals = list(mesh.normalVectorsAsDouble)
        except Exception:
            normals = None
        indices = list(mesh.nodeIndices)
        rep = fdm.analyze(coords, indices, normals=normals,
                          overhang_deg=overhang, bed_size=bed, bed_z=bed_z)
        offset = len(combined_coords) // 3
        combined_coords.extend(coords)
        combined_indices.extend(i + offset for i in indices)
        volume = b.volume * 1000.0
        rep = dict({'body': b.name, 'kind': 'mesh' if _is_mesh(b) else 'brep',
                    'solid': _solid(b), 'volume_mm3': round(volume, 1),
                    'mass_g_pla_solid': round(volume * fdm.PLA_DENSITY_G_MM3, 1)}, **rep)
        if not _solid(b):
            rep['warnings'].insert(0, 'Body is not a closed solid: the slicer may fail.')
        if _is_mesh(b) and not b.isOriented:
            rep['warnings'].insert(0, 'Mesh triangles are not consistently oriented.')
        if volume <= 0:
            rep['warnings'].insert(0, 'Body does not have positive volume.')
            rep['mass_g_pla_solid'] = None
        reports.append(rep)
    if not reports:
        raise ValueError('No visible BRep or mesh bodies to analyze')
    warnings = [w for r in reports for w in r['warnings']]
    res = {'overhang_threshold_deg': overhang, 'mode': mode, 'bodies': reports,
           'validation': {'passed': not warnings, 'warning_count': len(warnings),
                          'scope': 'geometric_precheck_not_slicing'}}
    if mode == 'plate':
        plate = fdm.analyze(combined_coords, combined_indices, overhang_deg=overhang,
                            bed_size=bed, bed_z=bed_z)
        res['plate'] = {'bbox_mm': plate.get('bbox_mm'), 'fits_bed': plate.get('fits_bed'),
                        'bed_z_mm': bed_z,
                        'note': 'Combined bounds only; collisions and exclusion zones require slicing'}
        if plate.get('fits_bed') is False:
            res['validation']['passed'] = False
    if args.get('strict') and not res['validation']['passed']:
        res['ok'] = False
    return res


def cmd_api(args):
    """Introspect the live Fusion API: docstrings and members, or search by name."""
    term = args.get('search')
    if term:
        term = term.lower()
        hits = []
        for modname, mod in (('adsk.core', adsk.core), ('adsk.fusion', adsk.fusion)):
            for cname in dir(mod):
                obj = getattr(mod, cname)
                if term in cname.lower():
                    hits.append('%s.%s' % (modname, cname))
                if isinstance(obj, type):
                    hits.extend('%s.%s.%s' % (modname, cname, m) for m in dir(obj)
                                if not m.startswith('_') and term in m.lower())
        return {'matches': hits[:300], 'total': len(hits)}

    name = args['name']
    parts = name.split('.')
    if parts[0] != 'adsk':
        for mod in ('fusion', 'core'):
            if hasattr(getattr(adsk, mod), parts[0]):
                parts = ['adsk', mod] + parts
                break
    obj = adsk
    for p in parts[1:]:
        obj = getattr(obj, p)
    res = {'name': '.'.join(parts), 'doc': inspect.getdoc(obj)}
    if isinstance(obj, type):
        members = []
        for m in dir(obj):
            if m.startswith('_') or m in ('this', 'thisown'):
                continue
            doc = inspect.getdoc(getattr(obj, m, None)) or ''
            members.append({'name': m, 'doc': doc.strip().split('\n')[0][:200]})
        res['members'] = members
    return res


def cmd_reload(args):
    importlib.reload(sys.modules[__package__])
    importlib.reload(fdm)
    importlib.reload(helpers)
    importlib.reload(mesh_io)
    importlib.reload(sys.modules[__name__])
    return {'reloaded': ['fdm', 'helpers', 'mesh_io', 'commands']}


COMMANDS = {
    'ping': cmd_ping, 'new': cmd_new, 'save': cmd_save, 'exec': cmd_exec,
    'rollback': cmd_rollback, 'tree': cmd_tree, 'params': cmd_params,
    'screenshot': cmd_screenshot, 'export': cmd_export, 'fdm': cmd_fdm,
    'api': cmd_api, 'reload': cmd_reload,
}


def dispatch(command, args):
    expected = args.pop('_document_id', None)
    if expected is not None:
        doc = _app().activeDocument
        if doc is None or str(doc.creationId) != str(expected):
            raise ValueError('Active document changed. Read ping/tree and choose the document again.')
    fn = COMMANDS.get(command)
    if fn is None:
        raise ValueError('Unknown command %r. Available: %s' % (command, ', '.join(sorted(COMMANDS))))
    return fn(args)
