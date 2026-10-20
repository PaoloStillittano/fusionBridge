"""Run with `f360 exec examples/plate.py` after `f360 new`; dimensions in mm.

Creates a 40 x 30 x 4 plate with two diameter-3.4 through holes, 24 mm apart.
Only thickness is linked to a user parameter; sketch dimensions are numeric.
"""
if (root.bRepBodies.count or root.meshBodies.count or root.occurrences.count
        or root.sketches.count or design.timeline.count):
    raise RuntimeError('This example needs an empty document. Run f360 new first.')

h.param('plate_thickness', 4)
sketch = h.sketch('xy', name='plate_outline')
h.rect(sketch, 40, 30)
h.circle(sketch, 3.4, center=(-12, 0))
h.circle(sketch, 3.4, center=(12, 0))
plate = h.extrude(h.profile(sketch, 'largest'), 'plate_thickness', name='plate').bodies.item(0)
plate.name = 'example_plate'
result = h.bbox(plate)
