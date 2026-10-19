import pytest
from PySide6.QtCore import Qt

from repdf.app import MainWindow
from test_page_view import make_document, settled


def load_window(qtbot, path, count):
    make_document(path, count)
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    window.activateWindow()
    qtbot.waitUntil(window.isActiveWindow)
    window.load_pdf(path)
    qtbot.waitUntil(lambda: window.current_document().ready, timeout=10000)
    doc = window.current_document()
    qtbot.waitUntil(lambda: settled(doc), timeout=15000)
    return window, doc


def enter(qtbot, field, text):
    field.setFocus()
    qtbot.waitUntil(field.hasFocus)
    qtbot.wait(1)
    field.selectAll()
    qtbot.keyClicks(field, text)


def test_page_number_scroll_jump_fit_and_reorder(qtbot, tmp_path):
    window, doc = load_window(qtbot, tmp_path / '100-pages.pdf', 100)
    field = window.page_number_input
    assert field.text() == '1' and window.page_total.text() == '/ 100'
    doc.scroll_area.verticalScrollBar().setValue(doc.scroll_area.verticalScrollBar().maximum())
    qtbot.waitUntil(lambda: field.text() == '100', timeout=10000)
    enter(qtbot, field, '45')
    qtbot.keyClick(field, Qt.Key.Key_Return)
    qtbot.waitUntil(lambda: doc.focused_page == 44 and settled(doc), timeout=15000)
    assert field.text() == '45'
    assert not field.hasFocus()
    window.fit_action.trigger()
    enter(qtbot, field, '90')
    qtbot.keyClick(field, Qt.Key.Key_Return)
    qtbot.waitUntil(lambda: doc.fit_page_index == 89 and settled(doc), timeout=15000)
    assert doc.fit_mode and field.text() == '90'
    doc._move_page(99, 0)
    enter(qtbot, field, '100')
    qtbot.keyClick(field, Qt.Key.Key_Return)
    qtbot.waitUntil(lambda: doc.fit_page_index == 99 and settled(doc), timeout=15000)
    assert doc.page_order[0] == 99 and field.text() == '100'
    assert len(doc.page_cards.realized) < 20


def test_page_input_keeps_draft_and_editing_keys_do_not_navigate(qtbot, tmp_path):
    window, doc = load_window(qtbot, tmp_path / 'edit.pdf', 12)
    field = window.page_number_input
    enter(qtbot, field, '10')
    window._sync_controls()
    assert field.text() == '10'
    qtbot.keyClick(field, Qt.Key.Key_Home)
    assert field.cursorPosition() == 0
    qtbot.keyClick(field, Qt.Key.Key_End)
    assert field.cursorPosition() == 2
    assert doc.focused_page is None
    qtbot.keyClick(field, Qt.Key.Key_Escape)
    assert field.text() == '1'
    enter(qtbot, field, '12')
    doc.scroll_area.setFocus()
    qtbot.waitUntil(lambda: field.text() == '1')


@pytest.mark.parametrize('text', ['0', '6', '-1', '1.5', 'abc', ''])
def test_invalid_page_number_stays_put(qtbot, tmp_path, text):
    window, doc = load_window(qtbot, tmp_path / 'invalid.pdf', 5)
    field = window.page_number_input
    enter(qtbot, field, text or '1')
    if not text:
        field.clear()
    before = doc.scroll_area.verticalScrollBar().value()
    qtbot.keyClick(field, Qt.Key.Key_Return)
    assert doc.scroll_area.verticalScrollBar().value() == before
    assert doc.focused_page is None
    assert '1–5' in window.statusBar().currentMessage()
    assert field.hasFocus()
    qtbot.keyClick(field, Qt.Key.Key_Escape)
    assert field.text() == '1'


def test_page_indicator_tab_close_and_status_messages(qtbot, tmp_path):
    window, first = load_window(qtbot, tmp_path / 'first.pdf', 4)
    field = window.page_number_input
    enter(qtbot, field, '4')
    path = tmp_path / 'second.pdf'
    make_document(path, 2)
    window.load_pdf(path)
    qtbot.waitUntil(lambda: window.current_document().ready, timeout=10000)
    second = window.current_document()
    assert field.text() == '1' and window.page_total.text() == '/ 2'
    assert not window._page_edit_dirty
    window.statusBar().showMessage('OCR test message')
    assert window.page_controls.isVisible()
    assert field.text() == '1'
    window.tabs.setCurrentWidget(first)
    assert window.page_total.text() == '/ 4'
    window.close_tab(window.tabs.indexOf(first))
    window.close_tab(window.tabs.indexOf(second))
    assert not field.isEnabled()
    assert field.text() == '-' and window.page_total.text() == '/ 0'
