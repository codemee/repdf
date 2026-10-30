"""Exercise registration without touching the actual user registry."""
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from repdf import desktop_integration as integration


def test_register_unregister_preserves_shared_keys_and_defaults(monkeypatch):
    values = {
        r'Software\Classes\.pdf\OpenWithProgids': {'Other.PDF': ''},
        r'Software\RegisteredApplications': {'Other': 'Software\\Other'},
        r'Software\Classes\.pdf': {'': 'Other.PDF'},
    }
    class Key:
        def __init__(self, path):
            self.path = path
        def __enter__(self):
            return self
        def __exit__(self, *_):
            pass
    def create(_root, path):
        pieces = path.split('\\')
        for end in range(1, len(pieces) + 1):
            values.setdefault('\\'.join(pieces[:end]), {})
        return Key(path)
    def open_key(_root, path, *_):
        if path not in values:
            raise FileNotFoundError(path)
        return Key(path)
    def delete_key(_root, path):
        if path not in values:
            raise FileNotFoundError(path)
        assert not any(other.startswith(path + '\\') for other in values)
        del values[path]
    def delete_value(key, name):
        if name not in values[key.path]:
            raise FileNotFoundError(name)
        del values[key.path][name]
    fake = SimpleNamespace(HKEY_CURRENT_USER=1, KEY_SET_VALUE=2, REG_SZ=3,
                           CreateKey=create, OpenKey=open_key, DeleteKey=delete_key,
                           DeleteValue=delete_value,
                           SetValueEx=lambda key, name, _reserved, _kind, value:
                               values[key.path].__setitem__(name, value))
    monkeypatch.setitem(sys.modules, 'winreg', fake)
    monkeypatch.setattr(integration, 'notify_shell', lambda: None)
    monkeypatch.setattr(integration, 'launch_command', lambda: ('repdf "%1"', 'repdf.exe,0'))
    monkeypatch.setattr(integration, 'install_application_icon', lambda: '"RePDF icon.ico",0')
    integration.register_windows()
    assert values[r'Software\RegisteredApplications']['RePDF'] == integration.APP_KEY
    assert values[integration.APP_KEY]['ApplicationIcon'] == '"RePDF icon.ico",0'
    assert values[r'Software\Classes\RePDF.PDF\Application']['ApplicationIcon'] == '"RePDF icon.ico",0'
    integration.unregister_windows()
    integration.unregister_windows()  # Safe to repeat.
    assert values[r'Software\Classes\.pdf\OpenWithProgids'] == {'Other.PDF': ''}
    assert values[r'Software\RegisteredApplications'] == {'Other': 'Software\\Other'}
    assert values[r'Software\Classes\.pdf'] == {'': 'Other.PDF'}
    assert not any(path.startswith(integration.CONTEXT_KEY) for path in values)


def test_frozen_registration_installs_fixed_path_and_updates_atomically(monkeypatch, tmp_path):
    source = tmp_path / 'new version.exe'
    source.write_bytes(b'new executable')
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, 'executable', str(source))
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'local'))
    command, icon = integration.launch_command()
    destination = tmp_path / 'local/Programs/RePDF/repdf.exe'
    assert destination.read_bytes() == source.read_bytes()
    assert str(destination) in command and command.endswith('"%1"')
    assert str(destination) in icon
    source.write_bytes(b'updated executable')
    integration.launch_command()
    assert destination.read_bytes() == b'updated executable'
    monkeypatch.setattr(integration.os, 'replace', lambda *_: (_ for _ in ()).throw(PermissionError('busy')))
    with pytest.raises(PermissionError):
        integration.launch_command()
    assert destination.read_bytes() == b'updated executable'
    assert not list(destination.parent.glob('*.new'))


def test_shell_icon_is_a_stable_multisize_ico(tmp_path):
    from PIL import Image
    location = integration.install_application_icon(tmp_path / 'with spaces')
    icon_path = tmp_path / 'with spaces/repdf.ico'
    assert location == f'"{icon_path}",0'
    with Image.open(icon_path) as icon:
        assert icon.format == 'ICO'
        assert {(16, 16), (20, 20), (32, 32), (48, 48), (256, 256)} <= icon.ico.sizes()
        assert icon.convert('RGBA').getchannel('A').getbbox()
