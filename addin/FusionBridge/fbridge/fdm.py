"""FDM printability analysis on a triangle mesh. Pure Python, no adsk imports.

Conventions: coordinates in mm, +Z is the build direction, the bed defaults to Z=0.
Overhang angle is measured from vertical, like slicers do: 0 deg = vertical wall,
90 deg = horizontal ceiling. A downward face is an overhang when its angle > threshold.
"""
import math

BRIDGE_DEG = 85.0  # overhang regions flatter than this are reported as bridges / flat ceilings
PLA_DENSITY_G_MM3 = 1.24e-3


def analyze(coords, indices, normals=None, overhang_deg=45.0, bed_size=None,
            bed_tol=0.05, weld=1e-3, max_regions=10, min_region_mm2=0.5, angle_tol=2.0,
            bed_z=0.0):
    """coords: flat [x0,y0,z0,x1,...] in mm. indices: flat triangle node indices.
    normals: optional flat per-node normals, used to fix triangle winding.
    bed_size: optional (x, y, z) build volume in mm.
    angle_tol: degrees of slack on the threshold, so exact 45 deg chamfers are not flagged
    because of tessellation noise. bed_z=None explicitly evaluates the part as if dropped
    onto its own lowest Z; it does not validate its placement on a shared plate."""
    if not 0 <= overhang_deg < 90 or not math.isfinite(overhang_deg):
        raise ValueError('overhang_deg must be finite and between 0 and 90 (exclusive)')
    if len(coords) % 3 or len(indices) % 3 or any(not math.isfinite(c) for c in coords):
        raise ValueError('Invalid mesh coordinates or triangle indices')
    if bed_z is not None and not math.isfinite(bed_z):
        raise ValueError('bed_z must be finite')
    if bed_size and (len(bed_size) != 3 or any(not math.isfinite(v) or v <= 0 for v in bed_size)):
        raise ValueError('Build volume must contain three positive finite dimensions')
    n_nodes = len(coords) // 3
    if any(not isinstance(i, int) or not 0 <= i < n_nodes for i in indices):
        raise ValueError('Triangle index outside mesh nodes')
    if n_nodes == 0 or len(indices) < 3:
        return {'triangles': 0, 'warnings': ['empty mesh']}

    # Weld duplicated nodes (meshes are often split per B-rep face) so regions connect.
    key_to_id, remap, pts = {}, [0] * n_nodes, []
    for i in range(n_nodes):
        x, y, z = coords[3 * i], coords[3 * i + 1], coords[3 * i + 2]
        key = (round(x / weld), round(y / weld), round(z / weld))
        j = key_to_id.get(key)
        if j is None:
            j = len(pts)
            key_to_id[key] = j
            pts.append((x, y, z))
        remap[i] = j

    xs, ys, zs = [p[0] for p in pts], [p[1] for p in pts], [p[2] for p in pts]
    lo = (min(xs), min(ys), min(zs))
    hi = (max(xs), max(ys), max(zs))
    zmin = lo[2] if bed_z is None else bed_z
    sin_t = math.sin(math.radians(min(overhang_deg + angle_tol, 90.0)))

    total_area = bed_area = 0.0
    over = []  # (verts, area, angle_deg, centroid)
    for t in range(len(indices) // 3):
        i0, i1, i2 = indices[3 * t], indices[3 * t + 1], indices[3 * t + 2]
        a, b, c = pts[remap[i0]], pts[remap[i1]], pts[remap[i2]]
        ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
        vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
        nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
        ln = math.sqrt(nx * nx + ny * ny + nz * nz)
        if ln == 0.0:
            continue
        if normals:
            mx = normals[3 * i0] + normals[3 * i1] + normals[3 * i2]
            my = normals[3 * i0 + 1] + normals[3 * i1 + 1] + normals[3 * i2 + 1]
            mz = normals[3 * i0 + 2] + normals[3 * i1 + 2] + normals[3 * i2 + 2]
            if nx * mx + ny * my + nz * mz < 0:
                nz = -nz
        area = ln / 2.0
        nz /= ln
        total_area += area
        if nz >= -sin_t:
            continue
        if min(a[2], b[2], c[2]) >= zmin - bed_tol and max(a[2], b[2], c[2]) <= zmin + bed_tol:
            bed_area += area
            continue
        angle = math.degrees(math.asin(min(1.0, -nz)))
        centroid = ((a[0] + b[0] + c[0]) / 3, (a[1] + b[1] + c[1]) / 3, (a[2] + b[2] + c[2]) / 3)
        over.append(((remap[i0], remap[i1], remap[i2]), area, angle, centroid))

    regions = _regions(over, pts, min_region_mm2)
    overhang_area = sum(o[1] for o in over)
    size = [hi[k] - lo[k] for k in range(3)]

    report = {
        'triangles': len(indices) // 3,
        'bbox_mm': {'min': _r(lo), 'max': _r(hi), 'size': _r(size)},
        'surface_area_mm2': round(total_area, 1),
        'bed_z_mm': round(zmin, 3),
        'bed_reference': 'body_minimum' if bed_z is None else 'global_plane',
        'bed_gap_mm': round(lo[2] - zmin, 3),
        'bed_contact_mm2': round(bed_area, 1),
        'overhang_area_mm2': round(overhang_area, 1),
        'overhang_regions': regions[:max_regions],
        'overhang_region_count': len(regions),
    }

    warnings = []
    if lo[2] > zmin + bed_tol:
        warnings.append('Body is floating %.3g mm above the bed.' % (lo[2] - zmin))
    elif lo[2] < zmin - bed_tol:
        warnings.append('Body extends %.3g mm below the bed.' % (zmin - lo[2]))
    if bed_area < 1.0:
        warnings.append('No flat face on the bed: the part touches the bed at an edge or point. '
                        'Reorient it or add a flat base.')
    elif size[2] > 4 * math.sqrt(bed_area):
        warnings.append('Tall part on a small footprint (%.0f mm high, %.0f mm2 on bed): '
                        'risk of tipping, consider a brim or a wider base.' % (size[2], bed_area))
    bridges = [r for r in regions if r['kind'] == 'bridge']
    long_bridges = [r for r in bridges if r['min_span_mm'] > 10]
    if long_bridges:
        warnings.append('%d flat ceiling/bridge region(s) wider than 10 mm on both axes: '
                        'needs supports or redesign.' % len(long_bridges))
    if any(r['kind'] == 'overhang' for r in regions):
        warnings.append('Overhangs steeper than %g deg: add supports, or redesign '
                        '(45 deg chamfers instead of fillets underneath, teardrop holes).' % overhang_deg)
    if bed_size:
        bx, by, bz = bed_size
        fits = (lo[2] >= zmin - bed_tol and hi[2] <= zmin + bz + bed_tol
                and ((size[0] <= bx and size[1] <= by) or (size[0] <= by and size[1] <= bx)))
        report['fits_bed'] = fits
        if not fits:
            warnings.append('Does not fit the %gx%gx%g mm build volume.' % (bx, by, bz))
    report['warnings'] = warnings
    return report


def _regions(over, pts, min_area):
    """Group overhang triangles that share a vertex into regions."""
    parent = list(range(len(over)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    owner = {}
    for k, (verts, _, _, _) in enumerate(over):
        for v in verts:
            if v in owner:
                ra, rb = find(k), find(owner[v])
                if ra != rb:
                    parent[ra] = rb
            else:
                owner[v] = k

    groups = {}
    for k in range(len(over)):
        groups.setdefault(find(k), []).append(k)

    regions = []
    for members in groups.values():
        area = sum(over[k][1] for k in members)
        if area < min_area:
            continue
        vs = {v for k in members for v in over[k][0]}
        rx = [pts[v][0] for v in vs]
        ry = [pts[v][1] for v in vs]
        rz = [pts[v][2] for v in vs]
        angle = sum(over[k][2] * over[k][1] for k in members) / area
        cx = sum(over[k][3][0] * over[k][1] for k in members) / area
        cy = sum(over[k][3][1] * over[k][1] for k in members) / area
        cz = sum(over[k][3][2] * over[k][1] for k in members) / area
        sx, sy = max(rx) - min(rx), max(ry) - min(ry)
        regions.append({
            'kind': 'bridge' if angle >= BRIDGE_DEG else 'overhang',
            'area_mm2': round(area, 1),
            'mean_angle_deg': round(angle, 1),
            'z_range_mm': [round(min(rz), 2), round(max(rz), 2)],
            'center_mm': _r((cx, cy, cz)),
            'xy_size_mm': _r((sx, sy)),
            'min_span_mm': round(min(sx, sy), 2),
        })
    regions.sort(key=lambda r: -r['area_mm2'])
    return regions


def _r(values, nd=2):
    return [round(v, nd) for v in values]
