import pytest
from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QApplication, QLabel, QMessageBox, QTextEdit

from repdf.message_dialogs import install_message_style, proofreading_range_message
from repdf.theme import ThemeController


@pytest.mark.parametrize('theme', ['light', 'dark'])
@pytest.mark.parametrize('method,button', [('information', 'Ok'), ('warning', 'Ok'),
                                          ('critical', 'Ok'), ('question', 'Yes')])
def test_static_message_helpers_share_style_and_keep_answers(qapp, qtbot, theme, method, button):
    ThemeController(qapp, theme)
    install_message_style(qapp)
    selected = getattr(QMessageBox.StandardButton, button)
    seen = []

    def respond():
        message = QApplication.activeModalWidget()
        try:
            assert isinstance(message, QMessageBox)
            assert message.property('modernMessageReady')
            assert message.testOption(QMessageBox.Option.DontUseNativeDialog)
            from repdf.strings import tr
            fallback = {'information': '資訊', 'warning': '警告', 'critical': '錯誤', 'question': '確認'}
            assert message.text() in ('Message heading', message.windowTitle(), tr(fallback[method]))
            assert message.informativeText() == 'Full explanation\nSecond line'
            assert message.findChild(QLabel, 'qt_msgboxex_icon_label').size().width() == 24
            assert message.button(selected).height() == 34
            assert message.icon() == QMessageBox.Icon.NoIcon
            if method == 'question':
                assert message.defaultButton() is message.button(QMessageBox.StandardButton.No)
            seen.append(message.property('modernMessageIcon'))
        finally:
            # Assertions in a timer must not leave a modal loop blocking CI.
            if isinstance(message, QMessageBox):
                message.button(selected).click()

    QTimer.singleShot(0, respond)
    if method == 'question':
        answer = QMessageBox.question(None, 'Message heading', 'Full explanation\nSecond line',
                                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                      QMessageBox.StandardButton.No)
    else:
        answer = getattr(QMessageBox, method)(None, 'Message heading', 'Full explanation\nSecond line')
    assert answer == selected and len(seen) == 1


def test_range_message_proportions_and_keyboard_dismissal(qapp, qtbot):
    ThemeController(qapp, 'light')
    message = proofreading_range_message(None, 29, 'F6791_CH03(28).pdf', 28)
    qtbot.addWidget(message)
    message.show()
    qtbot.waitExposed(message)
    title = message.findChild(QLabel, 'qt_msgbox_label')
    detail = message.findChild(QLabel, 'qt_msgbox_informativelabel')
    assert title.font().pointSize() == 12 and detail.font().pointSize() == 10
    assert '29' in message.text() and '28' in message.informativeText()
    assert 'F6791_CH03(28).pdf' in message.informativeText()
    assert message.iconPixmap().deviceIndependentSize().width() == 24
    assert message.defaultButton() is message.button(QMessageBox.StandardButton.Ok)
    qtbot.keyClick(message, Qt.Key.Key_Escape)
    assert message.result() == QMessageBox.StandardButton.Ok


def test_diagnostics_and_custom_button_roles_are_preserved(qapp, qtbot):
    install_message_style(qapp)
    message = QMessageBox()
    qtbot.addWidget(message)
    message.setWindowTitle('PDF changed')
    message.setText('Choose what to do')
    message.setDetailedText('Full backend diagnostics\nTraceback line')
    keep = message.addButton('Keep current contents', QMessageBox.ButtonRole.RejectRole)
    reload = message.addButton('Reload', QMessageBox.ButtonRole.AcceptRole)
    message.setDefaultButton(keep)
    message.show()
    qtbot.waitExposed(message)
    assert message.buttonRole(keep) == QMessageBox.ButtonRole.RejectRole
    assert message.buttonRole(reload) == QMessageBox.ButtonRole.AcceptRole
    assert message.defaultButton() is keep
    assert message.detailedText() == 'Full backend diagnostics\nTraceback line'
    details = next(b for b in message.buttons() if b not in (keep, reload))
    qtbot.mouseClick(details, Qt.MouseButton.LeftButton)
    assert any(edit.isVisible() for edit in message.findChildren(QTextEdit))
    qtbot.mouseClick(reload, Qt.MouseButton.LeftButton)
    assert message.clickedButton() is reload


def test_message_without_window_title_keeps_body_and_uses_type_heading(qapp, qtbot):
    from repdf.message_dialogs import style_message
    from repdf.strings import tr
    message = QMessageBox(QMessageBox.Icon.Warning, '', 'Complete original explanation',
                         QMessageBox.StandardButton.Ok)
    qtbot.addWidget(message)
    style_message(message)
    assert message.text() == tr('警告')
    assert message.informativeText() == 'Complete original explanation'
