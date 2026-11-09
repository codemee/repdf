import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QHelpEvent, QWheelEvent
from PySide6.QtWidgets import QApplication, QMessageBox, QToolTip
from pypdf import PdfWriter

from test_navigation import load_window
from test_page_view import settled
from test_preview import make_pdf, wait_for_preview


def files(qtbot, tmp_path, counts=(4, 4), trim=False):
    paths = [tmp_path / f'file-{i}.pdf' for i in range(len(counts))]
    for path, count in zip(paths, counts):
        writer = PdfWriter()
        for _ in range(count):
            page = writer.add_blank_page(300, 400)
            if trim:
                page.trimbox.lower_left = (30, 30)
                page.trimbox.upper_right = (270, 370)
        writer.write(path)
    window, first = load_window(qtbot, paths[0])
    docs = [first]
    for path in paths[1:]:
        window.load_pdf(path)
        doc = window.current_document()
        wait_for_preview(qtbot, doc)
        docs.append(doc)
    return window, docs


def choose(docs):
    for doc in docs:
        doc.include_checkbox.setChecked(True)


@pytest.mark.parametrize('split', [False, True])
def test_two_checked_tabs_always_compare_side_by_side(qtbot, tmp_path, split):
    window, (first, second) = files(qtbot, tmp_path)
    if split:
        window.workspace.transfer(second.document_id, window.workspace.active, 'bottom')
    choose([first, second])
    assert window.sync_views_action.isEnabled() and not window.sync_views_action.isChecked()
    assert window._fullscreen_preview is None
    second.jump_to_page(2)
    qtbot.waitUntil(lambda: settled(second), timeout=15000)
    assert first.focused_page != 2  # Normal panes remain independent.
    window.fullscreen_mode = 'cover'
    window.fullscreen_action.trigger()
    viewer = window._fullscreen_preview
    assert len(viewer.views) == 2 and viewer.splitter.orientation() == Qt.Orientation.Horizontal
    assert all(view.mode == 'cover' for view in viewer.views.values())
    qtbot.waitUntil(lambda: all(not view.image.isNull() for view in viewer.views.values()), timeout=15000)
    assert viewer.layout().contentsMargins().left() == 20
    assert all(frame.mapTo(viewer, QPoint()).x() >= 20 for frame in viewer.frames.values())
    frame = viewer.frames[first.document_id]
    qtbot.mouseClick(frame.title, Qt.MouseButton.LeftButton)
    assert viewer.document is first and frame.property('activePane') is True
    assert viewer.frames[second.document_id].property('activePane') is False
    viewer.close()
    assert window.fullscreen_mode == 'cover'
    assert window._fullscreen_preview is None and not window.sync_views_action.isChecked()
    assert len(window.workspace.panes) == (2 if split else 1)


@pytest.mark.parametrize('selected_count', [0, 1, 3])
def test_fullscreen_eligibility_by_checked_tab_count(qtbot, tmp_path, selected_count):
    window, docs = files(qtbot, tmp_path, (2, 3, 4))
    choose(docs[:selected_count])
    assert not window.sync_views_action.isEnabled()
    if selected_count > 2:
        assert not window.fullscreen_action.isEnabled()
        assert not window.fullscreen_menu_button.isEnabled()
        assert '兩份文件' in window.fullscreen_action.toolTip()
        window.resize(1400, 800)
        QApplication.processEvents()
        button = window.toolbar.widgetForAction(window.fullscreen_action)
        position = button.mapToGlobal(button.rect().center())
        help_event = QHelpEvent(QEvent.Type.ToolTip, window.toolbar.mapFromGlobal(position), position)
        QApplication.sendEvent(window.toolbar, help_event)
        assert '兩份文件' in QToolTip.text()
        QToolTip.hideText()
        window._show_fullscreen_preview()
        assert window._fullscreen_preview is None
    else:
        assert window.fullscreen_action.isEnabled()
        window._show_fullscreen_preview()
        assert not hasattr(window._fullscreen_preview, 'views')
        assert window._fullscreen_preview.document is (docs[0] if selected_count else docs[-1])


@pytest.mark.parametrize('start_with_sync', [False, True])
def test_unequal_page_counts_sync_only_pages_and_crop(qtbot, tmp_path, start_with_sync):
    window, (first, second) = files(qtbot, tmp_path, (3, 5), trim=True)
    choose([first, second])
    assert window.sync_views_action.isEnabled()
    if start_with_sync:
        window.sync_views_action.trigger()
    else:
        window._show_fullscreen_preview()
        window.sync_views_action.trigger()
    viewer = window._fullscreen_preview
    assert viewer is not None and window.sync_views_action.isChecked()
    viewer.show_page(1)
    assert all(v.page_index == 1 for v in viewer.views.values())
    frame = viewer.frames[first.document_id]
    qtbot.mouseClick(frame.title, Qt.MouseButton.LeftButton)
    qtbot.keyClick(viewer, Qt.Key.Key_PageDown)
    assert all(v.page_index == 2 for v in viewer.views.values())
    window._toggle_trim_view(True)
    assert first.trim_view and second.trim_view
    window._toggle_trim_view(False)
    assert not first.trim_view and not second.trim_view
    window._zoom_changed(120)
    assert first.zoom == 120 and second.zoom != 120
    first.selected_pages.add(0)
    assert not second.selected_pages
    window.sync_views_action.trigger()
    viewer.show_page(0)
    assert viewer.views[first.document_id].page_index == 0
    assert viewer.views[second.document_id].page_index == 2
    window._toggle_trim_view(True)
    assert first.trim_view and not second.trim_view


