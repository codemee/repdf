import io
import json

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication
from pypdf import PdfWriter

from repdf.app import MainWindow
from repdf.render_worker import render_document

REAL_CONFIRM_CLOSE = MainWindow._confirm_close


def make_pdf(path, sizes):
    writer = PdfWriter()
    for width, height in sizes:
        writer.add_blank_page(width=width, height=height)
    writer.write(path)


def test_fullscreen_close_shortcut_advances_and_exits_after_last_file(qtbot, tmp_path):
    from test_navigation import load_window
    paths = [tmp_path / f'close-{i}.pdf' for i in range(3)]
    for path in paths:
        make_pdf(path, [(300, 400)])
    window, first = load_window(qtbot, paths[0])
    docs = [first]
    for path in paths[1:]:
        window.load_pdf(path)
        doc = window.current_document()
        wait_for_preview(qtbot, doc)
        docs.append(doc)
    window.activate_document(docs[1])
    window._show_fullscreen_preview('spread')
    window.navigation.open('annotations')
    for expected in (docs[2], docs[0], None):
        viewer = window._fullscreen_preview
        window.navigation.floating.activateWindow()
        window.navigation.panel.setFocus()
        qtbot.keyClick(window.navigation.panel, Qt.Key.Key_W, Qt.KeyboardModifier.ControlModifier)
        if expected is None:
            qtbot.waitUntil(lambda: window._fullscreen_preview is None)
            assert not window.documents
        else:
            qtbot.waitUntil(lambda: window._fullscreen_preview is not None
                           and window._fullscreen_preview.document is expected, timeout=15000)
            assert window._fullscreen_preview.mode == 'spread'


@pytest.mark.parametrize('choice', ['Cancel', 'Discard', 'Save'])
def test_fullscreen_close_shortcut_respects_unsaved_changes(qtbot, tmp_path, monkeypatch, choice):
    from PySide6.QtWidgets import QMessageBox
    from test_navigation import load_window
    source, other = tmp_path / 'modified.pdf', tmp_path / 'other.pdf'
    make_pdf(source, [(300, 400), (300, 400)])
    make_pdf(other, [(300, 400)])
    window, doc = load_window(qtbot, source)
    window.load_pdf(other)
    following = window.current_document()
    wait_for_preview(qtbot, following)
    window.activate_document(doc)
    doc._move_page(1, 0)
    window._show_fullscreen_preview()
    viewer = window._fullscreen_preview
    def answer(message):
        assert message.parentWidget() is viewer
        return getattr(QMessageBox.StandardButton, choice)
    monkeypatch.setattr(QMessageBox, 'exec', answer)
    monkeypatch.setattr(window, '_confirm_close', lambda doc, on_saved=None:
                        REAL_CONFIRM_CLOSE(window, doc, on_saved))
    qtbot.keyClick(viewer, Qt.Key.Key_W, Qt.KeyboardModifier.ControlModifier)
    if choice == 'Cancel':
        assert window._fullscreen_preview is viewer and doc.document_id in window.documents
    else:
        qtbot.waitUntil(lambda: len(window.documents) == 1 and window._fullscreen_preview is not None
                       and window._fullscreen_preview.document is following, timeout=30000)
    monkeypatch.setattr(window, '_confirm_close', lambda doc, on_saved=None: True)


def wait_for_preview(qtbot, doc):
    qtbot.waitUntil(lambda: doc.ready and doc._render_pending == 0
                   and not doc.render_timer.isActive() and not doc.fit_timer.isActive(), timeout=15000)


