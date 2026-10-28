import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from pypdf import PdfWriter

from repdf.document_text import extract_document_text
from test_navigation import load_window
from test_search import search_pdf


def test_range_extraction_keeps_only_boundary_text(tmp_path):
    source = tmp_path / 'range.pdf'
    search_pdf(source, [[(40, 300, 'First page')], [], [(40, 300, 'Last page')]])
    messages = []
    extract_document_text({'source': str(source), 'pages': [0, 1, 2], 'generation': 1,
        'endpoints': {'start': [.25, .25], 'end': [.2, .25]}}, messages.append)
    assert messages[0]['text'].endswith('page')
    assert not messages[0]['text'].startswith('First')
    assert messages[1]['text'] == ''
    assert messages[2]['text'] == 'Las'
    assert messages[2]['text'] != 'Last page'


def test_cross_page_range_preview_and_reverse_copy(qtbot, tmp_path):
    source = tmp_path / 'drag.pdf'
    search_pdf(source, [[(40, 300, 'First page')], [(40, 300, 'Second page')]])
    window, doc = load_window(qtbot, source)
    window.copy_text_action.setChecked(True)
    copier = window.document_text
    clipboard = QApplication.clipboard()
    clipboard.setText('keep')
    copier.select_range(doc, (0, [0, 0]), (1, [1, 1]))
    qtbot.waitUntil(lambda: bool(doc.page_cards[1].preview._highlight_rects), timeout=10000)
    assert clipboard.text() == 'keep'
    copier.select_range(doc, (1, [1, 1]), (0, [0, 0]), copy=True)
    qtbot.waitUntil(lambda: copier.service is None, timeout=10000)
    assert clipboard.text() == 'First page\n\nSecond page'


def test_drag_past_page_edge_scrolls_and_copies_next_page(qtbot, tmp_path, monkeypatch):
    from PySide6.QtCore import QPoint
    source = tmp_path / 'edge.pdf'
    search_pdf(source, [[(40, 300, 'First page')], [(40, 300, 'Second page')]])
    window, doc = load_window(qtbot, source)
    window.copy_text_action.setChecked(True)
    label = doc.page_cards[0].preview
    qtbot.mousePress(label, Qt.MouseButton.LeftButton, pos=QPoint(1, 1))
    drag = window.document_text.drag
    drag.timer.stop()
    viewport = doc.scroll_area.viewport()
    before = doc.scroll_area.verticalScrollBar().value()
    monkeypatch.setattr('repdf.drag_selection.QCursor.pos', lambda:
                        viewport.mapToGlobal(QPoint(50, viewport.height() + label.height())))
    drag.advance()
    assert drag.crossed
    assert doc.scroll_area.verticalScrollBar().value() > before
    second = doc.pages.ensure_page(1).preview
    monkeypatch.setattr('repdf.drag_selection.QCursor.pos', lambda:
                        second.mapToGlobal(QPoint(second.width() - 1, second.height() - 1)))
    drag.advance()
    qtbot.mouseRelease(label, Qt.MouseButton.LeftButton, pos=QPoint(1, 1))
    qtbot.waitUntil(lambda: window.document_text.service is None, timeout=10000)
    assert QApplication.clipboard().text() == 'First page\n\nSecond page'


def test_fullscreen_drag_advances_page_group(qtbot, tmp_path, monkeypatch):
    from PySide6.QtCore import QPoint
    source = tmp_path / 'fullscreen-drag.pdf'
    search_pdf(source, [[(40, 300, 'First page')], [(40, 300, 'Second page')]])
    window, doc = load_window(qtbot, source)
    window.copy_text_action.setChecked(True)
    window.fullscreen_action.trigger()
    viewer = window._fullscreen_preview
    qtbot.mousePress(viewer.label, Qt.MouseButton.LeftButton, pos=QPoint(1, 1))
    drag = window.document_text.drag
    drag.timer.stop()
    monkeypatch.setattr('repdf.drag_selection.QCursor.pos', lambda:
                        viewer.mapToGlobal(QPoint(viewer.width() - 1, viewer.height() + 20)))
    drag.advance()
    assert viewer.page_index == 1
    qtbot.mouseRelease(viewer, Qt.MouseButton.LeftButton, pos=QPoint(viewer.width() - 1, viewer.height() - 1))
    qtbot.waitUntil(lambda: window.document_text.service is None, timeout=10000)
    assert QApplication.clipboard().text() == 'First page\n\nSecond page'
    viewer.close()


