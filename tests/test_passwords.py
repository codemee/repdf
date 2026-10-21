import io
import json
from pathlib import Path

import pytest
from pypdf import PdfReader, PdfWriter
from shiboken6 import isValid

from repdf.core import (DocumentSelection, IncorrectPasswordError, PasswordRequiredError,
                        export_documents, inspect_pdf, split_documents)
from test_text_copy import text_pdf
from test_images import image_pdf


def encrypt(source, destination, password='open-secret', *, algorithm='AES-256', owner='owner-secret'):
    writer = PdfWriter(clone_from=source)
    writer.encrypt(password, owner_password=owner, algorithm=algorithm)
    writer.write(destination)


@pytest.mark.parametrize('algorithm,password', [('RC4-128', 'open-secret'), ('AES-128', 'open-secret'),
                                               ('AES-256', '測試密碼123')])
def test_password_validation_and_unencrypted_export(tmp_path, algorithm, password):
    source, locked = tmp_path / 'source.pdf', tmp_path / 'locked.pdf'
    text_pdf(source)
    encrypt(source, locked, password, algorithm=algorithm)
    original = locked.read_bytes()
    with pytest.raises(PasswordRequiredError):
        inspect_pdf(locked)
    with pytest.raises(IncorrectPasswordError):
        inspect_pdf(locked, 'wrong')
    assert inspect_pdf(locked, password).page_count == 1
    assert inspect_pdf(locked, 'owner-secret').page_count == 1
    selection = DocumentSelection(locked, (0,), password)
    assert password not in repr(selection)
    merged = tmp_path / 'export.pdf'
    export_documents([selection], merged)
    assert not PdfReader(merged).is_encrypted
    assert 'Copy this text' in PdfReader(merged).pages[0].extract_text()
    outputs = split_documents([selection], tmp_path / 'split.pdf')
    assert not PdfReader(outputs[0]).is_encrypted
    with pytest.raises(IncorrectPasswordError):
        export_documents([DocumentSelection(locked, (0,), 'wrong')], merged)
    assert locked.read_bytes() == original
    assert not PdfReader(merged).is_encrypted


def test_empty_open_password_and_distinct_file_passwords(tmp_path):
    source = tmp_path / 'source.pdf'
    text_pdf(source)
    documents = []
    for i, password in enumerate(('', 'one', 'two')):
        locked = tmp_path / f'locked-{i}.pdf'
        encrypt(source, locked, password)
        if not password:
            assert inspect_pdf(locked).page_count == 1
        documents.append(DocumentSelection(locked, (0,), password))
    output = tmp_path / 'merged.pdf'
    assert export_documents(documents, output) == 3
    assert not PdfReader(output).is_encrypted


def test_encrypted_background_render_text_ocr_and_image(tmp_path, monkeypatch):
    from repdf import render_worker
    source, locked = tmp_path / 'source.pdf', tmp_path / 'locked.pdf'
    text_pdf(source)
    encrypt(source, locked)
    bitmap, locked_bitmap = tmp_path / 'bitmap.pdf', tmp_path / 'locked-bitmap.pdf'
    image_pdf(bitmap, alpha=True)
    encrypt(bitmap, locked_bitmap)
    def region(page, *_args, profile='builtin'):
        assert profile == 'builtin'
        textpage = page.get_textpage()
        try:
            return {'text': textpage.get_text_range(), 'rects': []}
        finally:
            textpage.close()
    monkeypatch.setattr(render_worker, 'recognize_region', region)
    requests = [
        {'source': str(locked), 'output_dir': str(tmp_path), 'scale': .5},
        {'type': 'copy_text', 'source': str(locked), 'page': 0, 'start': [.12, .22], 'end': [.78, .27]},
        {'type': 'ocr_region', 'source': str(locked), 'page': 0, 'start': [.1, .2], 'end': [.8, .3]},
        {'type': 'extract_image', 'source': str(locked_bitmap), 'page': 0,
         'point': [90/240, 140/240], 'output_dir': str(tmp_path)},
    ]
    for i, request in enumerate(requests):
        request.update(generation=i+1, password='open-secret')
    output = io.StringIO()
    render_worker.serve(io.StringIO('\n'.join(json.dumps(r) for r in requests)), output)
    messages = [json.loads(line) for line in output.getvalue().splitlines()]
    assert not [m for m in messages if m['type'] == 'error']
    assert len([m for m in messages if m['type'] == 'done']) == 4
    assert [m for m in messages if m['type'] == 'page']
    assert all('Copy this text' in m['text'] for m in messages if m['type'] == 'text')
    image = next(m['image'] for m in messages if m['type'] == 'image')
    assert (image['width'], image['height']) == (4, 2)
    assert 'open-secret' not in output.getvalue()


def test_password_dialog_masks_and_can_reveal_text(qtbot):
    from PySide6.QtWidgets import QLineEdit
    from repdf.widgets import PdfPasswordDialog
    dialog = PdfPasswordDialog('locked.pdf')
    qtbot.addWidget(dialog)
    dialog.password_edit.setText('test')
    assert dialog.password_edit.echoMode() == QLineEdit.EchoMode.Password
    dialog.show_password.setChecked(True)
    assert dialog.password_edit.echoMode() == QLineEdit.EchoMode.Normal
    dialog.show_password.setChecked(False)
    assert dialog.password_edit.echoMode() == QLineEdit.EchoMode.Password


