import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication
from pypdf import PdfReader, PdfWriter

from repdf.app import MainWindow
from test_annotations import annotations_pdf
from test_navigation import load_window
from test_page_view import settled


def spaced_annotations(path, original):
    annotations_pdf(original)
    writer = PdfWriter()
    for page in PdfReader(original).pages:
        writer.add_page(page)
        writer.add_blank_page(300, 400)
    writer.write(path)


@pytest.mark.parametrize('fullscreen', [False, True])
def test_open_annotations_always_jumps_to_first_item(qtbot, tmp_path, fullscreen):
    path = tmp_path / 'first.pdf'
    annotations_pdf(path)
    window, doc = load_window(qtbot, path)
    nav = window.navigation
    if fullscreen:
        window._show_fullscreen_preview()
        viewer = window._fullscreen_preview
        viewer.show_page(2)
        current_page = lambda: viewer.page_index
    else:
        doc.jump_to_page(2)
        qtbot.waitUntil(lambda: doc.focused_page == 2 and settled(doc), timeout=15000)
        current_page = lambda: doc.focused_page
    nav.open('annotations')
    qtbot.waitUntil(lambda: len(nav.items) == 4 and current_page() == 0, timeout=15000)
    assert nav.panel.tree.currentItem() is nav.items[0]
    nav.next_annotation_page.trigger()
    qtbot.waitUntil(lambda: current_page() == 1, timeout=15000)
    nav.close()
    nav.open('annotations')
    qtbot.waitUntil(lambda: current_page() == 0, timeout=15000)
    assert nav.panel.tree.currentItem() is nav.items[0]


@pytest.mark.parametrize('fullscreen', [True])
def test_compact_bar_reviews_pages_and_items_and_restores_full_mode(qtbot, tmp_path, fullscreen):
    path = tmp_path / 'spaced.pdf'
    spaced_annotations(path, tmp_path / 'original.pdf')
    window, doc = load_window(qtbot, path)
    nav = window.navigation
    nav.open('annotations')
    qtbot.waitUntil(lambda: len(nav.items) == 4, timeout=10000)
    if fullscreen:
        window._show_fullscreen_preview()
    nav.compact_action.trigger()
    bar = nav.compact_bar
    assert nav.compact and nav.floating.isVisible()
    assert bar.isVisible() and not nav.panel.header.isVisible()
    assert not nav.panel.tree.isVisible() and not nav.panel.text_panel.isVisible()
    assert not nav.panel.status.isVisible()
    assert nav.floating.width() > nav.floating.height() * 5
    assert nav.floating.height() < 90
    assert nav.floating.maximumHeight() == nav.floating.minimumHeight()
    old_height = bar.text.height()
    nav.floating.resize(nav.floating.width(), 180)
    QApplication.processEvents()
    assert bar.text.height() == old_height
    assert nav.floating.height() < 90
    assert all(bar.layout().itemAt(i).alignment() & Qt.AlignmentFlag.AlignVCenter
               for i in range(9))
    assert bar.text.height() == bar.annotations.height()
    bar.text.set_contents('first\nsecond ' + 'long text ' * 100)
    assert bar.text.text().endswith('…')
    assert 'first<br>second' in bar.text.toolTip()
    assert '\n' not in bar.text.text()
    from repdf.annotation_text import platform_text
    import os
    assert platform_text('a\rb\nc\r\nd') == os.linesep.join(['a', 'b', 'c', 'd'])
    bar.sync()
    assert [bar.layout().itemAt(i).widget() for i in range(9)] == [
        bar.grip, bar.mode, bar.mode_separator, bar.previous, bar.page_label, bar.next,
        bar.annotations, bar.content_separator, bar.text]
    assert bar.page == 0 and not bar.previous.isEnabled()
    assert bar.annotations.count() == 1
    def wait_page(page):
        if fullscreen:
            qtbot.waitUntil(lambda: window._fullscreen_preview.page_index == page, timeout=15000)
        else:
            qtbot.waitUntil(lambda: doc.focused_page == page and settled(doc), timeout=15000)
    nav.floating.activateWindow()
    nav.panel.setFocus()
    qtbot.keyClick(nav.panel, Qt.Key.Key_PageDown, Qt.KeyboardModifier.AltModifier)
    wait_page(2)
    assert bar.page == 2 and bar.page_label.text() == '第 3 頁'
    assert bar.annotations.count() == 2 and bar.text.contents == 'Review this'
    assert bar.annotations.currentText() == 'Review this'
    bar.annotations.setCurrentIndex(1)
    bar.annotations.activated.emit(1)
    assert nav.panel.tree.currentItem() is nav.items[2]
    assert not bar.text.contents
    bar.next.click()
    wait_page(4)
    assert bar.page == 4 and not bar.next.isEnabled()
    bar.previous.click()
    wait_page(2)
    assert bar.page == 2
    old_position = nav.floating.pos()
    label = bar.grip
    local = label.rect().center()
    global_position = label.mapToGlobal(local)
    for kind, position, button, buttons in (
        (QMouseEvent.Type.MouseButtonPress, global_position, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton),
        (QMouseEvent.Type.MouseMove, global_position + QPoint(30, 15), Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton),
        (QMouseEvent.Type.MouseButtonRelease, global_position + QPoint(30, 15), Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton),
    ):
        QApplication.sendEvent(label, QMouseEvent(kind, local, position, button, buttons, Qt.KeyboardModifier.NoModifier))
    assert nav.floating.pos() == old_position + QPoint(30, 15)
    window.search_controller.open()
    assert bar.isVisible() and window.search_controller.panel.isVisible()
    selected = nav.panel.tree.currentItem()
    bar.mode.click()
    assert not nav.compact and nav.panel.tree.isVisible()
    assert nav.panel.tree.currentItem() is selected
    qtbot.keyClick(nav.panel, Qt.Key.Key_PageUp, Qt.KeyboardModifier.AltModifier)
    wait_page(0)
    if fullscreen:
        assert nav.floating.isVisible() and nav.floating.height() > 100
        window._fullscreen_preview.close()
    else:
        assert nav.floating is None and nav.panel.parentWidget() is nav.workspace


