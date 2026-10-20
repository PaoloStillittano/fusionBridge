"""Immutable preparation bundles and evidence-based cloud handoff."""
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil

from . import VERSION
from .presets import Presets, configuration
from .studio import inspect_project, locate, run_slice, sha256


def prepare(inputs, out, app=None, nozzle='0.4', purpose='balanced', filament=None,
            process=None, plate='textured', supports='auto', orientation='preserve',
            overrides=None, timeout=600):
    files = [Path(p).expanduser().resolve() for p in inputs]
    if not files:
        raise ValueError('At least one STL or 3MF input is required')
    if not 0 < timeout <= 7200:
        raise ValueError('Slicing timeout must be between 0 and 7200 seconds')
    for path in files:
        if not path.is_file() or path.suffix.lower() not in ('.stl', '.3mf'):
            raise ValueError('Expected existing STL or 3MF input: %s' % path)
    dest = Path(out).expanduser().resolve()
    if dest.exists():
        raise ValueError('Output directory already exists; use a new job directory: %s' % dest)
    info = locate(app)
    config = configuration(Presets(info['profiles']), nozzle, purpose, filament, process,
                           plate, supports, overrides)
    dest.parent.mkdir(parents=True, exist_ok=True)
    # Reserve the bundle before invoking Studio; a failed job is retained for diagnostics.
    dest.mkdir()
    manifest = {'schema': 1, 'tool_version': VERSION,
                'created_at': datetime.now(timezone.utc).isoformat(), 'status': 'preparing',
                'transport': 'bambu_studio_cloud_gui', 'studio': info,
                'selection': config['selection'], 'orientation': orientation,
                'process_overrides': config['process_overrides'], 'sources': config['sources'],
                'inputs': [], 'cloud_state': 'not_submitted'}
    manifest_path = dest / 'job.json'
    try:
        source_dir = dest / 'inputs'
        source_dir.mkdir()
        for i, path in enumerate(files, 1):
            target = source_dir / ('%02d-' % i + path.name)
            shutil.copy2(path, target)
            manifest['inputs'].append({'original': str(path), 'copy': str(target),
                                       'sha256': sha256(target)})
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
        project, result, command = run_slice(info, [v['copy'] for v in manifest['inputs']], dest,
                                             config, config['selection']['plate'], orientation, timeout)
        settings = project['settings']
        selected = config['selection']
        if (settings.get('printer_settings_id') != selected['printer']
                or settings.get('curr_bed_type') != selected['plate']
                or settings.get('filament_settings_id') != [selected['filament']]
                or settings.get('nozzle_diameter') != [str(selected['nozzle_mm'])]):
            raise ValueError('Sliced project settings do not match the requested setup')
        if any(p.get('outside') == 'true' for p in project['plates']):
            raise ValueError('Sliced project contains objects outside the plate')
        manifest.update(status='sliced_needs_visual_review', project=project, slicer_result=result,
                        command=command)
        # Snapshot every setting used, including inherited machine G-code.
        manifest['settings_sha256'] = {k: sha256(dest / (k + '.json'))
                                      for k in ('machine', 'process', 'filament')}
    except Exception as error:
        manifest.update(status='failed', error=str(error))
        raise
    finally:
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    return manifest


def handoff(job):
    path = Path(job).expanduser().resolve()
    if path.is_dir():
        path /= 'job.json'
    manifest = json.loads(path.read_text())
    if manifest.get('cloud_state', 'not_submitted') != 'not_submitted':
        raise ValueError('This job already has a submission attempt. Inspect its cloud status; do not resend')
    if manifest.get('status') != 'sliced_needs_visual_review':
        raise ValueError('Only successfully sliced jobs can be handed to Bambu Studio')
    folder = path.parent
    for kind, digest in manifest['settings_sha256'].items():
        if sha256(folder / (kind + '.json')) != digest:
            raise ValueError('Preset changed after slicing: %s; prepare a new job' % kind)
    project = inspect_project(folder / 'project.3mf')
    if project['sha256'] != manifest['project']['sha256'] or not project['sliced']:
        raise ValueError('Sliced project changed; prepare a new job before submission')
    return {'ok': True, 'job': str(path), 'project': project['path'], 'sha256': project['sha256'],
            'selection': manifest['selection'], 'plates': project['plates'],
            'cloud_state': 'not_submitted', 'requires': ['visual_review_of_sliced_plates',
                'matching_printer_nozzle_plate_and_filament', 'online_idle_printer',
                'user_request_for_this_specific_print'],
            'transport': 'Use the authenticated Bambu Studio GUI; no account secrets are copied',
            'submission_rule': 'After an uncertain Send result, inspect Device before retrying'}


def status(job):
    path = Path(job).expanduser().resolve()
    if path.is_dir():
        path /= 'job.json'
    manifest = json.loads(path.read_text())
    return {'ok': True, 'job': str(path), 'status': manifest.get('status'),
            'cloud_state': manifest.get('cloud_state', 'not_submitted'),
            'observations': manifest.get('cloud_observations', []),
            'live_telemetry': False}


def record(job, state, printer, evidence, task_id=None):
    """Persist an agent/user observation; never infer a printer state from a local file."""
    import fcntl
    path = Path(job).expanduser().resolve()
    if path.is_dir():
        path /= 'job.json'
    with (path.parent / '.cloud-state.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        return _record_locked(path, state, printer, evidence, task_id)


def _record_locked(path, state, printer, evidence, task_id):
    if not printer.strip() or not evidence.strip():
        raise ValueError('A printer name and an actual GUI observation are required')
    allowed = {'not_submitted': {'submission_pending'},
               'submission_pending': {'submitted', 'printing', 'failed', 'unknown'},
               'submitted': {'printing', 'completed', 'failed', 'unknown'},
               'printing': {'printing', 'completed', 'failed', 'unknown'},
               'unknown': {'submitted', 'printing', 'completed', 'failed'},
               'failed': set(), 'completed': set()}
    if state not in {'submission_pending', 'submitted', 'printing', 'completed', 'failed', 'unknown'}:
        raise ValueError('Unknown cloud observation state')
    manifest = json.loads(path.read_text())
    old = manifest.get('cloud_state', 'not_submitted')
    if state not in allowed.get(old, set()):
        raise ValueError('Invalid cloud state transition: %s -> %s' % (old, state))
    if old == 'not_submitted':
        handoff(path)  # verify the exact files before reserving a submission attempt
    previous = manifest.get('cloud_observations', [])
    if previous and previous[0]['printer'] != printer:
        raise ValueError('Printer changed during this job; resolve the existing attempt first')
    manifest.setdefault('cloud_observations', []).append({
        'at': datetime.now(timezone.utc).isoformat(), 'state': state, 'printer': printer,
        'evidence': evidence, 'task_id': task_id, 'source': 'observed_in_gui'})
    manifest['cloud_state'] = state
    temporary = path.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    temporary.replace(path)
    return status(path)
