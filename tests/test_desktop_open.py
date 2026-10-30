import json
import uuid
import subprocess
import sys
from pathlib import Path

import pytest
from PySide6.QtCore import QObject
from PySide6.QtNetwork import QLocalSocket

from repdf.desktop_open import DesktopInstance, file_arguments
from repdf.desktop_integration import registration_entries, launch_command


class Receiver(QObject):
    def __init__(self):
        super().__init__()
        self.requests = []

    def open_files(self, paths):
        self.requests.append(paths)


def test_file_arguments_preserve_unicode_spaces_and_multiple_paths(tmp_path):
    paths = [tmp_path / '中文 空白.pdf', tmp_path / '-second.pdf']
    assert file_arguments(['--', *map(str, paths)]) == list(map(str, paths))
    assert file_arguments([]) == []
    with pytest.raises(SystemExit):
        file_arguments(['--unknown'])


def test_later_launch_delivers_multiple_files_to_lock_owner(qtbot, tmp_path):
    receiver = Receiver()
    name = 'repdf-test-' + uuid.uuid4().hex
    first = DesktopInstance(receiver, name)
    paths = [str(tmp_path / '中文 文件.pdf'), str(tmp_path / 'another.pdf')]
    try:
        assert first.start([])
        # Use a real second process: Windows named pipes require the receiving
        # thread to keep servicing its event loop during the sender's write.
        script = '''
import json, sys
from PySide6.QtCore import QCoreApplication
from repdf.desktop_open import DesktopInstance
app = QCoreApplication([])
instance = DesktopInstance(app, sys.argv[1])
assert not instance.start(json.loads(sys.argv[2]))
'''
        process = subprocess.Popen([sys.executable, '-c', script, name, json.dumps(paths)],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        qtbot.waitUntil(lambda: process.poll() is not None, timeout=15000)
        assert process.returncode == 0, process.communicate()[1].decode(errors='replace')
        qtbot.waitUntil(lambda: paths in receiver.requests)
        assert receiver.requests == [[], paths]
    finally:
        first.close()
    replacement = DesktopInstance(receiver, name)
    try:
        assert replacement.start([])
    finally:
        replacement.close()


def test_socket_waits_for_complete_message_and_rejects_bad_payload(qtbot, tmp_path):
    receiver = Receiver()
    instance = DesktopInstance(receiver, 'repdf-test-' + uuid.uuid4().hex)
    assert instance.start([])
    socket = QLocalSocket()
    try:
        socket.connectToServer(instance.name)
        assert socket.waitForConnected(1000)
        payload = json.dumps([str(tmp_path / 'test.pdf')]).encode()
        socket.write(payload[:5])
        socket.flush()
        qtbot.wait(30)
        assert receiver.requests == [[]]
        socket.write(payload[5:] + b'\n')
        socket.flush()
        qtbot.waitUntil(lambda: len(receiver.requests) == 2)
        assert receiver.requests[-1] == [str(tmp_path / 'test.pdf')]
    finally:
        socket.abort()
        instance.close()


def test_registry_plan_does_not_overwrite_default_or_other_apps():
    entries = registration_entries('"C:\\Program Files\\RePDF\\repdf.exe" "%1"', 'app.ico')
    assert any(path.endswith('OpenWithProgids') and name == 'RePDF.PDF' for path, name, _ in entries)
    assert any(path.endswith('shell\\open\\command') and value.endswith('"%1"') for path, _, value in entries)
    assert not any('UserChoice' in path for path, _, _ in entries)
    assert not any(path == r'Software\Classes\.pdf' for path, _, _ in entries)


def test_source_registration_uses_module_and_windowed_python():
    command, icon = launch_command()
    assert '-m repdf' in command
    assert command.endswith('"%1"')
    assert icon.endswith('",0')
