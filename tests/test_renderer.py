import io
import sys
import pytest

from repdf.renderer import RenderService


@pytest.mark.parametrize('failure', [None, 'exit', 'import', 'timeout'])
def test_packaged_worker_bootstrap_reports_startup_outcome(qtbot, monkeypatch, failure):
    import repdf.renderer as renderer
    popen = renderer.subprocess.Popen
    if failure == 'timeout':
        script = 'import time; time.sleep(30)'
    elif failure == 'exit':
        script = 'raise SystemExit(7)'
    elif failure == 'import':
        script = '''import sys
sys.modules['repdf.render_worker'] = None
from repdf.backend_bootstrap import serve_socket
raise SystemExit(serve_socket(int(sys.argv[1]), sys.argv[2]))'''
    else:
        script = '''import sys
from repdf.backend_bootstrap import serve_socket
raise SystemExit(serve_socket(int(sys.argv[1]), sys.argv[2]))'''
    def launch(args, **kwargs):
        assert 'PYINSTALLER_RESET_ENVIRONMENT' not in kwargs['env']
        return popen([sys.executable, '-c', script, *args[2:]], **kwargs)
    monkeypatch.setenv('PYINSTALLER_RESET_ENVIRONMENT', '1')
    monkeypatch.setattr(renderer.subprocess, 'Popen', launch)
    monkeypatch.setattr(renderer, 'FROZEN_START_TIMEOUT', .2 if failure == 'timeout' else 10)
    if failure:
        expected = {'exit': 'code 7', 'import': 'ModuleNotFoundError', 'timeout': 'did not connect'}
        with pytest.raises(RuntimeError, match=expected[failure]):
            renderer._start_frozen_backend()
    else:
        process = renderer._start_frozen_backend()
        assert process.poll() is None
        RenderService(process).close()


class FakeBackend:
    def __init__(self):
        self.stdin = io.StringIO()
        self.stdout = io.StringIO()
        self.stderr = io.StringIO()

    def poll(self):
        return 0


def test_startup_failure_shows_qt_error_and_releases_instance(qapp, monkeypatch):
    import repdf.app as application
    import repdf.desktop_open as desktop
    closed, messages = [], []
    class Instance:
        def __init__(self, app): pass
        def start(self, paths): return True
        def close(self): closed.append(True)
    monkeypatch.setattr(desktop, 'DesktopApplication', lambda _args: qapp)
    monkeypatch.setattr(desktop, 'DesktopInstance', Instance)
    monkeypatch.setattr(desktop, 'file_arguments', lambda _args: [])
    monkeypatch.setattr(application, 'configure_application', lambda _app: None)
    def fail():
        raise RuntimeError('worker startup diagnostics')
    monkeypatch.setattr(application, 'start_render_backend', fail)
    monkeypatch.setattr(application.QMessageBox, 'exec', lambda box: messages.append(box.detailedText()))
    assert application.main() == 1
    assert messages == ['worker startup diagnostics']
    assert closed == [True]


def test_render_queue_coalesces_per_document_and_prioritizes_current(qtbot, tmp_path, monkeypatch):
    service = RenderService(FakeBackend())
    service._reader.join()
    sent = []
    monkeypatch.setattr(service, "_write", lambda payload: (sent.append(payload), True)[1])
    service.request(tmp_path / "a.pdf", 1, tmp_path, 1, document_id=1)
    service.request(tmp_path / "b.pdf", 1, tmp_path, 2, document_id=2)
    service.request(tmp_path / "a.pdf", 2, tmp_path, 3, document_id=1)
    service.request(tmp_path / "b.pdf", 2, tmp_path, 4, document_id=2)
    assert [payload["generation"] for payload in sent] == [1]
    assert [payload["generation"] for payload in service._pending.values()] == [4, 3]
    service.prioritize(1)
    assert list(service._pending) == [1, 2]
    service.cancel_pending(2)
    service._busy = False
    service._start_next()
    assert [payload["generation"] for payload in sent] == [1, 3]
    service.close()


def test_stopped_backend_reports_failure_without_stalling_queue(qtbot, tmp_path):
    service = RenderService(FakeBackend())
    service._reader.join()
    with qtbot.waitSignal(service.message) as signal:
        service.request(tmp_path / "a.pdf", 1, tmp_path, 1, document_id=1)
    assert signal.args[0]["type"] == "error"
    assert not service._busy
    assert not service._pending
    service.close()
