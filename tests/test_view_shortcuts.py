import pytest
from PySide6.QtGui import QKeySequence

from test_proofreading import files, choose


@pytest.mark.parametrize('mode', ['normal', 'fullscreen', 'comparison'])
def test_trim_and_annotation_shortcuts_in_each_view(qtbot, tmp_path, mode):
    window, docs = files(qtbot, tmp_path, trim=True)
    if mode == 'comparison':
        choose(docs)
    if mode != 'normal':
        window.fullscreen_action.trigger()
    target = window._fullscreen_preview or window
    target.activateWindow()
    qtbot.waitUntil(target.isActiveWindow)
    assert window.trim_view_action.shortcut() == QKeySequence('Alt+C')
    assert window.annotation_action.shortcut() == QKeySequence('Alt+D')
    for action in (window.trim_view_action, window.annotation_action):
        assert action.shortcut().toString(QKeySequence.SequenceFormat.NativeText) in action.toolTip()
    doc = window.current_document()
    before = doc.trim_view
    qtbot.keySequence(target, QKeySequence('Alt+C'))
    assert doc.trim_view != before
    qtbot.keySequence(target, QKeySequence('Alt+C'))
    assert doc.trim_view == before
    qtbot.keySequence(target, QKeySequence('Alt+D'))
    assert window.annotation_action.isChecked()
    panel = window.navigation.floating or target
    panel.activateWindow()
    qtbot.waitUntil(panel.isActiveWindow)
    qtbot.keySequence(panel, QKeySequence('Alt+D'))
    assert not window.annotation_action.isChecked()
    if mode != 'normal':
        assert window._fullscreen_preview is target and not target.closed
        target.close()
