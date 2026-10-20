"""Bambu Studio CLI adapter. Never reads account credentials or submits prints."""
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import zipfile


def locate(app=None):
    selected = app or os.environ.get('BAMBU_STUDIO_APP') or '/Applications/BambuStudio.app'
    path = Path(selected).expanduser().resolve()
    if path.suffix == '.app':
        binary = path / 'Contents/MacOS/BambuStudio'
        resources = path / 'Contents/Resources/profiles/BBL'
        with (path / 'Contents/Info.plist').open('rb') as f:
            version = plistlib.load(f).get('CFBundleShortVersionString')
    else:
        binary, version = path, None
        resource_var = os.environ.get('BAMBU_STUDIO_PROFILES')
        if not resource_var:
            raise ValueError('Set BAMBU_STUDIO_PROFILES to the installed profiles/BBL folder')
        resources = Path(resource_var).expanduser().resolve()
    if not binary.is_file() or not os.access(binary, os.X_OK):
        raise ValueError('Bambu Studio executable not found: %s' % binary)
    if not (resources / 'machine').is_dir():
        raise ValueError('Bambu Studio preset directory not found: %s' % resources)
    return {'binary': str(binary), 'profiles': str(resources), 'version': version}


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def doctor(app=None):
    info = locate(app)
    # Studio writes result.json even for --help; isolate it from the caller's directory.
    with tempfile.TemporaryDirectory(prefix='b360-doctor-') as work:
        run = subprocess.run([info['binary'], '--help'], cwd=work, capture_output=True,
                             text=True, timeout=30)
    required = ['--load-settings', '--load-filaments', '--slice', '--export-3mf', '--datadir']
    missing = [flag for flag in required if flag not in run.stdout]
    return dict(info, ok=run.returncode == 0 and not missing, missing_options=missing,
                cloud_transport='Bambu Studio authenticated GUI',
                cloud_login_verified=False, printer_online_verified=False)


def inspect_project(path):
    """Read slicer evidence without extracting G-code to arbitrary archive paths."""
    path = Path(path).resolve()
    if not path.is_file() or path.suffix.lower() != '.3mf':
        raise ValueError('Expected an existing .3mf project')
    with zipfile.ZipFile(path) as archive:
        bad = archive.testzip()
        if bad:
            raise ValueError('Corrupt 3MF member: %s' % bad)
        names = archive.namelist()
        gcodes = [n for n in names if re.fullmatch(r'Metadata/plate_\d+\.gcode', n)]
        models = [n for n in names if n.lower().endswith('.model')]
        units = []
        for name in models:
            if archive.getinfo(name).file_size > 64 * 1024 * 1024:
                continue
            units.append(ET.fromstring(archive.read(name)).get('unit', 'millimeter'))
        plates = []
        slice_metadata = {}
        if 'Metadata/slice_info.config' in names:
            tree = ET.fromstring(archive.read('Metadata/slice_info.config'))
            for plate in tree.findall('plate'):
                metadata = {v.get('key'): v.get('value') for v in plate.findall('metadata')}
                slice_metadata[metadata.get('index')] = {
                    'estimated_seconds': float(metadata['prediction']) if metadata.get('prediction') else None,
                    'filament_grams': float(metadata['weight']) if metadata.get('weight') else None,
                    'outside': metadata.get('outside'),
                    'warnings': [dict(v.attrib) for v in plate.findall('warning')],
                    'filaments': [dict(v.attrib) for v in plate.findall('filament')]}
        for name in gcodes:
            if archive.getinfo(name).file_size == 0:
                raise ValueError('Empty sliced G-code member: %s' % name)
            # Header statistics are near the beginning; do not load multi-GB G-code.
            with archive.open(name) as stream:
                header = stream.read(128 * 1024).decode('utf-8', errors='replace')
            stats = {}
            for line in header.split('; CONFIG_BLOCK_START', 1)[0].splitlines():
                if line.startswith(';') and ':' in line:
                    for item in line[1:].split(';'):
                        if ':' in item:
                            key, value = item.split(':', 1)
                            stats[key.strip()] = value.strip()
            index = re.search(r'plate_(\d+)', name).group(1)
            plates.append({'gcode': name, 'bytes': archive.getinfo(name).file_size,
                           'statistics': stats, **slice_metadata.get(index, {})})
        config = {}
        if 'Metadata/project_settings.config' in names:
            config = json.loads(archive.read('Metadata/project_settings.config'))
        chosen = {k: config[k] for k in ('printer_settings_id', 'printer_model', 'nozzle_diameter',
                  'print_settings_id', 'filament_settings_id', 'filament_type', 'curr_bed_type',
                  'layer_height', 'wall_loops', 'sparse_infill_density', 'enable_support',
                  'support_type') if k in config}
    return {'ok': True, 'path': str(path), 'sha256': sha256(path), 'units': units,
            'sliced': bool(plates), 'plate_count': len(plates), 'plates': plates,
            'settings': chosen, 'zip_integrity': 'passed'}


def run_slice(info, files, work, configs, plate, orientation, timeout):
    work = Path(work)
    for kind in ('machine', 'process', 'filament'):
        (work / (kind + '.json')).write_text(json.dumps(configs[kind], ensure_ascii=False, indent=2))
    data = work / 'studio-data'
    data.mkdir()
    # Full settings are supplied explicitly. Do not share the logged-in GUI's data directory.
    command = [info['binary'], '--datadir', str(data), '--load-settings',
               str(work / 'machine.json') + ';' + str(work / 'process.json'),
               '--load-filaments', str(work / 'filament.json'), '--curr-bed-type', plate,
               '--check-preset', '--arrange', '1', '--orient', '1' if orientation == 'auto' else '0',
               '--slice', '0', '--export-3mf', 'project.3mf',
               '--outputdir', str(work), '--debug', '2'] + [str(f) for f in files]
    (work / 'command.json').write_text(json.dumps(command, ensure_ascii=False, indent=2))
    with (work / 'slicer.log').open('w') as log:
        try:
            run = subprocess.run(command, cwd=work, stdout=log, stderr=subprocess.STDOUT,
                                 timeout=timeout)
        except subprocess.TimeoutExpired:
            raise ValueError('Slicing timed out; process stopped. See %s' % (work / 'slicer.log'))
    result_path = work / 'result.json'
    result = json.loads(result_path.read_text()) if result_path.exists() else {}
    if run.returncode or result.get('return_code', 0):
        raise ValueError('Bambu slicing failed (exit %s, result %s). See %s' %
                         (run.returncode, result.get('error_string'), work / 'slicer.log'))
    project = inspect_project(work / 'project.3mf')
    if not project['sliced']:
        raise ValueError('Bambu returned no sliced plates; job is not ready')
    return project, result, command
