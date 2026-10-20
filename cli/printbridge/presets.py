"""Resolve installed Bambu presets, including inheritance and G-code includes."""
import copy
import json
from pathlib import Path


class Presets:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.index = {}
        for kind in ('machine', 'process', 'filament'):
            self.index[kind] = {}
            for path in sorted((self.root / kind).glob('*.json')):
                data = json.loads(path.read_text())
                name = data.get('name', path.stem)
                if name in self.index[kind]:
                    raise ValueError('Duplicate installed preset: %s' % name)
                self.index[kind][name] = (data, path)

    def resolve(self, kind, name, trail=()):
        key = (kind, name)
        if key in trail:
            raise ValueError('Preset inheritance/include cycle: %s' % repr(trail + (key,)))
        try:
            data, path = self.index[kind][name]
        except KeyError:
            raise ValueError('Unknown %s preset: %s' % (kind, name))
        merged, sources = {}, []
        parents = data.get('inherits', [])
        if isinstance(parents, str):
            parents = [parents] if parents else []
        for parent in list(parents) + list(data.get('include', [])):
            inherited, inherited_sources = self.resolve(kind, parent, trail + (key,))
            merged.update(inherited)
            sources.extend(inherited_sources)
        merged.update(copy.deepcopy(data))
        # CLI inputs must be full configs. Preserve exact system names/identifiers.
        merged.pop('inherits', None)
        merged.pop('include', None)
        sources.append(str(path))
        return merged, list(dict.fromkeys(sources))

    def list(self, kind, search='', compatible=None):
        found = []
        for name, (data, _) in self.index[kind].items():
            if str(data.get('instantiation', 'false')).lower() != 'true':
                continue
            if search.casefold() not in name.casefold():
                continue
            config, _ = self.resolve(kind, name)
            machines = config.get('compatible_printers', [])
            if compatible and machines and compatible not in machines:
                continue
            found.append(name)
        return sorted(found)


PURPOSES = {
    '0.4': {'balanced': '0.20mm Standard @BBL A1', 'strength': '0.20mm Strength @BBL A1',
            'detail': '0.12mm High Quality @BBL A1', 'draft': '0.24mm Draft @BBL A1'},
    '0.2': {'balanced': '0.10mm Standard @BBL A1 0.2 nozzle',
            'strength': '0.10mm Standard @BBL A1 0.2 nozzle',
            'detail': '0.08mm High Quality @BBL A1 0.2 nozzle',
            'draft': '0.12mm Draft @BBL A1 0.2 nozzle'},
}

PLATES = {'textured': 'Textured PEI Plate', 'smooth': 'High Temp Plate',
          'cool': 'Cool Plate', 'supertack': 'Cool Plate SuperTack'}


def configuration(catalog, nozzle='0.4', purpose='balanced', filament=None, process=None,
                  plate='textured', supports='auto', overrides=None):
    machine_name = 'Bambu Lab A1 %s nozzle' % nozzle
    machine, machine_sources = catalog.resolve('machine', machine_name)
    process_name = process or PURPOSES[nozzle][purpose]
    process_config, process_sources = catalog.resolve('process', process_name)
    filament_name = filament or machine['default_filament_profile'][0]
    filament_config, filament_sources = catalog.resolve('filament', filament_name)
    for config in (process_config, filament_config):
        compatible = config.get('compatible_printers', [])
        if compatible and machine_name not in compatible:
            raise ValueError('%s is not compatible with %s' % (config['name'], machine_name))
    material = filament_config.get('filament_type', [])
    if material and material[0] not in ('PLA', 'PETG'):
        raise ValueError('This A1 workflow currently supports PLA and PETG presets only')
    changes = {'enable_support': '0' if supports == 'none' else '1'}
    if supports != 'none':
        changes['support_type'] = 'tree(auto)' if supports == 'tree' else 'normal(auto)'
    if purpose == 'strength' and nozzle == '0.2':
        changes.update(wall_loops='4', sparse_infill_density='25%')
    allowed = {'layer_height', 'wall_loops', 'sparse_infill_density', 'sparse_infill_pattern',
               'top_shell_layers', 'bottom_shell_layers', 'brim_type', 'brim_width',
               'support_on_build_plate_only', 'support_threshold_angle', 'seam_position'}
    for key, value in (overrides or {}).items():
        if key not in allowed or key not in process_config:
            raise ValueError('Unsupported process override: %s' % key)
        old = process_config[key]
        changes[key] = [value] if isinstance(old, list) else value
    process_config.update(changes)
    if 'layer_height' in process_config:
        height = float(process_config['layer_height'])
        if not 0 < height <= float(nozzle) * 0.8:
            raise ValueError('Layer height must be positive and <= 80% of the nozzle diameter')
    return {'machine': machine, 'process': process_config, 'filament': filament_config,
            'selection': {'printer': machine_name, 'nozzle_mm': float(nozzle), 'purpose': purpose,
                          'process': process_name, 'filament': filament_name,
                          'plate': PLATES[plate], 'supports': supports},
            'process_overrides': changes,
            'sources': {'machine': machine_sources, 'process': process_sources,
                        'filament': filament_sources}}
