from pathlib import Path

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, DictionaryObject, NameObject, NumberObject, TextStringObject
from PySide6.QtWidgets import QFileDialog, QMessageBox

from repdf.core import save_document
from test_annotations import annotations_pdf
from test_navigation import load_window
from test_page_view import settled


@pytest.mark.parametrize('choice', [QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Discard, QMessageBox.StandardButton.Save])
@pytest.mark.parametrize('language', ['zh', 'en'])
def test_unsaved_message_action_order_and_choices(qtbot, monkeypatch, choice, language):
    from repdf.message_dialogs import unsaved_changes_message
    monkeypatch.setattr('repdf.strings.LANGUAGE', language)

    message = unsaved_changes_message(None, 'example.pdf')
    qtbot.addWidget(message)
    message.show()
    qtbot.waitExposed(message)
    buttons = [message.button(button) for button in (QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Discard, QMessageBox.StandardButton.Save)]
    assert buttons[0].x() < buttons[1].x() < buttons[2].x()
    assert message.text() == ('有尚未儲存的變更' if language == 'zh' else 'You have unsaved changes')
    assert [button.text() for button in buttons] == (['取消', '不儲存', '儲存'] if language == 'zh' else ['Cancel', 'Don’t Save', 'Save'])
    assert 'example.pdf' in message.informativeText()
    assert ('捨棄' if language == 'zh' else 'discard') in message.informativeText()
    assert message.defaultButton() is buttons[2]
    assert message.escapeButton() is buttons[0]
    from PySide6.QtCore import Qt
    qtbot.mouseClick(message.button(choice), Qt.MouseButton.LeftButton)
    assert message.result() == choice


@pytest.mark.parametrize('encrypted', [False, True])
def test_save_preserves_annotations_destinations_labels_and_encryption(tmp_path, encrypted):
    source, destination = tmp_path / 'source.pdf', tmp_path / 'saved.pdf'
    annotations_pdf(source)
    writer = PdfWriter(clone_from=source)
    writer.add_metadata({'/Title': 'Keep me'})
    writer._root_object[NameObject('/PageLabels')] = DictionaryObject({NameObject('/Nums'): ArrayObject([
        NumberObject(0), DictionaryObject({NameObject('/P'): TextStringObject('A-'), NameObject('/S'): NameObject('/D')})])})
    if encrypted:
        writer.encrypt('secret', algorithm='AES-256')
    writer.write(source)
    password = 'secret' if encrypted else None
    assert save_document(source, destination, [2, 0, 1], password=password) == 3
    reader = PdfReader(destination)
    assert reader.is_encrypted == encrypted
    if encrypted:
        assert reader.decrypt('secret')
    assert reader.metadata.title == 'Keep me'
    assert reader.page_labels == ['A-3', 'A-1', 'A-2']
    assert reader.get_destination_page_number(reader.outline[0]) == 1
    assert len(reader.pages[0]['/Annots']) == 1
    assert reader.pages[1]['/Annots'][0].get_object()['/Contents'] == '中文註解 <b>內容</b>'
    link = reader.pages[1]['/Annots'][-1].get_object()
    assert link['/Dest'][0] == reader.pages[0].indirect_reference
    save_document(destination, destination, [1, 2, 0], password=password)
    reread = PdfReader(destination, password=password)
    assert reread.page_labels == ['A-1', 'A-2', 'A-3']
    assert reread.get_destination_page_number(reread.outline[0]) == 0


def test_failed_save_is_atomic_and_requires_complete_order(tmp_path, monkeypatch):
    source = tmp_path / 'original.pdf'
    annotations_pdf(source)
    original = source.read_bytes()
    for order in ([0, 1], [0, 0, 2], [0, 1, 3]):
        with pytest.raises(ValueError):
            save_document(source, source, order)
    def fail(*args):
        raise PermissionError('cannot replace')
    monkeypatch.setattr('repdf.core.os.replace', fail)
    with pytest.raises(PermissionError):
        save_document(source, source, [2, 0, 1])
    assert source.read_bytes() == original
    assert not list(tmp_path.glob('.repdf-save-*'))


def test_default_fit_and_save_then_save_as_without_page_selection(qtbot, tmp_path, monkeypatch):
    source, destination = tmp_path / 'original.pdf', tmp_path / 'copy.pdf'
    annotations_pdf(source)
    window, doc = load_window(qtbot, source)
    assert doc.fit_mode and window.fit_action.isChecked()
    assert doc.page_cards[0].height() <= doc.scroll_area.viewport().height()
    assert not window.save_action.isEnabled() and window.save_as_action.isEnabled()
    doc._move_page(2, 0)
    assert doc.modified and window.save_action.isEnabled()
    assert window.tabs.tabText(window.tabs.indexOf(doc)).endswith(' *')
    assert not doc.selected_pages
    window.save_action.trigger()
    qtbot.waitUntil(lambda: window.saving.task is None, timeout=15000)
    current = window.current_document()
    assert current is not doc and current.source_path == source
    qtbot.waitUntil(lambda: settled(current), timeout=15000)
    assert not current.modified and not window.save_action.isEnabled()
    assert current.fit_mode and current.page_count == 3
    assert 'Marked text' in PdfReader(source).pages[0].extract_text()
    before = source.read_bytes()
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *a, **kw: (str(destination), ''))
    window.save_as_action.trigger()
    qtbot.waitUntil(lambda: window.saving.task is None, timeout=15000)
    assert window.current_document().source_path == destination
    assert source.read_bytes() == before
    current = window.current_document()
    qtbot.waitUntil(lambda: settled(current), timeout=15000)
    current._move_page(0, 2)
    window.save_action.trigger()
    qtbot.waitUntil(lambda: window.saving.task is None, timeout=15000)
    assert len(PdfReader(destination).pages) == 3
    assert not window.current_document().modified


def test_save_failure_preserves_order_and_restores_preview(qtbot, tmp_path, monkeypatch):
    source = tmp_path / 'original.pdf'
    annotations_pdf(source)
    window, doc = load_window(qtbot, source)
    original = source.read_bytes()
    doc._move_page(2, 0)
    errors = []
    monkeypatch.setattr(QMessageBox, 'critical', lambda *a: errors.append(a[-1]))
    def fail(*a, **kw):
        raise PermissionError('write failed')
    monkeypatch.setattr('repdf.workers.save_document', fail)
    window.save_action.trigger()
    qtbot.waitUntil(lambda: window.saving.task is None, timeout=15000)
    assert errors and source.read_bytes() == original
    assert window.current_document() is doc and doc.page_order == [2, 0, 1]
    assert window.toolbar.isEnabled() and window.save_action.isEnabled()
    qtbot.waitUntil(lambda: settled(doc), timeout=15000)
