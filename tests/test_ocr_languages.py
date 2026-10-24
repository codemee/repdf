import hashlib
import io
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from PySide6.QtCore import QPointF
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QDialog, QToolButton

from repdf import ocr, ocr_models, render_worker
from repdf.app import DocumentView, MainWindow
from repdf.ocr_languages import OcrModelDialog
from repdf.ocr_models import model_directory as real_model_directory
from test_ocr import damaged_pdf


@pytest.fixture(autouse=True)
def isolated_models(tmp_path, monkeypatch):
    monkeypatch.setattr(ocr_models, 'model_directory', lambda: tmp_path / 'models')


@pytest.fixture
def model_server(monkeypatch):
    state = {'data': b'a downloaded recognition model', 'requests': 0, 'slow': False}
    gate = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            state['requests'] += 1
            self.send_response(state.get('status', 200))
            self.send_header('Content-Length', str(len(state['data'])))
            self.end_headers()
            try:
                self.wfile.write(state['data'][:1])
                self.wfile.flush()
                if state['slow']:
                    gate.wait(5)
                self.wfile.write(state['data'][1:])
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    info = dict(ocr_models.PROFILES['korean'])
    info.update(url=f'http://127.0.0.1:{server.server_port}/korean.onnx',
                sha256=hashlib.sha256(state['data']).hexdigest())
    monkeypatch.setitem(ocr_models.PROFILES, 'korean', info)
    yield state
    gate.set()
    server.shutdown()
    server.server_close()
    thread.join(2)


def window_for_test(qtbot, monkeypatch):
    monkeypatch.setattr(DocumentView, '_queue_all_renders', lambda self: None)
    window = MainWindow()
    qtbot.addWidget(window)
    return window


def test_language_menu_download_requires_confirmation_and_persists(qtbot, monkeypatch, model_server):
    window = window_for_test(qtbot, monkeypatch)
    control = window.ocr_languages
    button = window.ocr_language_button
    assert button.menu() is control.menu
    assert button is not window.toolbar.widgetForAction(window.region_ocr_action)
    assert button.parent() is window.toolbar.widgetForAction(window.region_ocr_action).parent()
    assert button.popupMode() == QToolButton.ToolButtonPopupMode.InstantPopup
    assert control.profile == 'builtin'
    control.actions['korean'].trigger()
    dialog = control.dialog
    assert dialog is not None and dialog.reply is None
    assert model_server['requests'] == 0
    assert control.profile == 'builtin' and control.actions['builtin'].isChecked()
    dialog.start()
    qtbot.waitUntil(lambda: control.dialog is None, timeout=5000)
    assert control.profile == 'korean'
    assert ocr_models.model_available('korean')
    assert window.settings.value('ocr/language') == 'korean'
    labels = [a.text() for a in control.menu.actions()]
    separators = [i for i, a in enumerate(control.menu.actions()) if a.isSeparator()]
    assert len(separators) == 2
    assert separators[0] < labels.index('韓文（已下載）') < separators[1]
    control.choose('builtin')
    control.choose('korean')
    assert control.dialog is None and model_server['requests'] == 1
    window.close()
    restored = window_for_test(qtbot, monkeypatch)
    assert restored.ocr_languages.profile == 'korean'


def test_cancel_never_changes_language_or_starts_download(qtbot, monkeypatch, model_server):
    window = window_for_test(qtbot, monkeypatch)
    window.ocr_languages.choose('korean')
    window.ocr_languages.dialog.reject()
    assert window.ocr_languages.profile == 'builtin'
    assert window.ocr_languages.dialog is None
    assert not ocr_models.model_path('korean').exists()
    assert model_server['requests'] == 0


def test_auto_and_download_sections_reflect_valid_models(qtbot, monkeypatch, model_server):
    window = window_for_test(qtbot, monkeypatch)
    control = window.ocr_languages
    labels = [a.text() for a in control.menu.actions()]
    separators = [i for i, a in enumerate(control.menu.actions()) if a.isSeparator()]
    assert labels.index('韓文') > separators[-1]
    assert '已下載' not in labels and '未下載' not in labels
    control.choose('auto')
    assert control.profile == 'auto' and control.dialog is None
    assert model_server['requests'] == 0
    path = ocr_models.model_path('korean')
    path.parent.mkdir(parents=True)
    path.write_bytes(model_server['data'])
    control.refresh()
    labels = [a.text() for a in control.menu.actions()]
    separators = [i for i, a in enumerate(control.menu.actions()) if a.isSeparator()]
    assert len(separators) == 2
    assert separators[0] < labels.index('韓文（已下載）') < separators[1]
    path.write_bytes(b'corrupt')
    control.refresh()
    labels = [a.text() for a in control.menu.actions()]
    separators = [i for i, a in enumerate(control.menu.actions()) if a.isSeparator()]
    assert labels.index('韓文') > separators[-1]
    assert control.actions['auto'].isChecked()


