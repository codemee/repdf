import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    'regression_fingerprint', Path(__file__).parents[1] / 'scripts/regression_fingerprint.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def write_inputs(root, version='1.0', dependency='2.0'):
    (root / 'pyproject.toml').write_text(
        f'[project]\nname="repdf"\nversion="{version}"\n', encoding='utf-8')
    lock = (f'[[package]]\nname="repdf"\nversion="{version}"\nsource={{editable="."}}\n'
            f'[[package]]\nname="dependency"\nversion="{dependency}"\n')
    (root / 'uv.lock').write_text(lock, encoding='utf-8')
    (root / 'third_party').mkdir(exist_ok=True)
    (root / 'third_party/locked-packages.json').write_text(
        json.dumps({'lock_sha256': hashlib.sha256(lock.encode()).hexdigest(), 'packages': []}),
        encoding='utf-8')


def key(root):
    return module.fingerprint(root, [p.relative_to(root).as_posix()
                                    for p in root.rglob('*') if p.is_file()])


def test_docs_and_release_version_reuse_but_dependencies_invalidate(tmp_path):
    write_inputs(tmp_path)
    original = key(tmp_path)
    (tmp_path / 'README.md').write_text('New release notes')
    (tmp_path / 'docs').mkdir()
    (tmp_path / 'docs/guide.md').write_text('Updated instructions')
    write_inputs(tmp_path, version='1.1')
    assert key(tmp_path) == original
    write_inputs(tmp_path, version='1.1', dependency='3.0')
    assert key(tmp_path) != original


@pytest.mark.parametrize('path', ['src/app.py', 'tests/test_app.py', 'packaging/app.spec',
                                  '.github/workflows/regression.yml', 'NOTICE', 'src/icon.png'])
def test_code_tests_build_settings_and_assets_invalidate(tmp_path, path):
    write_inputs(tmp_path)
    target = tmp_path / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b'first')
    original = key(tmp_path)
    target.write_bytes(b'second')
    assert key(tmp_path) != original


def test_stale_license_audit_cannot_reuse_success(tmp_path):
    write_inputs(tmp_path)
    with (tmp_path / 'uv.lock').open('a', encoding='utf-8') as stream:
        stream.write('\n# changed lock\n')
    with pytest.raises(ValueError, match='License audit'):
        key(tmp_path)


def test_inconsistent_release_version_cannot_reuse_success(tmp_path):
    write_inputs(tmp_path)
    (tmp_path / 'pyproject.toml').write_text('[project]\nversion="9.0"\n')
    with pytest.raises(ValueError, match='versions differ'):
        key(tmp_path)