@pytest.mark.parametrize('encrypted', [False, True])
def test_extract_all_text_in_display_order_including_blank_pages(tmp_path, encrypted):
    source = tmp_path / 'all.pdf'
    search_pdf(source, [[(40, 300, 'First page')], [], [(40, 300, 'Last page')]])
    if encrypted:
        writer = PdfWriter(clone_from=source)
        writer.encrypt('secret', algorithm='AES-256')
        writer.write(source)
    messages = []
    extract_document_text({'source': str(source), 'pages': [2, 1, 0], 'generation': 7,
                           'password': 'secret' if encrypted else None}, messages.append)
    assert [message['text'] for message in messages] == ['Last page', '', 'First page']
    assert [message['page'] for message in messages] == [2, 1, 0]
    assert messages[0]['rects'] and not messages[1]['rects']
    assert all(0 <= a < c <= 1 and 0 <= b < d <= 1 for message in messages for a, b, c, d in message['rects'])


def test_ctrl_a_copies_whole_document_in_main_and_fullscreen(qtbot, tmp_path):
    source = tmp_path / 'all.pdf'
    search_pdf(source, [[(40, 300, 'First page')], [(40, 300, 'Second page')]])
    window, doc = load_window(qtbot, source)
    doc._move_page(1, 0)
    window.activateWindow()
    qtbot.waitUntil(window.isActiveWindow)
    window.copy_text_action.setChecked(True)
    clipboard = QApplication.clipboard()
    clipboard.setText('before')
    qtbot.keyClick(doc.scroll_area.viewport(), Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    qtbot.waitUntil(lambda: clipboard.text() != 'before', timeout=10000)
    assert clipboard.text() == 'Second page\n\nFirst page'
    assert doc.page_cards[0].preview._highlight_rects
    assert doc.page_cards[1].preview._highlight_rects
    window._show_fullscreen_preview()
    viewer = window._fullscreen_preview
    assert viewer.label._highlight_rects
    clipboard.setText('fullscreen')
    qtbot.keyClick(viewer.label, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    qtbot.waitUntil(lambda: clipboard.text() != 'fullscreen', timeout=10000)
    assert clipboard.text() == 'Second page\n\nFirst page'
    viewer.close()
    window.search_controller.open()
    query = window.search_controller.panel.query
    query.setText('search input')
    query.setCursorPosition(2)
    clipboard.setText('unchanged')
    qtbot.keyClick(query, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    assert query.selectedText() == 'search input'
    assert clipboard.text() == 'unchanged' and window.document_text.service is None


def test_cancelled_copy_and_image_only_pdf_keep_clipboard(qtbot, tmp_path):
    source = tmp_path / 'blank.pdf'
    search_pdf(source, [[]])
    window, doc = load_window(qtbot, source)
    window.copy_text_action.setChecked(True)
    clipboard = QApplication.clipboard()
    clipboard.setText('keep')
    window.document_text.start(doc)
    old_generation = window.document_text.generation
    window.document_text.cancel()
    window.document_text.receive({'type': 'done', 'generation': old_generation})
    assert clipboard.text() == 'keep'
    window.document_text.start(doc)
    qtbot.waitUntil(lambda: window.document_text.service is None, timeout=10000)
    assert clipboard.text() == 'keep'
    assert '沒有可複製' in window.statusBar().currentMessage()