def test_corrupt_download_keeps_existing_file_and_can_retry(qtbot, model_server):
    path = ocr_models.model_path('korean')
    path.parent.mkdir(parents=True)
    path.write_bytes(b'existing model')
    original = model_server['data']
    model_server['data'] = b'bad server response'
    dialog = OcrModelDialog('korean')
    qtbot.addWidget(dialog)
    dialog.start()
    qtbot.waitUntil(lambda: dialog.reply is None, timeout=5000)
    assert dialog.result() == QDialog.DialogCode.Rejected
    assert '校驗' in dialog.status.text()
    assert path.read_bytes() == b'existing model'
    assert dialog.download_button.isEnabled()
    model_server['data'] = original
    dialog.start()
    qtbot.waitUntil(lambda: dialog.result() == QDialog.DialogCode.Accepted, timeout=5000)
    assert path.read_bytes() == original


@pytest.mark.parametrize('timeout', [False, True])
def test_cancel_or_timeout_removes_partial_download(qtbot, model_server, timeout):
    model_server['slow'] = True
    dialog = OcrModelDialog('korean')
    qtbot.addWidget(dialog)
    dialog.start()
    qtbot.waitUntil(lambda: dialog.received > 0, timeout=5000)
    if timeout:
        dialog.timer.timeout.emit()
        assert dialog.download_button.isEnabled() and '逾時' in dialog.status.text()
    else:
        dialog.reject()
    assert dialog.reply is None and dialog.file is None
    assert not ocr_models.model_path('korean').exists()
    assert list(ocr_models.model_directory().iterdir()) == []


def test_missing_profile_never_uses_rapidocr_downloader(monkeypatch):
    from rapidocr.utils.download_file import DownloadFile
    monkeypatch.setattr(DownloadFile, 'run', lambda *_args: pytest.fail('Unexpected automatic download'))
    ocr._engine.cache_clear()
    with pytest.raises(ocr.OcrModelMissing):
        ocr._engine('korean')


def test_network_error_allows_retry_without_switching(qtbot, monkeypatch, model_server):
    model_server['status'] = 503
    window = window_for_test(qtbot, monkeypatch)
    window.ocr_languages.choose('korean')
    dialog = window.ocr_languages.dialog
    dialog.start()
    qtbot.waitUntil(lambda: dialog.reply is None, timeout=5000)
    assert dialog.download_button.isEnabled() and window.ocr_languages.profile == 'builtin'
    assert not ocr_models.model_path('korean').exists()
    model_server['status'] = 200
    dialog.start()
    qtbot.waitUntil(lambda: window.ocr_languages.dialog is None, timeout=5000)
    assert window.ocr_languages.profile == 'korean'


def test_closing_application_aborts_language_download(qtbot, monkeypatch, model_server):
    model_server['slow'] = True
    window = window_for_test(qtbot, monkeypatch)
    window.ocr_languages.choose('korean')
    dialog = window.ocr_languages.dialog
    dialog.start()
    qtbot.waitUntil(lambda: dialog.received > 0, timeout=5000)
    window.close()
    assert window.ocr_languages.dialog is None
    assert dialog.reply is None
    assert not ocr_models.model_path('korean').exists()


@pytest.mark.parametrize('platform', ['win32', 'darwin', 'linux'])
def test_frozen_model_location_uses_user_data(monkeypatch, tmp_path, platform):
    monkeypatch.setattr(ocr_models.sys, 'platform', platform)
    monkeypatch.setattr(ocr_models.sys, 'frozen', True, raising=False)
    monkeypatch.setattr(ocr_models.sys, '_MEIPASS', str(tmp_path / 'bundle'), raising=False)
    monkeypatch.setattr(ocr_models.Path, 'home', lambda: tmp_path)
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'Local'))
    monkeypatch.setenv('XDG_DATA_HOME', str(tmp_path / 'share'))
    expected = {'win32': tmp_path / 'Local', 'darwin': tmp_path / 'Library/Application Support',
                'linux': tmp_path / 'share'}[platform]
    assert real_model_directory() == expected / 'RePDF/ocr/models'