def test_batch_password_retry_cancel_export_and_reopen(qtbot, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QDialog, QFileDialog, QLabel, QMessageBox
    from repdf.app import DocumentView, MainWindow
    from repdf.widgets import PdfPasswordDialog
    source, locked, canceled = tmp_path / 'plain.pdf', tmp_path / 'locked.pdf', tmp_path / 'canceled.pdf'
    text_pdf(source)
    encrypt(source, locked)
    encrypt(source, canceled, 'different')
    monkeypatch.setattr(DocumentView, '_queue_all_renders', lambda self: None)
    errors, notices, dialogs = [], [], []
    monkeypatch.setattr(QMessageBox, 'critical', lambda *args: errors.append(args))
    monkeypatch.setattr(QMessageBox, 'information', lambda *args: notices.append(args[-1]))
    attempts = []
    def answer(dialog):
        labels = '\n'.join(label.text() for label in dialog.findChildren(QLabel))
        dialogs.append(dialog)
        if str(canceled) in labels:
            return QDialog.DialogCode.Rejected
        attempts.append('密碼不正確' in labels)
        dialog.password_edit.setText('wrong' if len(attempts) == 1 else 'open-secret')
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(PdfPasswordDialog, 'exec', answer)
    window = MainWindow()
    qtbot.addWidget(window)
    window.load_pdfs([locked, canceled, source])
    qtbot.waitUntil(lambda: not window._load_batches, timeout=5000)
    assert not errors
    assert attempts == [False, True]
    assert {doc.source_path for doc in window.documents.values()} == {locked, source}
    doc = next(doc for doc in window.documents.values() if doc.source_path == locked)
    assert doc.password == 'open-secret'
    assert all(dialog.password_edit.text() == '' for dialog in dialogs if isValid(dialog))
    window.tabs.setCurrentWidget(doc)
    doc.page_cards[0].checkbox.click()
    captions = []
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda _parent, title, *_args:
                        (captions.append(title) or '', ''))
    window.choose_output()
    assert '不加密' in captions[0]
    output = tmp_path / 'export.pdf'
    window._start_export(output)
    qtbot.waitUntil(lambda: not window._export_running, timeout=5000)
    assert not PdfReader(output).is_encrypted
    assert '不加密' in notices[-1]
    window.close_tab(window.tabs.indexOf(doc))
    assert doc.password is None
    window.load_pdf(locked)
    qtbot.waitUntil(lambda: not window._load_batches, timeout=5000)
    assert attempts == [False, True, False]
    assert 'open-secret' not in window.settings.fileName()
    settings_path = Path(window.settings.fileName())
    if settings_path.exists():
        assert 'open-secret' not in settings_path.read_text()


def test_unlock_then_preview_text_and_fullscreen(qtbot, monkeypatch, tmp_path):
    from PySide6.QtCore import QPoint
    from PySide6.QtWidgets import QApplication, QDialog
    from repdf.app import MainWindow
    from repdf.widgets import PdfPasswordDialog
    source, locked = tmp_path / 'source.pdf', tmp_path / 'locked.pdf'
    text_pdf(source)
    encrypt(source, locked)
    def unlock(dialog):
        dialog.password_edit.setText('open-secret')
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(PdfPasswordDialog, 'exec', unlock)
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    window.load_pdf(locked)
    qtbot.waitUntil(lambda: bool(window.documents) and window.current_document().ready, timeout=5000)
    doc = window.current_document()
    label = doc.page_cards[0].preview
    qtbot.waitUntil(lambda: not label.pixmap().isNull(), timeout=10000)
    window.copy_text_action.setChecked(True)
    QApplication.clipboard().setText('before')
    window._copy_text_selection(doc, 0, label, QPoint(round(label.width() * .12), round(label.height() * .22)),
                                QPoint(round(label.width() * .78), round(label.height() * .27)))
    qtbot.waitUntil(lambda: 'Copy this text' in QApplication.clipboard().text(), timeout=5000)
    window._show_fullscreen_preview()
    viewer = window._fullscreen_preview
    viewer.images.clear()
    viewer.request_render()
    qtbot.waitUntil(lambda: bool(viewer.images) and not viewer.image.isNull(), timeout=10000)
    viewer.close()


def test_closed_password_requests_do_not_reopen_or_stall_batch(qtbot, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QDialog
    from repdf.app import MainWindow
    from repdf.widgets import PdfPasswordDialog
    source, locked = tmp_path / 'source.pdf', tmp_path / 'locked.pdf'
    text_pdf(source)
    encrypt(source, locked)
    window = MainWindow()
    qtbot.addWidget(window)
    def close_while_prompting(_dialog):
        window.close_tab(window.tabs.currentIndex())
        return QDialog.DialogCode.Rejected
    monkeypatch.setattr(PdfPasswordDialog, 'exec', close_while_prompting)
    window.load_pdf(locked)
    qtbot.waitUntil(lambda: not window._load_batches, timeout=5000)
    assert not window.documents
    assert window._password_queue == []
    assert window._password_dialog is None
