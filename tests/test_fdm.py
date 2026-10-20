import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'addin', 'FusionBridge'))
from fbridge import fdm  # noqa: E402

# unit cube, outward counter-clockwise winding
_V = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)]
_T = [(0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7), (0, 1, 5), (0, 5, 4),
      (2, 3, 7), (2, 7, 6), (0, 4, 7), (0, 7, 3), (1, 2, 6), (1, 6, 5)]


def box(lo, hi, coords, indices, flip=False):
    base = len(coords) // 3
    for v in _V:
        coords.extend(lo[k] + v[k] * (hi[k] - lo[k]) for k in range(3))
    for t in _T:
        indices.extend(base + i for i in (reversed(t) if flip else t))


class FdmTest(unittest.TestCase):
    def test_floating_cube_has_no_global_bed_contact(self):
        c, i = [], []
        box((0, 0, 50), (10, 10, 60), c, i)
        r = fdm.analyze(c, i)
        self.assertEqual(r['bed_contact_mm2'], 0)
        self.assertEqual(r['bed_gap_mm'], 50)
        self.assertTrue(any('floating' in w for w in r['warnings']))

    def test_part_mode_explicitly_uses_its_own_base(self):
        c, i = [], []
        box((0, 0, 50), (10, 10, 60), c, i)
        r = fdm.analyze(c, i, bed_z=None)
        self.assertEqual(r['bed_contact_mm2'], 100)
        self.assertEqual(r['bed_reference'], 'body_minimum')

    def test_body_below_plate_is_not_a_valid_fit(self):
        c, i = [], []
        box((0, 0, -5), (10, 10, 5), c, i)
        r = fdm.analyze(c, i, bed_size=(256, 256, 256))
        self.assertFalse(r['fits_bed'])
        self.assertTrue(any('below' in w for w in r['warnings']))

    def test_invalid_geometry_fails_instead_of_false_validation(self):
        for coords, indices in [([float('nan'), 0, 0], [0, 0, 0]),
                                ([0, 0, 0], [0, 0, 8]), ([0, 0], [])]:
            with self.assertRaises(ValueError):
                fdm.analyze(coords, indices)

    def test_cube_on_bed(self):
        c, i = [], []
        box((0, 0, 0), (10, 10, 10), c, i)
        r = fdm.analyze(c, i)
        self.assertAlmostEqual(r['bed_contact_mm2'], 100.0)
        self.assertEqual(r['overhang_area_mm2'], 0.0)
        self.assertEqual(r['bbox_mm']['size'], [10, 10, 10])
        self.assertEqual(r['warnings'], [])

    def test_t_shape_reports_bridge(self):
        c, i = [], []
        box((10, 0, 0), (20, 10, 10), c, i)    # stem
        box((0, 0, 10), (30, 10, 15), c, i)    # top slab, overhanging 10 mm each side
        r = fdm.analyze(c, i, bed_size=(20, 20, 20))
        self.assertAlmostEqual(r['bed_contact_mm2'], 100.0)
        self.assertAlmostEqual(r['overhang_area_mm2'], 300.0)  # slab underside
        region = r['overhang_regions'][0]
        self.assertEqual(region['kind'], 'bridge')
        self.assertEqual(region['z_range_mm'], [10, 10])
        self.assertEqual(region['min_span_mm'], 10)
        self.assertFalse(r['fits_bed'])  # 30 mm wide on a 20 mm bed

    def test_winding_fixed_by_normals(self):
        c, i = [], []
        box((0, 0, 0), (10, 10, 10), c, i, flip=True)
        normals = []
        for v in _V:  # outward per-node normals of the cube
            normals.extend(1 if v[k] else -1 for k in range(3))
        r = fdm.analyze(c, i, normals=normals)
        self.assertAlmostEqual(r['bed_contact_mm2'], 100.0)
        self.assertEqual(r['overhang_area_mm2'], 0.0)

    def test_45_deg_chamfer_not_flagged(self):
        # flat triangle on the bed + a downward face at exactly 45 deg above it
        c = [0, 0, 0, 10, 0, 0, 0, 10, 0,
             0, 0, 5, 0, 10, 5, 10, 0, 15]
        i = [0, 2, 1, 3, 4, 5]
        self.assertEqual(fdm.analyze(c, i)['overhang_area_mm2'], 0.0)
        self.assertGreater(fdm.analyze(c, i, angle_tol=0.0, overhang_deg=40)['overhang_area_mm2'], 0)

    def test_point_contact_warning(self):
        c = [0, 0, 0, 10, 0, 5, 0, 10, 5, 10, 10, 5]
        i = [0, 2, 1, 1, 2, 3]
        r = fdm.analyze(c, i)
        self.assertIn('No flat face on the bed', r['warnings'][0])


if __name__ == '__main__':
    unittest.main()