def test_compact_mode_survives_fullscreen_and_handles_empty_document(qtbot, tmp_path):
    path, empty = tmp_path / 'comments.pdf', tmp_path / 'empty.pdf'
    annotations_pdf(path)
    writer = PdfWriter()
    writer.add_blank_page(300, 400)
    writer.write(empty)
    window, doc = load_window(qtbot, path)
    nav = window.navigation
    nav.open('annotations')
    qtbot.waitUntil(lambda: len(nav.items) == 4, timeout=10000)
    nav.set_compact(True)
    assert nav.floating is None and nav.panel.tree.isVisible()
    assert not nav.mode_button.isVisible()
    window._show_fullscreen_preview()
    assert nav.floating.parentWidget() is window._fullscreen_preview
    assert nav.compact_bar.isVisible()
    window._fullscreen_preview.close()
    assert nav.floating is None and not nav.compact_bar.isVisible()
    assert nav.panel.tree.isVisible() and nav.compact
    window.activateWindow()
    nav.panel.tree.setFocus()
    qtbot.keyClick(nav.panel.tree, Qt.Key.Key_PageDown, Qt.KeyboardModifier.AltModifier)
    qtbot.waitUntil(lambda: doc.focused_page == 1, timeout=15000)
    window.load_pdf(empty)
    qtbot.waitUntil(lambda: window.current_document().annotations == [], timeout=10000)
    window._show_fullscreen_preview()
    assert nav.compact_bar.annotations.count() == 0
    assert not nav.compact_bar.previous.isEnabled() and not nav.compact_bar.next.isEnabled()
    assert not nav.compact_bar.text.contents
    assert nav.compact_bar.page_label.text() == '沒有註解頁面'
    nav.close()
    nav.open('annotations')
    assert nav.compact_bar.isVisible()
    restored = MainWindow()
    qtbot.addWidget(restored)
    assert restored.navigation.compact
    window.language_controller.set_mode('en')
    assert nav.compact_bar.page_label.text() == 'No annotated pages'