def test_extra_model_uses_mobile_route_and_bundled_detection(monkeypatch, tmp_path):
    import rapidocr
    path = ocr_models.model_path('korean')
    path.parent.mkdir(parents=True)
    path.write_bytes(b'model')
    info = dict(ocr_models.PROFILES['korean'], sha256=hashlib.sha256(b'model').hexdigest())
    monkeypatch.setitem(ocr_models.PROFILES, 'korean', info)
    calls = []
    monkeypatch.setattr(rapidocr, 'RapidOCR', lambda **kwargs: calls.append(kwargs) or object())
    ocr._engine.cache_clear()
    try:
        ocr._engine('korean')
        params = calls[0]['params']
        assert params['Rec.model_path'] == str(path)
        assert params['Rec.ocr_version'].value == 'PP-OCRv5'
        assert params['Rec.model_type'].value == 'mobile'
        assert params['Rec.lang_type'] == 'korean'
        assert Path(params['Det.model_path']).name == ocr.DETECTION_MODEL
        assert Path(params['Det.model_path']).parent != path.parent
    finally:
        ocr._engine.cache_clear()


@pytest.mark.parametrize('region', [False, True])
def test_worker_passes_selected_language_and_reports_missing_model(tmp_path, monkeypatch, region):
    path = tmp_path / 'damaged.pdf'
    damaged_pdf(path)
    profiles = []
    def missing(*_args, **kwargs):
        profiles.append(kwargs['profile'])
        raise ocr.OcrModelMissing('Missing model')
    monkeypatch.setattr(render_worker, 'recognize_region' if region else 'recognize_selection', missing)
    request = {'type': 'ocr_region' if region else 'copy_text', 'source': str(path), 'page': 0,
               'start': [.12, .22], 'end': [.78, .27], 'generation': 7, 'allow_ocr': True,
               'ocr_profile': 'korean'}
    output = io.StringIO()
    render_worker.serve(io.StringIO(json.dumps(request) + '\n'), output)
    messages = [json.loads(line) for line in output.getvalue().splitlines()]
    result = next(m for m in messages if m['type'] in ('text', 'error'))
    assert profiles == ['korean']
    assert result['ocr_model_missing']
    assert result['ocr_retry'] == {k: request[k] for k in ('type', 'page', 'start', 'end', 'ocr_profile')}
    assert 'source' not in result['ocr_retry'] and 'password' not in result['ocr_retry']


@pytest.mark.parametrize('stale', [False, True])
def test_missing_model_download_retries_only_live_selection(qtbot, monkeypatch, tmp_path, model_server, stale):
    window = window_for_test(qtbot, monkeypatch)
    window.ocr_languages.profile = 'korean'
    doc = window._new_document(tmp_path / 'selection.pdf')
    doc.loaded(1)
    doc.page_sizes[0] = (300, 400)
    image = QImage(300, 400, QImage.Format.Format_RGB32)
    image.fill(0xffffffff)
    doc.page_cards[0].set_image(image)
    label = doc.page_cards[0].preview
    window._sync_controls()
    window.region_ocr_action.trigger()
    calls = []
    monkeypatch.setattr(window.render_service, 'request_text', lambda *a, **kw: calls.append((a, kw)))
    window._copy_text_selection(doc, 0, label, QPointF(30, 40), QPointF(200, 100))
    generation = window._next_generation
    window._handle_render_message({'type': 'error', 'generation': generation,
        'message': 'Missing model', 'ocr_model_missing': True,
        'ocr_retry': {'type': 'ocr_region', 'page': 0, 'start': [.1, .1], 'end': [2/3, .25],
                      'ocr_profile': 'korean'}})
    window._handle_render_message({'type': 'done', 'generation': generation})
    dialog = window.ocr_languages.dialog
    if stale:
        window.close_tab(window.tabs.indexOf(doc))
    dialog.start()
    qtbot.waitUntil(lambda: window.ocr_languages.dialog is None, timeout=5000)
    assert len(calls) == (1 if stale else 2)
    assert calls[-1][1]['ocr_profile'] == 'korean'


def test_overflow_keeps_language_menu_available(qtbot, monkeypatch):
    window = window_for_test(qtbot, monkeypatch)
    window.annotation_tools_action.setChecked(True)
    window.setMinimumWidth(100)
    window.resize(200, 240)
    window.show()
    qtbot.waitUntil(window.toolbar.overflow_button.isVisible)
    window.toolbar._populate_overflow()
    if window.ocr_language_button.isVisible():
        assert window.ocr_language_button.menu() is window.ocr_languages.menu
    else:
        assert window.ocr_languages.menu.menuAction() in window.toolbar.overflow_menu.actions()
