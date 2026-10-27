"""Collect reviewed notices for the actual build environment, without building."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata as metadata
import json
from pathlib import Path
import re
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]


def check_qt_binaries(binaries):
    """Reject newly collected Qt modules outside the reviewed source scope."""
    reviewed = {'Core', 'Gui', 'Widgets', 'Network', 'PrintSupport', 'OpenGL',
                'OpenGLWidgets', 'DBus', 'Svg', 'SvgWidgets'}
    found = set()
    for entry in binaries:
        name = str(entry[0]).replace('\\', '/')
        match = re.search(r'(?:^|/)(?:lib)?Qt6([A-Za-z0-9]+)\.(?:dll|dylib|so)', name)
        if not match:
            match = re.search(r'(?:^|/)Qt([A-Za-z0-9]+)\.framework/', name)
        if match:
            found.add(match[1])
    if found - reviewed:
        raise ValueError(f'Unreviewed Qt binary modules: {sorted(found - reviewed)}')
    return sorted(found)


def canonical(name):
    return re.sub(r'[-_.]+', '-', name).lower()


def is_notice(path):
    return any(re.search(r'license|licence|notice|copying|copyright|authors', part, re.I)
               for part in path.parts)


def collect(destination, *, root=ROOT, distributions=None, python_license=None):
    destination = Path(destination)
    review = json.loads((root / 'third_party/locked-packages.json').read_text(encoding='utf-8'))
    digest = hashlib.sha256((root / 'uv.lock').read_text(encoding='utf-8').encode()).hexdigest()
    if digest != review['lock_sha256']:
        raise ValueError('uv.lock changed: review third-party licenses before release.')
    reviewed = {(canonical(p['name']), p['version']): p for p in review['packages']}
    expected_names = {name for name, _ in reviewed}
    installed = list(metadata.distributions() if distributions is None else distributions)
    for dist in installed:
        name = canonical(dist.metadata['Name'])
        if name in expected_names and (name, dist.version) not in reviewed:
            raise ValueError(f'Unreviewed installed dependency: {name} {dist.version}')
    destination.mkdir(parents=True, exist_ok=True)
    # The snapshot is a conservative superset, covering conditional dependencies
    # and official Qt source notices absent from the wheel's metadata.
    shutil.copytree(root / 'third_party', destination / 'third_party', dirs_exist_ok=True)
    for name in ('LICENSE', 'NOTICE', 'THIRD_PARTY_NOTICES.md'):
        shutil.copy2(root / name, destination / name)
    (destination / 'docs').mkdir(exist_ok=True)
    for name in ('LICENSE_AUDIT.md', 'LICENSE_AUDIT.en.md'):
        shutil.copy2(root / 'docs' / name, destination / 'docs' / name)
    inventory = []
    for dist in installed:
        name = canonical(dist.metadata['Name'])
        if name not in expected_names:
            continue
        copied = []
        for file in dist.files or ():
            if '..' in file.parts or not is_notice(file):
                continue
            source = Path(dist.locate_file(file))
            if not source.is_file():
                continue
            target = destination / 'environment' / name / str(file)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            copied.append(target.relative_to(destination).as_posix())
        if not copied:
            record = reviewed[name, dist.version]
            for file in record['notice_files']:
                source = root / file
                if not source.is_file():
                    raise FileNotFoundError(f'Missing reviewed license material: {source}')
                copied.append(file)
            if not copied:
                raise ValueError(f'Missing license material: {name} {dist.version}')
        inventory.append({'name': name, 'version': dist.version, 'notice_files': sorted(copied)})
    python_license = Path(python_license) if python_license else Path(sys.base_prefix) / 'LICENSE.txt'
    if not python_license.is_file():
        raise FileNotFoundError(f'Python license not found: {python_license}')
    shutil.copy2(python_license, destination / 'PYTHON-LICENSE.txt')
    (destination / 'environment.json').write_text(json.dumps({
        'python': sys.version, 'platform': sys.platform,
        'scope': 'Build environment; a conservative superset of shipped modules.',
        'packages': sorted(inventory, key=lambda p: p['name']),
    }, indent=2) + '\n', encoding='utf-8')
    sources = ['Corresponding source locations for this build',
               'RePDF source and build instructions: https://github.com/codemee/repdf/tags',
               'Choose the release tag matching the executable version.',
               'Python: https://www.python.org/ftp/python/' + sys.version.split()[0] + '/',
               '', 'Locked Python dependency source archives (hashes in third_party/locked-packages.json):']
    for record in review['packages']:
        if record.get('sdist'):
            sources.append(f"{record['name']} {record['version']}: {record['sdist']['url']}")
        elif record.get('source_wheel'):
            sources.append(f"{record['name']} {record['version']} (Python source wheel): {record['source_wheel']['url']}")
    sources += ['', 'Additional native/source locations:']
    locations = json.loads((root / 'third_party/source-locations.json').read_text(encoding='utf-8'))
    sources += [f"{entry['name']}: {entry['url']}" for entry in locations['sources']]
    (destination / 'SOURCES.txt').write_text('\n'.join(sources) + '\n', encoding='utf-8')
    files = {p.relative_to(destination).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in sorted(destination.rglob('*')) if p.is_file() and p.name != 'SHA256SUMS.json'}
    (destination / 'SHA256SUMS.json').write_text(json.dumps(files, indent=2) + '\n', encoding='utf-8')
    return len(inventory), len(files)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    packages, files = collect(args.destination)
    print(f'Collected {files} files for {packages} installed dependency distributions.')