def test_out_of_range_is_atomic_for_keys_wheel_annotation_and_page_field(qtbot, tmp_path, monkeypatch):
    window, (first, second) = files(qtbot, tmp_path, (2, 4))
    choose([first, second])
    window.sync_views_action.trigger()
    viewer = window._fullscreen_preview
    viewer.show_page(1)
    messages = []
    def notify(message):
        assert message.testOption(QMessageBox.Option.DontUseNativeDialog)
        messages.append(message.text() + message.informativeText())
        return QMessageBox.StandardButton.Ok
    monkeypatch.setattr(QMessageBox, 'exec', notify)
    def unchanged():
        assert [v.page_index for v in viewer.views.values()] == [1, 1]
    qtbot.keyClick(viewer, Qt.Key.Key_PageDown)
    unchanged()
    assert len(messages) == 1 and '2' in messages[-1]
    event = QWheelEvent(QPointF(4, 4), QPointF(4, 4), QPoint(), QPoint(0, -120),
                        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                        Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(viewer.views[second.document_id], event)
    unchanged()
    assert len(messages) == 2
    window.navigation.activate(second, {'page': 3})
    unchanged()
    assert len(messages) == 3
    window.page_number_input.setText('4')
    window._jump_from_page_field()
    unchanged()
    assert len(messages) == 4
    viewer.show_page(0)
    assert all(v.page_index == 0 for v in viewer.views.values())


def test_normal_split_is_not_comparison_without_checked_tabs(qtbot, tmp_path):
    window, (first, second) = files(qtbot, tmp_path)
    window.workspace.transfer(second.document_id, window.workspace.active, 'top')
    assert not window.sync_views_action.isEnabled()
    window._show_fullscreen_preview('cover')
    assert not hasattr(window._fullscreen_preview, 'views')
    assert window._fullscreen_preview.document is second
    assert window._fullscreen_preview.mode == 'cover'


def test_comparison_mode_menu_preserves_independent_pages_and_synchronizes(qtbot, tmp_path):
    window, (first, second) = files(qtbot, tmp_path, (5, 7))
    choose([first, second])
    assert window.fullscreen_menu_button.isEnabled()
    window._show_fullscreen_preview('single')
    viewer = window._fullscreen_preview
    qtbot.mouseClick(viewer.frames[first.document_id].title, Qt.MouseButton.LeftButton)
    viewer.show_page(1)
    qtbot.mouseClick(viewer.frames[second.document_id].title, Qt.MouseButton.LeftButton)
    viewer.show_page(3)
    assert viewer.floating_tools.arrows[-1].isEnabled()
    window.spread_action.trigger()
    assert viewer.mode == 'spread' and all(v.mode == 'spread' for v in viewer.views.values())
    assert viewer.views[first.document_id].visible_pages == [0, 1]
    assert viewer.views[second.document_id].visible_pages == [2, 3]
    assert window.settings.value('ui/fullscreen_mode') == 'spread'
    window.cover_action.trigger()
    assert viewer.mode == 'cover' and window.cover_action.isChecked()
    assert viewer.views[first.document_id].visible_pages == [0]
    assert viewer.views[second.document_id].visible_pages == [1, 2]
    window.sync_views_action.trigger()
    assert all(v.page_index == 1 for v in viewer.views.values())
    window.single_action.trigger()
    assert viewer.mode == 'single' and all(v.visible_pages == [1] for v in viewer.views.values())


@pytest.mark.parametrize('mode, page', [('single', 2), ('spread', 2), ('cover', 1)])
def test_sync_range_checks_in_each_comparison_mode(qtbot, tmp_path, monkeypatch, mode, page):
    window, docs = files(qtbot, tmp_path, (3, 5))
    choose(docs)
    window._show_fullscreen_preview(mode)
    viewer = window._fullscreen_preview
    window.sync_views_action.trigger()
    viewer.show_page(page)
    before = [v.page_index for v in viewer.views.values()]
    messages = []
    monkeypatch.setattr(QMessageBox, 'exec', lambda message: messages.append(message.text()))
    qtbot.keyClick(viewer, Qt.Key.Key_PageDown)
    assert len(messages) == 1
    assert [v.page_index for v in viewer.views.values()] == before
    assert all(v.mode == mode for v in viewer.views.values())


def test_blocked_mode_change_restores_menu_selection(qtbot, tmp_path, monkeypatch):
    window, docs = files(qtbot, tmp_path, (2, 7))
    choose(docs)
    window._show_fullscreen_preview('single')
    viewer = window._fullscreen_preview
    viewer.show_page(4)
    messages = []
    monkeypatch.setattr(QMessageBox, 'exec', lambda message: messages.append(message.text()))
    window.sync_views_action.trigger()
    before = [v.page_index for v in viewer.views.values()]
    window.cover_action.trigger()
    assert len(messages) == 2
    assert window.single_action.isChecked() and not window.cover_action.isChecked()
    assert window.fullscreen_mode == viewer.mode == 'single'
    assert [v.page_index for v in viewer.views.values()] == before
