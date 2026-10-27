import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import tomllib

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('collect_licenses', ROOT / 'scripts/collect_licenses.py')
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)


def test_every_locked_dependency_has_reviewed_terms_and_notices():
    lock = tomllib.loads((ROOT / 'uv.lock').read_text(encoding='utf-8'))
    review = json.loads((ROOT / 'third_party/locked-packages.json').read_text(encoding='utf-8'))
    assert review['lock_sha256'] == hashlib.sha256((ROOT / 'uv.lock').read_text(encoding='utf-8').encode()).hexdigest()
    expected = {(p['name'], p['version']) for p in lock['package'] if p['name'] != 'repdf'}
    assert expected == {(p['name'], p['version']) for p in review['packages']}
    for package in review['packages']:
        assert package['reviewed_license']
        assert package['notice_files']
        assert all((ROOT / file).is_file() for file in package['notice_files'])


def test_actual_environment_notices_and_fallback_are_collected(tmp_path):
    destination = tmp_path / 'licenses'
    count, files = collector.collect(destination)
    assert count > 20 and files > 300
    inventory = json.loads((destination / 'environment.json').read_text(encoding='utf-8'))
    flatbuffers = next(p for p in inventory['packages'] if p['name'] == 'flatbuffers')
    assert all((destination / p).is_file() for p in flatbuffers['notice_files'])
    sums = json.loads((destination / 'SHA256SUMS.json').read_text(encoding='utf-8'))
    assert all(hashlib.sha256((destination / p).read_bytes()).hexdigest() == digest for p, digest in sums.items())
    assert 'qt-everywhere-src-6.11.2' in (destination / 'SOURCES.txt').read_text()
    assert (destination / 'PYTHON-LICENSE.txt').is_file()


def test_changed_lock_or_unreviewed_installed_version_stops_collection(tmp_path):
    root = tmp_path / 'source'
    (root / 'third_party').mkdir(parents=True)
    (root / 'third_party/locked-packages.json').write_bytes((ROOT / 'third_party/locked-packages.json').read_bytes())
    (root / 'uv.lock').write_text('changed lock')
    with pytest.raises(ValueError, match='uv.lock changed'):
        collector.collect(tmp_path / 'out', root=root)
    wrong = SimpleNamespace(metadata={'Name': 'PySide6'}, version='999.0')
    with pytest.raises(ValueError, match='Unreviewed installed dependency'):
        collector.collect(tmp_path / 'out', distributions=[wrong])
    assert not (tmp_path / 'out').exists()


def test_qt_module_scope_in_windows_and_macos_binaries():
    assert collector.check_qt_binaries([
        ('PySide6/Qt6Core.dll', '', ''),
        ('PySide6/Qt/lib/QtWidgets.framework/Versions/A/QtWidgets', '', ''),
        ('PySide6/Qt6Svg.dll', '', ''),
    ]) == ['Core', 'Svg', 'Widgets']
    with pytest.raises(ValueError, match='Unreviewed Qt binary modules'):
        collector.check_qt_binaries([('PySide6/Qt6Quick.dll', '', '')])


def test_unused_qt_pdf_plugin_does_not_remove_pdfium_or_other_image_plugins():
    used = [('pypdfium2_raw/pdfium.dll', '', ''), ('PySide6/plugins/imageformats/qjpeg.dll', '', ''),
            ('PySide6/Qt6Core.dll', '', ''),
            ('PySide6/plugins/platforminputcontexts/libibusplatforminputcontextplugin.so', '', '')]
    extra = [('PySide6/plugins/imageformats/qpdf.dll', '', ''), ('PySide6/Qt6Pdf.dll', '', ''),
             ('PySide6/Qt/plugins/imageformats/libqpdf.dylib', '', ''),
             ('PySide6/Qt/lib/QtPdf.framework/Versions/A/QtPdf', '', ''),
             ('PySide6/plugins/platforminputcontexts/qtvirtualkeyboardplugin.dll', '', ''),
             ('PySide6/Qt/lib/QtQuick.framework/Versions/A/QtQuick', '', ''),
             ('PySide6/Qt/lib/QtVirtualKeyboardQml.framework/Versions/A/QtVirtualKeyboardQml', '', ''),
             ('PySide6/Qt/lib/QtVirtualKeyboardQml.framework/Resources/Info.plist', '', ''),
             ('PySide6/Qt/qml/QtQuick/Controls/qmldir', '', ''),
             ('PySide6/Qt6QmlMeta.dll', '', '')]
    assert collector.without_unused_qt_plugins(used + extra) == used


def test_python_license_is_found_in_unix_stdlib_and_windows_prefix(tmp_path):
    prefix = tmp_path / 'python'
    library = prefix / 'lib/python3.12'
    library.mkdir(parents=True)
    (library / 'LICENSE.txt').write_text('Unix CPython license')
    assert collector.python_license_path(prefix, library) == library / 'LICENSE.txt'
    (prefix / 'LICENSE.txt').write_text('Windows CPython license')
    assert collector.python_license_path(prefix, library) == prefix / 'LICENSE.txt'


def test_reviewed_models_match_current_catalog_and_real_weights():
    from repdf.ocr_models import PROFILES
    import rapidocr
    models = json.loads((ROOT / 'third_party/models.json').read_text())
    expected = {key for key, item in PROFILES.items() if 'url' in item}
    assert expected == {p['profile'] for p in models['downloadable']}
    for model in models['downloadable']:
        assert model['license'] == 'Apache-2.0'
        assert model['sha256'] == PROFILES[model['profile']]['sha256']
        assert model['artifact_url'] == PROFILES[model['profile']]['url']
        assert (ROOT / model['card_file']).is_file()
    root = Path(rapidocr.__file__).parent
    for model in models['bundled']:
        path = next(root.rglob(model['name']))
        assert hashlib.sha256(path.read_bytes()).hexdigest() == model['sha256']
