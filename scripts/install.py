#!/usr/bin/env python3
"""Install only owned symlinks; no downloads, account access or shell configuration."""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def exists(path):
    return path.exists() or path.is_symlink()


def target(path):
    return str(path.resolve()) if path.is_symlink() else None


def load_receipt(path):
    if not path.exists():
        return {}
    data = json.loads(path.read_text())
    if (not isinstance(data, dict) or data.get('version') != 1
            or not isinstance(data.get('links'), dict)
            or not all(isinstance(dst, str) and isinstance(src, str)
                       and Path(dst).is_absolute() and Path(src).is_absolute()
                       for dst, src in data['links'].items())):
        raise ValueError('Unrecognized installation receipt: %s' % path)
    return data['links']


def write_receipt(path, links):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='install-', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump({'version': 1, 'links': links}, stream, indent=2)
            stream.write('\n')
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def plan(args, home):
    links = {
        home / '.local/bin/f360': ROOT / 'cli/f360',
        home / '.local/bin/b360': ROOT / 'cli/b360',
    }
    if not args.skip_fusion:
        autodesk = home / 'Library/Application Support/Autodesk'
        if args.fusion_addins or autodesk.is_dir():
            addins = (Path(args.fusion_addins).expanduser().absolute() if args.fusion_addins
                      else autodesk / 'Autodesk Fusion 360/API/AddIns')
            links[addins / 'FusionBridge'] = ROOT / 'addin/FusionBridge'
        else:
            print('SKIP Fusion add-in: open Fusion once, then run this installer again.')
    if args.agent in ('codex', 'both'):
        # Retain an existing legacy installation without creating duplicate skill entries.
        legacy = home / '.codex/skills/fusion360'
        destination = legacy if exists(legacy) else home / '.agents/skills/fusion360'
        links[destination] = ROOT / 'skill/fusion360'
    if args.agent in ('claude', 'both'):
        links[home / '.claude/skills/fusion360'] = ROOT / 'skill/fusion360'
    return links


def install(args, home, receipt, owned):
    links = plan(args, home)
    # Check the whole plan before changing anything, including broken symlinks.
    for dst, src in links.items():
        if not src.exists():
            raise ValueError('Missing checkout file: %s' % src)
        if exists(dst) and target(dst) not in (str(src.resolve()), owned.get(str(dst))):
            raise ValueError('Refusing to replace existing file or unrelated link: %s' % dst)
        # A regular file must never count as owned, even with a stale receipt.
        if exists(dst) and not dst.is_symlink():
            raise ValueError('Refusing to replace existing file: %s' % dst)
        for parent in dst.parents:
            if exists(parent) and not parent.is_dir():
                raise ValueError('Destination parent is not a directory: %s' % parent)
    for dst, src in links.items():
        print('%s %s -> %s' % ('PLAN' if args.dry_run else 'LINK', dst, src))
    if args.dry_run:
        return
    previous = {}
    try:
        for dst, src in links.items():
            previous[dst] = os.readlink(dst) if dst.is_symlink() else None
            dst.parent.mkdir(parents=True, exist_ok=True)
            if dst.is_symlink():
                dst.unlink()
            dst.symlink_to(src)
        updated = dict(owned)
        updated.update({str(dst): str(src.resolve()) for dst, src in links.items()})
        write_receipt(receipt, updated)
    except OSError:
        # Restore links already touched if the installation cannot complete.
        for dst, old in reversed(list(previous.items())):
            if dst.is_symlink():
                dst.unlink()
            if old is not None:
                dst.symlink_to(old)
        raise
    print('Installed. Keep this checkout in place; activate FusionBridge in Fusion Add-Ins.')
    print('If needed, add to your shell: export PATH="$HOME/.local/bin:$PATH"')


def uninstall(args, home, receipt, owned):
    # Also recognize links from the original installer, which had no receipt.
    candidates = dict(owned)
    legacy_args = argparse.Namespace(skip_fusion=False, fusion_addins=args.fusion_addins,
                                     agent='both')
    for dst, src in plan(legacy_args, home).items():
        if target(dst) == str(src.resolve()):
            candidates[str(dst)] = str(src.resolve())
    for name, src in candidates.items():
        dst = Path(name)
        if not exists(dst):
            continue
        if target(dst) != src:
            print('KEEP modified or unrelated destination: %s' % dst)
            # Do not retain ownership over destinations the user has replaced.
            continue
        print('%s %s' % ('PLAN REMOVE' if args.dry_run else 'REMOVE', dst))
        if not args.dry_run:
            dst.unlink()
    if not args.dry_run and receipt.exists():
        receipt.unlink()
    print('Checkout, models, application settings and connection data are preserved.')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--agent', choices=('codex', 'claude', 'both', 'none'), default='both',
                        help='skill destinations (default: both); CLIs are always installed')
    parser.add_argument('--skip-fusion', action='store_true', help='install CLIs/skills only')
    parser.add_argument('--fusion-addins', metavar='DIR', help='custom Fusion AddIns directory')
    parser.add_argument('--home', metavar='DIR', help='alternative user root (isolated testing)')
    parser.add_argument('--dry-run', action='store_true', help='print changes without writing')
    parser.add_argument('--uninstall', action='store_true', help='remove owned links only')
    args = parser.parse_args(argv)
    if sys.version_info < (3, 9):
        parser.error('Python 3.9 or newer is required')
    if sys.platform != 'darwin':
        parser.error('Automatic installation currently supports macOS only')
    home = Path(args.home).expanduser().absolute() if args.home else Path.home()
    receipt = home / '.fusion-bridge/install.json'
    try:
        owned = load_receipt(receipt)
        if args.uninstall:
            uninstall(args, home, receipt, owned)
        else:
            install(args, home, receipt, owned)
    except (OSError, ValueError) as exc:
        print('ERROR: %s' % exc, file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
