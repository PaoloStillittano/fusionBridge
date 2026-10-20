"""Portable mm exports for MeshBody, which Fusion's BRep exporters may silently skip."""
import math
import os
import struct
import uuid
import xml.etree.ElementTree as ET
import zipfile


def export(path, coords, indices, name='mesh'):
    if (not coords or not indices or len(coords) % 3 or len(indices) % 3
            or any(not math.isfinite(v) for v in coords)
            or any(not isinstance(i, int) or not 0 <= i < len(coords) // 3 for i in indices)):
        raise ValueError('Invalid or empty triangle mesh')
    fmt = os.path.splitext(path)[1].lower()
    if fmt not in ('.stl', '.3mf'):
        raise ValueError('Mesh export supports STL and 3MF')
    temporary = path + '.' + uuid.uuid4().hex + '.tmp'
    try:
        if fmt == '.stl':
            with open(temporary, 'wb') as f:
                f.write(b'FusionBridge mesh export; units mm'.ljust(80, b' '))
                f.write(struct.pack('<I', len(indices) // 3))
                for t in range(0, len(indices), 3):
                    points = [coords[i * 3:i * 3 + 3] for i in indices[t:t + 3]]
                    a, b, c = points
                    u, v = [b[k] - a[k] for k in range(3)], [c[k] - a[k] for k in range(3)]
                    n = [u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0]]
                    length = math.sqrt(sum(x*x for x in n))
                    n = [x / length for x in n] if length else [0, 0, 0]
                    f.write(struct.pack('<12fH', *(n + a + b + c), 0))
        else:
            ns = 'http://schemas.microsoft.com/3dmanufacturing/core/2015/02'
            ET.register_namespace('', ns)
            def tag(n):
                return '{%s}%s' % (ns, n)
            model = ET.Element(tag('model'), unit='millimeter', attrib={'{http://www.w3.org/XML/1998/namespace}lang': 'en-US'})
            resources = ET.SubElement(model, tag('resources'))
            obj = ET.SubElement(resources, tag('object'), id='1', type='model', name=name)
            mesh = ET.SubElement(obj, tag('mesh'))
            vertices, triangles = ET.SubElement(mesh, tag('vertices')), ET.SubElement(mesh, tag('triangles'))
            for i in range(0, len(coords), 3):
                ET.SubElement(vertices, tag('vertex'), **dict(zip(('x', 'y', 'z'),
                    (format(v, '.10g') for v in coords[i:i+3]))))
            for i in range(0, len(indices), 3):
                ET.SubElement(triangles, tag('triangle'), **dict(zip(('v1', 'v2', 'v3'),
                    (str(v) for v in indices[i:i+3]))))
            ET.SubElement(ET.SubElement(model, tag('build')), tag('item'), objectid='1')
            with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_DEFLATED) as z:
                z.writestr('3D/3dmodel.model', ET.tostring(model, encoding='utf-8', xml_declaration=True))
                z.writestr('[Content_Types].xml', '''<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>''')
                z.writestr('_rels/.rels', '''<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>''')
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)
