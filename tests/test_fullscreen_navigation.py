import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox, QToolTip

from test_navigation import load_window
from test_preview import make_pdf
from test_proofreading import files, choose


def enter(qtbot, field, text):
    field.setFocus()
    qtbot.waitUntil(field.hasFocus)
    qtbot.wait(1)
    field.selectAll()
    qtbot.keyClicks(field, text)
    qtbot.keyClick(field, Qt.Key.Key_Return)


@pytest.mark.parametrize('mode', ['single', 'spread', 'cover'])
def test_fullscreen_page_input_jump_edit_escape_and_invalid_values(qtbot, tmp_path, monkeypatch, mode):
    path = tmp_path / 'jump.pdf'
    make_pdf(path, [(300, 400)] * 6)
    window, doc = load_window(qtbot, path)
    window._show_fullscreen_preview(mode)
    viewer = window._fullscreen_preview
    qtbot.waitUntil(viewer.isActiveWindow)
    control = viewer.floating_tools.page_navigation
    field = control.input
    assert control.total.text() == '/ 6' and field.text() == '1'
    enter(qtbot, field, '4')
    assert 3 in viewer.visible_pages
    assert field.text() == str(viewer.page_index + 1)
    current = viewer.page_index
    field.setFocus()
    qtbot.waitUntil(field.hasFocus)
    qtbot.wait(1)
    field.selectAll()
    qtbot.keyClicks(field, '6')
    viewer.update_image()
    assert field.text() == '6'  # Render refresh must not overwrite unsubmitted input.
    qtbot.keyClick(field, Qt.Key.Key_Home)
    qtbot.keyClick(field, Qt.Key.Key_Right)
    assert viewer.page_index == current
    qtbot.keyClick(field, Qt.Key.Key_Escape)
    assert not viewer.closed and field.text() == str(current + 1)
    warnings = []
    monkeypatch.setattr(QToolTip, 'showText', lambda *args: warnings.append(args[1]))
    for value in ('0', '7', 'abc'):
        enter(qtbot, field, value)
        assert viewer.page_index == current
    assert len(warnings) == 3
    field.clearFocus()
    viewer.setFocus()
    qtbot.keyClick(viewer, Qt.Key.Key_Home)
    assert viewer.page_index == 0 and field.text() == '1'
    viewer.resize(320, 400)
    qtbot.waitUntil(lambda: viewer.rect().contains(viewer.floating_tools.geometry()))
    assert field.isVisible()
    viewer.close()


def test_comparison_page_input_tracks_focus_and_uses_atomic_sync(qtbot, tmp_path, monkeypatch):
    window, (first, second) = files(qtbot, tmp_path, counts=(6, 4))
    choose([first, second])
    window.fullscreen_action.trigger()
    viewer = window._fullscreen_preview
    qtbot.waitUntil(viewer.isActiveWindow)
    control = viewer.floating_tools.page_navigation
    field = control.input
    assert control.total.text() == '/ 4'
    qtbot.mouseClick(viewer.frames[first.document_id].title, Qt.MouseButton.LeftButton)
    assert control.total.text() == '/ 6'
    enter(qtbot, field, '5')
    assert viewer.views[first.document_id].page_index == 4
    assert viewer.views[second.document_id].page_index == 0
    qtbot.mouseClick(viewer.frames[second.document_id].title, Qt.MouseButton.LeftButton)
    assert control.total.text() == '/ 4' and field.text() == '1'
    window.sync_views_action.setChecked(True)
    qtbot.mouseClick(viewer.frames[first.document_id].title, Qt.MouseButton.LeftButton)
    messages = []
    monkeypatch.setattr(QMessageBox, 'exec', lambda self: messages.append(self.text()) or QMessageBox.StandardButton.Ok)
    enter(qtbot, field, '5')
    assert messages and all(view.page_index == 0 for view in viewer.views.values())
    assert field.text() == '1'
    enter(qtbot, field, '3')
    assert all(view.page_index == 2 for view in viewer.views.values())
    assert window.sync_views_action.isChecked()
    viewer.close()
