"""Installer behavior in isolated directories; never changes the actual user setup."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('fusionbridge_install', REPO / 'scripts/install.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory(prefix='fusionbridge-install-')
        self.addCleanup(self.work.cleanup)
        self.base = Path(self.work.name).resolve()
        self.home = self.base / 'test user'
        self.checkout = self.base / 'checkout with spaces'
        for name in ('cli/f360', 'cli/b360', 'scripts/install.py', 'install.sh'):
            dst = self.checkout / name
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / name, dst)
        shutil.copytree(REPO / 'cli/printbridge', self.checkout / 'cli/printbridge',
                        ignore=shutil.ignore_patterns('__pycache__'))
        (self.checkout / 'addin/FusionBridge').mkdir(parents=True)
        (self.checkout / 'skill/fusion360').mkdir(parents=True)
        self.root_patch = patch.object(installer, 'ROOT', self.checkout)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)
        self.platform_patch = patch.object(sys, 'platform', 'darwin')
        self.platform_patch.start()
        self.addCleanup(self.platform_patch.stop)
        self.receipt = self.home / '.fusion-bridge/install.json'

    def run_installer(self, *args):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return installer.main(['--home', str(self.home), *args])

    def test_fresh_install_and_idempotent_rerun(self):
        autodesk = self.home / 'Library/Application Support/Autodesk'
        autodesk.mkdir(parents=True)
        self.assertEqual(self.run_installer(), 0)
        expected = {
            '.local/bin/f360': 'cli/f360', '.local/bin/b360': 'cli/b360',
            '.agents/skills/fusion360': 'skill/fusion360',
            '.claude/skills/fusion360': 'skill/fusion360',
            'Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns/FusionBridge':
                'addin/FusionBridge',
        }
        for dst, src in expected.items():
            self.assertEqual((self.home / dst).resolve(), self.checkout / src)
        self.assertEqual(self.run_installer(), 0)
        self.assertEqual(len(json.loads(self.receipt.read_text())['links']), 5)
        for cli in ('f360', 'b360'):
            run = subprocess.run([str(self.home / '.local/bin' / cli), '--help'],
                                 capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)

    def test_dry_run_leaves_home_absent(self):
        self.assertEqual(self.run_installer('--dry-run'), 0)
        self.assertFalse(self.home.exists())

    def test_conflicting_file_prevents_all_links(self):
        conflict = self.home / '.claude/skills/fusion360'
        conflict.parent.mkdir(parents=True)
        conflict.write_text('existing user file')
        self.assertEqual(self.run_installer(), 1)
        self.assertEqual(conflict.read_text(), 'existing user file')
        self.assertFalse((self.home / '.local').exists())
        self.assertFalse(self.receipt.exists())

    def test_unrelated_broken_link_is_preserved(self):
        conflict = self.home / '.local/bin/b360'
        conflict.parent.mkdir(parents=True)
        other = self.base / 'unrelated missing executable'
        conflict.symlink_to(other)
        self.assertEqual(self.run_installer(), 1)
        self.assertEqual(conflict.readlink(), other)
        self.assertFalse((self.home / '.local/bin/f360').exists())

    def test_moved_checkout_updates_only_recorded_links(self):
        self.assertEqual(self.run_installer(), 0)
        moved = self.base / 'moved checkout'
        self.checkout.rename(moved)
        with patch.object(installer, 'ROOT', moved):
            self.assertEqual(self.run_installer(), 0)
        self.assertEqual((self.home / '.local/bin/f360').resolve(), moved / 'cli/f360')

    def test_uninstall_preserves_replaced_files_and_connection_data(self):
        self.assertEqual(self.run_installer(), 0)
        changed = self.home / '.local/bin/b360'
        changed.unlink()
        changed.write_text('replacement')
        connection = self.home / '.fusion-bridge/connection.json'
        connection.write_text('synthetic fixture')
        self.assertEqual(self.run_installer('--uninstall', '--dry-run'), 0)
        self.assertTrue((self.home / '.local/bin/f360').is_symlink())
        self.assertEqual(self.run_installer('--uninstall'), 0)
        self.assertFalse((self.home / '.local/bin/f360').is_symlink())
        self.assertEqual(changed.read_text(), 'replacement')
        self.assertEqual(connection.read_text(), 'synthetic fixture')
        self.assertFalse(self.receipt.exists())
        self.assertTrue((self.checkout / 'cli/f360').exists())

    def test_legacy_owned_skill_does_not_create_duplicate(self):
        legacy = self.home / '.codex/skills/fusion360'
        legacy.parent.mkdir(parents=True)
        legacy.symlink_to(self.checkout / 'skill/fusion360')
        self.assertEqual(self.run_installer('--agent', 'codex', '--skip-fusion'), 0)
        self.assertTrue(legacy.is_symlink())
        self.assertFalse((self.home / '.agents').exists())
        self.assertFalse((self.home / '.claude').exists())
        self.assertEqual(self.run_installer('--uninstall'), 0)
        self.assertFalse(legacy.is_symlink())

    def test_receipt_failure_restores_previous_links(self):
        self.assertEqual(self.run_installer('--agent', 'none'), 0)
        old = (self.home / '.local/bin/f360').readlink()
        before = self.receipt.read_bytes()
        with patch.object(installer, 'write_receipt', side_effect=OSError('synthetic failure')):
            self.assertEqual(self.run_installer(), 1)
        self.assertEqual((self.home / '.local/bin/f360').readlink(), old)
        self.assertFalse((self.home / '.agents/skills/fusion360').is_symlink())
        self.assertEqual(self.receipt.read_bytes(), before)

    def test_invalid_receipt_fails_without_changes(self):
        for content in ('[]', '{"version":1,"links":{"relative":"also relative"}}', 'not json'):
            self.receipt.parent.mkdir(parents=True, exist_ok=True)
            self.receipt.write_text(content)
            self.assertEqual(self.run_installer(), 1)
            self.assertFalse((self.home / '.local').exists())

    def test_custom_addins_directory_and_no_agent(self):
        addins = self.base / 'custom AddIns'
        self.assertEqual(self.run_installer('--fusion-addins', str(addins), '--agent', 'none'), 0)
        self.assertEqual((addins / 'FusionBridge').resolve(), self.checkout / 'addin/FusionBridge')
        self.assertFalse((self.home / '.agents').exists())
        self.assertEqual(self.run_installer('--uninstall'), 0)
        self.assertFalse((addins / 'FusionBridge').is_symlink())


if __name__ == '__main__':
    unittest.main()