def test_fullscreen_remembers_mode_and_floats_annotations(qtbot, tmp_path):
    source = tmp_path / 'float.pdf'
    make_pdf(source, [(300, 400)] * 3)
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    window.load_pdf(source)
    doc = window.current_document()
    wait_for_preview(qtbot, doc)
    window._show_fullscreen_preview('cover')
    viewer = window._fullscreen_preview
    viewer.set_mode('spread')
    assert window.settings.value('ui/fullscreen_mode') == 'spread'
    before = viewer.size()
    window.annotation_action.trigger()
    nav = window.navigation
    assert nav.floating is not None and nav.floating.isVisible()
    assert nav.floating.windowTitle() == '註解'
    assert nav.floating.windowFlags() & Qt.WindowType.FramelessWindowHint
    assert nav.panel.header.isVisible()
    assert nav.panel.close_button.isVisible()
    assert nav.floating.size_grip.isVisible()
    old_position = nav.floating.pos()
    header = nav.panel.title
    local = header.rect().center()
    global_position = header.mapToGlobal(local)
    for event_type, position, button, buttons in (
        (QMouseEvent.Type.MouseButtonPress, global_position, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton),
        (QMouseEvent.Type.MouseMove, global_position + QPoint(30, 20), Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton),
        (QMouseEvent.Type.MouseButtonRelease, global_position + QPoint(30, 20), Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton),
    ):
        QApplication.sendEvent(header, QMouseEvent(event_type, local, position, button, buttons, Qt.KeyboardModifier.NoModifier))
    assert nav.floating.pos() == old_position + QPoint(30, 20)
    assert viewer.size() == before
    assert window._fullscreen_preview is viewer
    nav.panel.close_button.click()
    assert not nav.floating.isVisible()
    assert not window.annotation_action.isChecked()
    window.annotation_action.trigger()
    viewer.close()
    assert nav.floating is None
    assert nav.panel.parentWidget() is nav.workspace
    assert nav.panel.header.isVisible()
    assert nav.panel.close_button.isVisible()
    assert nav.panel.title.cursor().shape() == Qt.CursorShape.ArrowCursor
    nav.panel.close_button.click()
    assert not nav.opened
    window.close()
    restored = MainWindow()
    qtbot.addWidget(restored)
    assert restored.fullscreen_mode == 'spread'
    assert restored.spread_action.isChecked()


@pytest.mark.parametrize('count', [8, 80])
@pytest.mark.parametrize('fit', [False, True])
def test_exit_fullscreen_keeps_last_viewed_page(qtbot, tmp_path, count, fit):
    source = tmp_path / 'return-page.pdf'
    make_pdf(source, [(300, 400)] * count)
    window = MainWindow()
    qtbot.addWidget(window)
    window.resize(900, 700)
    window.show()
    window.load_pdf(source)
    doc = window.current_document()
    wait_for_preview(qtbot, doc)
    doc.fit_mode = fit
    window._show_fullscreen_preview('single')
    viewer = window._fullscreen_preview
    target = count - 2
    viewer.show_page(target)
    viewer.close()
    qtbot.waitUntil(lambda: window._fullscreen_preview is None
                   and doc.preview_page_index() == target, timeout=15000)
    from test_page_view import settled
    qtbot.waitUntil(lambda: settled(doc) and doc.preview_page_index() == target, timeout=15000)
    assert doc.preview_page_index() == target
    assert doc.fit_mode == fit
    if fit:
        assert doc.fit_page_index == target


