"""Identify regression inputs, excluding documentation and release version bumps."""
from __future__ import annotations

import hashlib
import json
import subprocess
import tomllib
from pathlib import Path


def fingerprint(root: Path, paths: list[str]) -> str:
    project = tomllib.loads((root / 'pyproject.toml').read_text(encoding='utf-8'))
    lock_text = (root / 'uv.lock').read_text(encoding='utf-8')
    lock = tomllib.loads(lock_text)
    own = next(p for p in lock['package']
               if p['name'] == 'repdf' and p.get('source') == {'editable': '.'})
    if own['version'] != project['project']['version']:
        raise ValueError('Project and lock versions differ')
    project['project']['version'] = own['version'] = '<release-version>'
    audit = json.loads((root / 'third_party/locked-packages.json').read_text(encoding='utf-8'))
    if audit['lock_sha256'] != hashlib.sha256(lock_text.encode()).hexdigest():
        raise ValueError('License audit does not match uv.lock')
    audit['lock_sha256'] = '<validated-lock-digest>'
    normalized = {'pyproject.toml': project, 'uv.lock': lock,
                  'third_party/locked-packages.json': audit}
    digest = hashlib.sha256()
    for name in sorted(paths):
        # Keep legal notices and all executable/build/test inputs in the key.
        if (name.startswith('docs/') and name.endswith('.md')) or name in {'README.md', 'README.en.md'}:
            continue
        if name in normalized:
            data = json.dumps(normalized[name], sort_keys=True, default=str).encode()
        else:
            data = (root / name).read_bytes()
            if Path(name).suffix in {'.py', '.json', '.toml', '.lock', '.yml', '.yaml', '.md', '.txt', '.spec'}:
                data = data.replace(b'\r\n', b'\n')
        digest.update(name.encode() + b'\0' + hashlib.sha256(data).digest())
    return digest.hexdigest()


if __name__ == '__main__':
    root = Path(__file__).resolve().parents[1]
    paths = subprocess.check_output(['git', 'ls-files', '-z'], cwd=root).decode().split('\0')
    print(fingerprint(root, [p for p in paths if p]))
