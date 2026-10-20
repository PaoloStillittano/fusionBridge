import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'addin/FusionBridge'))
from fbridge import mesh_io


class MeshExportTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.coords = [-10., 0., 0., 10., 0., 0., 0., 20., 0.]

    def test_stl_contains_actual_mm_coordinates_and_normal(self):
        path = self.root / 'part.stl'
        mesh_io.export(str(path), self.coords, [0, 1, 2])
        data = path.read_bytes()
        self.assertEqual(len(data), 134)
        self.assertEqual(struct.unpack_from('<I', data, 80)[0], 1)
        floats = struct.unpack_from('<12fH', data, 84)
        self.assertEqual(list(floats[3:12]), self.coords)
        self.assertEqual(floats[:3], (0., 0., 1.))

    def test_3mf_build_uses_mm_and_preserves_vertex_indices(self):
        path = self.root / 'part.3mf'
        mesh_io.export(str(path), self.coords, [0, 1, 2], 'mesh & name')
        with zipfile.ZipFile(path) as z:
            self.assertIsNone(z.testzip())
            model = ET.fromstring(z.read('3D/3dmodel.model'))
            ns = {'m': 'http://schemas.microsoft.com/3dmanufacturing/core/2015/02'}
            self.assertEqual(model.get('unit'), 'millimeter')
            self.assertEqual(model.find('m:build/m:item', ns).get('objectid'), '1')
            self.assertEqual(len(model.findall('.//m:vertex', ns)), 3)
            self.assertEqual(model.find('.//m:triangle', ns).attrib, {'v1':'0','v2':'1','v3':'2'})

    def test_bad_mesh_cannot_replace_a_previous_export(self):
        path = self.root / 'part.stl'
        path.write_bytes(b'previous export')
        with self.assertRaises(ValueError):
            mesh_io.export(str(path), self.coords, [0, 1, 8])
        self.assertEqual(path.read_bytes(), b'previous export')