def test_long_page_grid_preserves_full_preview_and_reflows(qtbot):
    from PySide6.QtCore import QPoint
    from PySide6.QtWidgets import QScrollArea
    from repdf.widgets import PageCard, PageGrid, PageGridLayout

    area = QScrollArea()
    qtbot.addWidget(area)
    area.setWidgetResizable(True)
    host = PageGrid()
    layout = PageGridLayout(host)
    layout.setContentsMargins(12, 12, 12, 12)
    layout.setSpacing(12)
    layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
    # Enough rows to exceed Qt's 524287px aggregate layout limit without
    # rendering hundreds of PDF pages or allocating large pixmaps.
    cards = [PageCard(i, 100) for i in range(70)]
    for i, card in enumerate(cards):
        card.set_preview_size(100, 8000)
        layout.addWidget(card, i, 0, Qt.AlignmentFlag.AlignHCenter)
    area.setWidget(host)
    area.resize(360, 500)
    area.show()
    qtbot.waitUntil(lambda: host.height() > 524287)
    layout.activate()
    for card in (cards[0], cards[35], cards[-1]):
        assert card.height() >= card.sizeHint().height()
        bottom = card.preview.mapTo(card, QPoint(0, card.preview.height() - 1))
        assert card.rect().contains(bottom)
    assert cards[-1].geometry().bottom() <= host.height()
    area.verticalScrollBar().setValue(area.verticalScrollBar().maximum())
    last_bottom = cards[-1].mapTo(area.viewport(), cards[-1].rect().bottomLeft())
    assert 0 <= last_bottom.y() < area.viewport().height()
    while layout.count():
        layout.takeAt(0)
    for i, card in enumerate(cards):
        layout.addWidget(card, i // 2, i % 2, Qt.AlignmentFlag.AlignHCenter)
    layout.activate()
    qtbot.waitUntil(lambda: host.height() < 524287)
    assert cards[0].height() >= cards[0].sizeHint().height()
    assert cards[1].y() == cards[0].y()
    # A subsequent smaller zoom must also release the tall scroll range.
    for card in cards:
        card.set_preview_size(100, 100)
    layout.invalidate()
    layout.activate()
    qtbot.waitUntil(lambda: host.height() < 20000)
    for card in cards:
        assert card.height() >= card.sizeHint().height()


@pytest.mark.parametrize("size", [(595, 842), (842, 595)])
def test_fit_page_and_resize_then_manual_zoom(qtbot, tmp_path, size):
    source = tmp_path / "fit.pdf"
    make_pdf(source, [size])
    window = MainWindow()
    qtbot.addWidget(window)
    window.resize(1000, 800)
    window.show()
    window.load_pdf(source)
    doc = window.current_document()
    wait_for_preview(qtbot, doc)
    window.fit_action.trigger()
    wait_for_preview(qtbot, doc)
    assert doc.fit_mode
    assert window.fit_action.isChecked()
    card = doc.page_cards[0]
    viewport = doc.scroll_area.viewport()
    assert card.width() <= viewport.width()
    assert card.height() <= viewport.height()
    if size[1] > size[0]:
        assert viewport.height() - card.height() <= 2
    assert abs(card.preview.width() / card.preview.height() - size[0] / size[1]) < .01
    old_zoom = doc.zoom
    window.resize(700, 500)
    qtbot.waitUntil(lambda: doc.zoom < old_zoom)
    wait_for_preview(qtbot, doc)
    assert card.width() <= viewport.width()
    assert card.height() <= viewport.height()
    window._set_manual_zoom(100)
    assert not doc.fit_mode
    assert doc.zoom == 100
    assert not window.fit_action.isChecked()


def test_fit_middle_page_fills_height_without_next_page_peeking(qtbot, tmp_path):
    source = tmp_path / "middle.pdf"
    make_pdf(source, [(595, 842)] * 3)
    window = MainWindow()
    qtbot.addWidget(window)
    window.resize(1100, 800)
    window.show()
    window.load_pdf(source)
    doc = window.current_document()
    wait_for_preview(qtbot, doc)
    doc.scroll_area.ensureWidgetVisible(doc.page_cards[1], 0, 0)
    doc.focused_page = 1
    window.fit_action.trigger()
    wait_for_preview(qtbot, doc)
    qtbot.wait(20)
    viewport = doc.scroll_area.viewport()
    card = doc.page_cards[1]
    scroll = doc.scroll_area.verticalScrollBar().value()
    assert doc.fit_page_index == 1
    assert 0 <= viewport.height() - card.height() <= 2
    assert abs(card.y() - scroll) <= 1
    assert doc.page_cards[2].y() - scroll >= viewport.height()


def test_fullscreen_aspect_navigation_escape_and_zoom_preserved(qtbot, tmp_path):
    source = tmp_path / "preview.pdf"
    make_pdf(source, [(595, 842), (842, 595)])
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    window.load_pdf(source)
    doc = window.current_document()
    wait_for_preview(qtbot, doc)
    window._set_manual_zoom(100)
    wait_for_preview(qtbot, doc)
    doc.page_order = [1, 0]
    doc._reflow_grid()
    doc.focused_page = 1
    window._show_fullscreen_preview()
    viewer = window._fullscreen_preview
    qtbot.waitUntil(lambda: viewer.isFullScreen() and not viewer.image.isNull())
    assert viewer.page_index == 1
    qtbot.waitUntil(lambda: not viewer.timer.isActive() and viewer.render_generation > 0)
    qtbot.waitUntil(lambda: abs(viewer.image.width() - viewer.label.width() * viewer.devicePixelRatioF()) <= 2,
                   timeout=15000)
    pixmap = viewer.label.pixmap()
    displayed = pixmap.size() / pixmap.devicePixelRatio()
    assert displayed.width() <= viewer.width()
    assert displayed.height() <= viewer.height()
    # PDF raster and Qt aspect fitting can each round by one pixel.
    assert min(viewer.width() - displayed.width(),
               viewer.height() - viewer.HEADER_HEIGHT - displayed.height()) <= 2
    qtbot.keyClick(viewer, Qt.Key.Key_Right)
    assert viewer.page_index == 0
    assert viewer.render_generation == -1
    qtbot.keyClick(viewer, Qt.Key.Key_Escape)
    assert window._fullscreen_preview is None
    assert doc.zoom == 100
    assert doc.selected_pages == set()


def test_worker_renders_only_requested_page_and_reports_pdf_size(tmp_path):
    source = tmp_path / "pages.pdf"
    make_pdf(source, [(300, 420), (600, 400)])
    output = io.StringIO()
    render_document(source, 1, tmp_path, 9, output, pages=[1])
    messages = [json.loads(line) for line in output.getvalue().splitlines()]
    assert len(messages) == 1
    assert messages[0]["page"] == 1
    assert messages[0]["width_points"] == 600
    assert messages[0]["height_points"] == 400
    assert not (tmp_path / "g9-p0.png").exists()


def test_navigation_keys_control_preview_when_slider_has_focus(qtbot, tmp_path):
    source = tmp_path / "keys.pdf"
    make_pdf(source, [(595, 842)] * 3)
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    window.load_pdf(source)
    doc = window.current_document()
    wait_for_preview(qtbot, doc)
    window._set_manual_zoom(100)
    wait_for_preview(qtbot, doc)
    window.zoom_slider.setFocus()
    vertical = doc.scroll_area.verticalScrollBar()
    vertical.setValue(0)
    qtbot.keyClick(window.zoom_slider, Qt.Key.Key_Down)
    assert vertical.value() > 0
    qtbot.keyClick(window.zoom_slider, Qt.Key.Key_Up)
    assert vertical.value() == 0
    qtbot.keyClick(window.zoom_slider, Qt.Key.Key_PageDown)
    assert vertical.value() > 0
    qtbot.keyClick(window.zoom_slider, Qt.Key.Key_PageUp)
    assert vertical.value() == 0
    for key in (Qt.Key.Key_Left, Qt.Key.Key_Right):
        qtbot.keyClick(window.zoom_slider, key)
    assert window.zoom_slider.value() == 100
    assert doc.zoom == 100
    window.fit_action.trigger()
    wait_for_preview(qtbot, doc)
    zoom = doc.zoom
    qtbot.keyClick(window.zoom_slider, Qt.Key.Key_PageDown)
    assert doc.fit_page_index == 1
    qtbot.keyClick(window.zoom_slider, Qt.Key.Key_Left)
    assert doc.fit_page_index == 0
    assert doc.zoom == zoom
    assert doc.fit_mode


@pytest.mark.parametrize('fit', [False, True])
def test_home_end_follow_reordered_pages_with_slider_focus(qtbot, tmp_path, fit):
    source = tmp_path / 'home-end.pdf'
    make_pdf(source, [(595, 842)] * 5)
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    window.load_pdf(source)
    doc = window.current_document()
    wait_for_preview(qtbot, doc)
    window._set_manual_zoom(100)
    wait_for_preview(qtbot, doc)
    doc.page_order = [3, 1, 4, 0, 2]
    doc._reflow_grid()
    if fit:
        window.fit_action.trigger()
        wait_for_preview(qtbot, doc)
    zoom = doc.zoom
    window.zoom_slider.setFocus()
    qtbot.keyClick(window.zoom_slider, Qt.Key.Key_End)
    if fit:
        wait_for_preview(qtbot, doc)
        qtbot.waitUntil(lambda: not doc._fit_navigation_pending)
        assert doc.fit_page_index == 2
    else:
        vertical = doc.scroll_area.verticalScrollBar()
        assert vertical.value() == min(doc.page_cards[2].y(), vertical.maximum())
    assert doc.preview_page_index() == 2
    assert doc.focused_page == 2
    qtbot.keyClick(window.zoom_slider, Qt.Key.Key_Home)
    if fit:
        wait_for_preview(qtbot, doc)
        qtbot.waitUntil(lambda: not doc._fit_navigation_pending)
        assert doc.fit_page_index == 3
        # Repeated/rapid jumps must not leave navigation anchored to an old page.
        qtbot.keyClick(window.zoom_slider, Qt.Key.Key_End)
        qtbot.keyClick(window.zoom_slider, Qt.Key.Key_PageUp)
        assert doc.fit_page_index == 0
        qtbot.keyClick(window.zoom_slider, Qt.Key.Key_Home)
        wait_for_preview(qtbot, doc)
        qtbot.waitUntil(lambda: not doc._fit_navigation_pending)
    else:
        assert doc.scroll_area.verticalScrollBar().value() == doc.scroll_area.verticalScrollBar().minimum()
    assert doc.preview_page_index() == 3
    assert doc.focused_page == 3
    assert doc.zoom == zoom


def test_fit_navigation_uses_visible_last_page_and_clamps_boundaries(qtbot, tmp_path):
    source = tmp_path / "boundary.pdf"
    make_pdf(source, [(595, 842)] * 3)
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    window.load_pdf(source)
    doc = window.current_document()
    wait_for_preview(qtbot, doc)
    assert doc.fit_mode
    qtbot.wait(20)
    wait_for_preview(qtbot, doc)
    assert doc.fit_page_index == 0
    vertical = doc.scroll_area.verticalScrollBar()
    # Scroll to the last page independently of the Fit reference, as with the mouse wheel.
    vertical.setValue(vertical.maximum())
    assert doc.preview_page_index() == 2
    bottom = vertical.value()
    for _ in range(3):
        qtbot.keyClick(window.zoom_slider, Qt.Key.Key_PageDown)
        qtbot.wait(10)
        assert doc.fit_page_index == 2
        assert vertical.value() == bottom
    qtbot.keyClick(window.zoom_slider, Qt.Key.Key_PageUp)
    qtbot.wait(20)
    assert doc.fit_page_index == 1
    assert vertical.value() < bottom
    qtbot.keyClick(window.zoom_slider, Qt.Key.Key_PageUp)
    qtbot.wait(20)
    assert doc.fit_page_index == 0
    top = vertical.value()
    qtbot.keyClick(window.zoom_slider, Qt.Key.Key_PageUp)
    assert doc.fit_page_index == 0
    assert vertical.value() == top
    # Rapid navigation must also stop at the last page, without an extra hidden step.
    for _ in range(5):
        qtbot.keyClick(window.zoom_slider, Qt.Key.Key_PageDown)
    assert doc.fit_page_index == 2
    qtbot.keyClick(window.zoom_slider, Qt.Key.Key_PageUp)
    assert doc.fit_page_index == 1


@pytest.mark.parametrize("sizes", [[(595, 842), (400, 842)], [(842, 595), (595, 842)]])
def test_preview_centers_pages_with_different_widths(qtbot, tmp_path, sizes):
    source = tmp_path / "center.pdf"
    make_pdf(source, sizes)
    window = MainWindow()
    qtbot.addWidget(window)
    window.resize(1100, 800)
    window.show()
    window.load_pdf(source)
    doc = window.current_document()
    wait_for_preview(qtbot, doc)
    qtbot.wait(20)
    viewport = doc.scroll_area.viewport()
    for card in doc.page_cards:
        center = card.mapTo(viewport, card.rect().center())
        assert abs(center.x() - viewport.rect().center().x()) <= 1
    window.fit_action.trigger()
    wait_for_preview(qtbot, doc)
    qtbot.wait(20)
    for card in doc.page_cards:
        center = card.mapTo(viewport, card.rect().center())
        assert abs(center.x() - viewport.rect().center().x()) <= 1


@pytest.mark.parametrize("mode,groups", [
    ("single", [[3], [1], [4], [0], [2]]),
    ("spread", [[3, 1], [4, 0], [2]]),
    ("cover", [[3], [1, 4], [0, 2]]),
])
def test_fullscreen_modes_follow_order_and_sync_selection(qtbot, tmp_path, monkeypatch, mode, groups):
    source = tmp_path / "spread.pdf"
    make_pdf(source, [(595, 842), (842, 595), (595, 842), (595, 842), (400, 700)])
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    window.load_pdf(source)
    doc = window.current_document()
    wait_for_preview(qtbot, doc)
    window._set_manual_zoom(100)
    wait_for_preview(qtbot, doc)
    doc.page_order = [3, 1, 4, 0, 2]
    doc.page_cards[1].checkbox.click()
    monkeypatch.setattr(doc, "preview_page_index", lambda: 3)
    action = {"single": window.fullscreen_action, "spread": window.spread_action, "cover": window.cover_action}[mode]
    action.trigger()
    viewer = window._fullscreen_preview
    assert viewer.groups == groups
    assert viewer.visible_pages == groups[0]
    assert not viewer.checkboxes[3].isChecked()
    viewer.checkboxes[3].click()
    assert doc.selected_pages == {1, 3}
    assert doc.page_cards[3].checkbox.isChecked()
    qtbot.waitUntil(lambda: viewer.render_generation > 0, timeout=5000)
    qtbot.waitUntil(lambda: all(not image.isNull() for image in viewer.images.values()))
    for index, label in viewer.labels.items():
        assert label.x() >= 0
        assert label.y() >= viewer.HEADER_HEIGHT
        assert label.geometry().right() < viewer.width()
        assert label.geometry().bottom() < viewer.height()
        assert viewer.checkboxes[index].geometry().bottom() < label.y()
    # Navigation works even while the page checkbox has keyboard focus.
    qtbot.keyClick(viewer.checkboxes[3], Qt.Key.Key_End)
    assert viewer.visible_pages == groups[-1]
    last_label = viewer.label
    qtbot.keyClick(viewer, Qt.Key.Key_End)
    assert viewer.label is last_label
    qtbot.keyClick(viewer.checkboxes[groups[-1][0]], Qt.Key.Key_Home)
    assert viewer.visible_pages == groups[0]
    qtbot.keyClick(viewer.checkboxes[3], Qt.Key.Key_PageDown)
    assert viewer.visible_pages == groups[1]
    assert viewer.render_generation == -1
    if 1 in viewer.visible_pages:
        assert viewer.checkboxes[1].isChecked()
        viewer.checkboxes[1].click()
        assert 1 not in doc.selected_pages
        assert not doc.page_cards[1].checkbox.isChecked()
    qtbot.keyClick(viewer, Qt.Key.Key_PageUp)
    assert viewer.visible_pages == groups[0]
    assert viewer.checkboxes[3].isChecked()
    viewer.show_page(2)
    assert viewer.visible_pages == groups[-1]
    qtbot.keyClick(viewer, Qt.Key.Key_Down)
    assert viewer.visible_pages == groups[-1]
    qtbot.keyClick(viewer, Qt.Key.Key_F11 if mode == "cover" else Qt.Key.Key_Escape)
    assert window._fullscreen_preview is None
    assert doc.zoom == 100
    assert window.output_selection()[0].pages == tuple(page for page in doc.page_order if page in doc.selected_pages)



def test_fullscreen_dropdown_switches_modes_in_place(qtbot, tmp_path):
    from test_navigation import load_window
    source = tmp_path / 'fullscreen-menu.pdf'
    make_pdf(source, [(300, 400)] * 5)
    window, doc = load_window(qtbot, source)
    window.resize(1600, 850)
    assert window.fullscreen_menu.actions() == [window.single_action, window.spread_action, window.cover_action]
    assert window.single_action not in window.toolbar.tool_actions()
    assert window.cover_action not in window.toolbar.tool_actions()
    window.cover_action.trigger()
    viewer = window._fullscreen_preview
    assert viewer.mode == 'cover' and window.fullscreen_mode == 'cover'
    assert window.fullscreen_menu.parentWidget() is viewer
    assert not window.annotation_floating.isVisible()
    viewer.show_page(3)
    for action, mode in ((window.spread_action, 'spread'), (window.single_action, 'single'), (window.cover_action, 'cover')):
        page = viewer.page_index
        action.trigger()
        assert window._fullscreen_preview is viewer
        assert viewer.mode == mode and window.fullscreen_mode == mode
        assert page in viewer.visible_pages
        assert action.isChecked()
        assert viewer.render_generation == -1
        assert viewer.floating_tools.isVisible()
    viewer.close()
    assert window.fullscreen_menu.parentWidget() is window
    window.fullscreen_action.trigger()
    assert window._fullscreen_preview.mode == 'cover'
    window._fullscreen_preview.close()
    window.resize(320, 240)
    qtbot.waitUntil(window.toolbar.overflow_button.isVisible)
    window.toolbar._populate_overflow()
    assert window.fullscreen_action in window.toolbar.overflow_menu.actions()
    assert window.fullscreen_menu.menuAction() in window.toolbar.overflow_menu.actions()


@pytest.mark.parametrize('main_expanded',[False,True])
def test_fullscreen_floating_annotation_tools_drag_menus_and_restore(qtbot,tmp_path,main_expanded):
    from PySide6.QtCore import QPoint,QTimer
    source = tmp_path / 'floating.pdf'
    make_pdf(source,[(300,400),(300,400)])
    window = MainWindow();qtbot.addWidget(window);window.show()
    window.annotation_tools_action.setChecked(main_expanded)
    window.load_pdf(source);doc=window.current_document();wait_for_preview(qtbot,doc)
    editor=window.annotation_editor
    menus=[editor.mark_menu,editor.callout_menu,editor.draw_menu,window.ocr_languages.menu,window.fullscreen_menu]
    parents=[menu.parentWidget() for menu in menus]
    window._show_fullscreen_preview();viewer=window._fullscreen_preview
    floating=viewer.floating_tools
    qtbot.waitUntil(floating.isVisible)
    assert all(menu.parentWidget() is viewer for menu in menus)
    if not floating.toggle.isChecked(): qtbot.mouseClick(floating.toggle,Qt.MouseButton.LeftButton)
    assert floating.toolbar.isVisible()
    qtbot.mouseClick(floating.buttons[editor.mark_action],Qt.MouseButton.LeftButton)
    assert editor.mark_action.isChecked()
    assert window.annotation_toolbar.widgetForAction(editor.mark_action).isChecked()
    observed=[]
    def use_menu():
        observed.append(editor.mark_menu.isVisible())
        editor.mark_menu.width.setValue(2)
        editor.mark_menu.hide()
    QTimer.singleShot(80,use_menu)
    qtbot.mouseClick(floating.arrows[0],Qt.MouseButton.LeftButton)
    assert observed == [True] and editor.mark_style['width'] == 2
    original=floating.pos()
    qtbot.mousePress(floating.grip,Qt.MouseButton.LeftButton,pos=QPoint(8,16))
    qtbot.mouseMove(floating.grip,QPoint(58,-34))
    qtbot.mouseRelease(floating.grip,Qt.MouseButton.LeftButton,pos=QPoint(8,16))
    assert floating.manual_position and floating.pos() != original
    moved=floating.pos();viewer.show_page(1)
    assert floating.pos() == moved and floating.isVisible()
    floating.move(9999,9999);floating.reposition()
    assert viewer.rect().contains(floating.geometry())
    qtbot.mouseClick(floating.toggle,Qt.MouseButton.LeftButton)
    assert not floating.toolbar.isVisible() and not editor.mark_action.isChecked()
    assert floating.mode_toolbar.isVisible()
    modes = []
    def choose_mode():
        modes.append(window.fullscreen_menu.isVisible())
        window.spread_action.trigger()
        window.fullscreen_menu.hide()
    QTimer.singleShot(80, choose_mode)
    qtbot.mouseClick(floating.arrows[-1], Qt.MouseButton.LeftButton)
    assert modes == [True] and viewer.mode == 'spread'
    assert window._fullscreen_preview is viewer
    assert not floating.toolbar.isVisible() and floating.mode_toolbar.isVisible()
    floating.toggle.setChecked(True)
    viewer.resize(320, 240)
    qtbot.wait(20)
    floating.toolbar._populate_overflow()
    for action in (editor.mark_action, editor.callout_action, editor.draw_action,
                   window.copy_text_action, window.region_ocr_action, window.extract_image_action):
        assert not floating.buttons[action].isVisible()
        assert action in floating.toolbar.overflow_menu.actions()
    assert viewer.rect().contains(floating.geometry())
    viewer.close()
    assert window._fullscreen_preview is None
    assert [menu.parentWidget() for menu in menus] == parents
    assert window.annotation_tools_action.isChecked() == main_expanded
    assert window.annotation_floating.isVisible() == main_expanded
