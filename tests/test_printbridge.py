import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'cli'))
from printbridge.presets import Presets, configuration
from printbridge.studio import inspect_project, sha256
from printbridge.jobs import handoff, prepare, record, status


def project(path, sliced=True):
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('3D/3dmodel.model', '<model unit="millimeter"/>')
        z.writestr('Metadata/project_settings.config', json.dumps({
            'printer_settings_id': 'Bambu Lab A1 0.4 nozzle',
            'curr_bed_type': 'Textured PEI Plate', 'nozzle_diameter': ['0.4'],
            'filament_settings_id': ['PLA']}))
        if sliced:
            z.writestr('Metadata/plate_1.gcode', '; total estimated time: 2m 1s\nG1 X1\n')
            z.writestr('Metadata/slice_info.config', '''<config><plate>
                <metadata key="index" value="1"/><metadata key="prediction" value="121"/>
                <metadata key="weight" value="2.5"/><metadata key="outside" value="false"/>
                <warning msg="check me" level="2"/></plate></config>''')


class PresetTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for kind in ('machine', 'process', 'filament'):
            (self.root / kind).mkdir()

    def preset(self, kind, name, **data):
        (self.root / kind / (name + '.json')).write_text(json.dumps(dict(name=name, **data)))

    def test_inheritance_and_included_gcode_are_fully_resolved(self):
        self.preset('machine', 'base', speed='100', machine_start_gcode='BASE')
        self.preset('machine', 'startup', machine_start_gcode='G28\nM109 S220')
        self.preset('machine', 'A1', inherits='base', include=['startup'], speed='80',
                    instantiation='true')
        full, sources = Presets(self.root).resolve('machine', 'A1')
        self.assertEqual(full['machine_start_gcode'], 'G28\nM109 S220')
        self.assertEqual(full['speed'], '80')
        self.assertNotIn('inherits', full)
        self.assertNotIn('include', full)
        self.assertEqual(len(sources), 3)

    def test_cycles_and_missing_includes_fail(self):
        self.preset('machine', 'A', inherits='B')
        self.preset('machine', 'B', inherits='A')
        with self.assertRaisesRegex(ValueError, 'cycle'):
            Presets(self.root).resolve('machine', 'A')
        self.preset('machine', 'C', include=['missing'])
        with self.assertRaisesRegex(ValueError, 'Unknown'):
            Presets(self.root).resolve('machine', 'C')

    def test_incompatible_nozzle_preset_is_rejected(self):
        self.preset('machine', 'Bambu Lab A1 0.4 nozzle', default_filament_profile=['PLA'])
        self.preset('process', 'wrong', compatible_printers=['Bambu Lab A1 0.2 nozzle'])
        self.preset('filament', 'PLA')
        with self.assertRaisesRegex(ValueError, 'compatible'):
            configuration(Presets(self.root), process='wrong')

    def test_machine_gcode_cannot_be_overridden_as_process(self):
        self.preset('machine', 'Bambu Lab A1 0.4 nozzle', default_filament_profile=['PLA'])
        self.preset('process', 'default', layer_height='0.2')
        self.preset('filament', 'PLA', filament_type=['PLA'])
        with self.assertRaisesRegex(ValueError, 'Unsupported'):
            configuration(Presets(self.root), process='default',
                          overrides={'machine_start_gcode': 'arbitrary'})


class ProjectTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_mesh_only_3mf_is_not_reported_as_sliced(self):
        p = self.root / 'mesh.3mf'
        project(p, False)
        self.assertFalse(inspect_project(p)['sliced'])

    def test_estimates_and_warnings_survive_inspection(self):
        p = self.root / 'sliced.3mf'
        project(p)
        report = inspect_project(p)
        self.assertEqual(report['plates'][0]['estimated_seconds'], 121)
        self.assertEqual(report['plates'][0]['filament_grams'], 2.5)
        self.assertEqual(report['plates'][0]['warnings'][0]['msg'], 'check me')
        self.assertEqual(report['plates'][0]['statistics']['total estimated time'], '2m 1s')

    def job(self):
        p = self.root / 'project.3mf'
        project(p)
        hashes = {}
        for kind in ('machine', 'process', 'filament'):
            config = self.root / (kind + '.json')
            config.write_text('{}')
            hashes[kind] = sha256(config)
        manifest = {'status': 'sliced_needs_visual_review', 'settings_sha256': hashes,
                    'project': inspect_project(p), 'selection': {}}
        (self.root / 'job.json').write_text(json.dumps(manifest))

    def test_changed_gcode_project_cannot_be_handed_to_printer(self):
        self.job()
        self.assertTrue(handoff(self.root)['ok'])
        with zipfile.ZipFile(self.root / 'project.3mf', 'a') as z:
            z.writestr('changed.txt', 'modified after slicing')
        with self.assertRaisesRegex(ValueError, 'changed'):
            handoff(self.root)

    def test_changed_preset_blocks_handoff(self):
        self.job()
        (self.root / 'machine.json').write_text('{"nozzle":"wrong"}')
        with self.assertRaisesRegex(ValueError, 'Preset changed'):
            handoff(self.root)

    def test_failed_job_cannot_be_handed_off(self):
        (self.root / 'job.json').write_text('{"status":"failed"}')
        with self.assertRaisesRegex(ValueError, 'successfully sliced'):
            handoff(self.root)

    def test_prepare_preserves_existing_directory(self):
        p = self.root / 'part.stl'
        p.write_bytes(b'test input')
        marker = self.root / 'do-not-overwrite'
        marker.write_text('original')
        with self.assertRaisesRegex(ValueError, 'already exists'):
            prepare([p], self.root)
        self.assertEqual(marker.read_text(), 'original')

    def test_uncertain_submission_cannot_be_retried(self):
        self.job()
        record(self.root, 'submission_pending', 'A1', 'Dialog verified before Send')
        record(self.root, 'unknown', 'A1', 'Lost GUI response after Send')
        with self.assertRaisesRegex(ValueError, 'already has a submission'):
            handoff(self.root)
        with self.assertRaisesRegex(ValueError, 'Invalid cloud state'):
            record(self.root, 'submission_pending', 'A1', 'retry')
        self.assertFalse(status(self.root)['live_telemetry'])

    def test_completion_requires_a_previous_attempt(self):
        self.job()
        with self.assertRaisesRegex(ValueError, 'Invalid cloud state'):
            record(self.root, 'completed', 'A1', 'No actual attempt')

    def test_observed_task_cannot_change_printer_midway(self):
        self.job()
        record(self.root, 'submission_pending', 'A1', 'Ready to submit')
        with self.assertRaisesRegex(ValueError, 'Printer changed'):
            record(self.root, 'printing', 'another A1', 'Wrong device selected')

    def test_two_agents_cannot_reserve_the_same_submission(self):
        self.job()
        def attempt(_):
            try:
                record(self.root, 'submission_pending', 'A1', 'Ready to submit')
                return True
            except ValueError:
                return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(attempt, range(2)))
        self.assertEqual(sum(results), 1)


if __name__ == '__main__':
    unittest.main()
