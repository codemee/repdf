import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QFont, QWheelEvent
from PySide6.QtWidgets import QApplication, QTreeWidgetItem

from repdf.app import DocumentView, MainWindow
from repdf import desktop_preferences as desktop
from test_search import loaded_document, search_pdf, wait_search


@pytest.mark.parametrize('width', [1100, 320])
def test_annotations_and_search_coexist_and_close_independently(qtbot, width):
    window = MainWindow()
    qtbot.addWidget(window)
    window.resize(width, 650)
    window.show()
    nav, search = window.navigation, window.search_controller
    nav.open('annotations')
    search.open()
    assert nav.panel.isVisible() and search.panel.isVisible()
    assert window.annotation_action.isChecked() and window.search_action.isChecked()
    search.close()
    assert nav.panel.isVisible() and not search.panel.isVisible()
    search.open()
    nav.close()
    assert search.panel.isVisible() and not nav.panel.isVisible()
    nav.open('annotations')
    assert search.panel.isVisible() and nav.panel.isVisible()
    if width < 640:
        nav.reveal_document()
        assert nav.content.isVisible()
        assert not nav.panel.isVisible() and not search.panel.isVisible()


def test_sidebar_font_sizes_are_independent_persistent_and_support_ctrl_wheel(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    nav, search = window.navigation, window.search_controller
    group = QTreeWidgetItem(nav.panel.tree, ['Page'])
    bold = QFont(nav.panel.tree.font())
    bold.setBold(True)
    group.setFont(0, bold)
    nav.text_size.actions[20].trigger()
    search.text_size.actions[14].trigger()
    assert nav.panel.tree.font().pointSize() == 20
    assert group.font(0).pointSize() == 20 and group.font(0).bold()
    assert search.panel.files.font().pointSize() == 14
    assert search.panel.files.header().font().bold()
    assert search.panel.query.font().pointSize() == 14
    event = QWheelEvent(QPointF(5, 5), QPointF(5, 5), QPoint(), QPoint(0, 120),
                        Qt.MouseButton.NoButton, Qt.KeyboardModifier.ControlModifier,
                        Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(search.panel.files.viewport(), event)
    assert search.text_size.size == 16 and nav.text_size.size == 20
    window._theme_controller.set_mode('dark')
    window.language_controller.set_mode('en')
    assert search.panel.files.font().pointSize() == 16
    assert nav.panel.tree.font().pointSize() == 20
    restored = MainWindow()
    qtbot.addWidget(restored)
    assert restored.navigation.text_size.size == 20
    assert restored.search_controller.text_size.size == 16


def test_fullscreen_keeps_both_floating_panels_and_navigates_search_results(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr(DocumentView, '_queue_all_renders', lambda self: None)
    first, second = tmp_path / 'first.pdf', tmp_path / 'second.pdf'
    search_pdf(first)
    search_pdf(second, [[(40, 340, 'nothing')], [(40, 340, 'copy target')]])
    window = MainWindow()
    qtbot.addWidget(window)
    a = loaded_document(window, first)
    b = loaded_document(window, second, 2)
    window.activate_document(a)
    window.show()
    nav, search = window.navigation, window.search_controller
    nav.open('annotations')
    window._show_fullscreen_preview('single')
    viewer = window._fullscreen_preview
    search.open()
    assert window._fullscreen_preview is viewer
    assert nav.floating.isVisible() and search.floating.isVisible()
    assert viewer.size() == window.screen().geometry().size()
    search.panel.scope.setCurrentIndex(2)
    search.panel.query.setText('copy')
    search.start()
    wait_search(qtbot, search)
    for index in range(search.panel.files.topLevelItemCount()):
        item = search.panel.files.topLevelItem(index)
        if item.data(0, Qt.ItemDataRole.UserRole) == b.document_id:
            search.panel.files.setCurrentItem(item)
            break
    qtbot.waitUntil(lambda: window._fullscreen_preview.document is b)
    viewer = window._fullscreen_preview
    assert viewer.page_index == 1
    assert viewer.labels[1]._active_search_rects
    assert nav.floating.isVisible() and search.floating.isVisible()
    search.panel.close_button.click()
    assert not search.floating.isVisible() and nav.floating.isVisible()
    search.open()
    viewer.close()
    assert nav.floating is None and search.floating is None
    assert nav.panel.isVisible() and search.panel.isVisible()


def test_desktop_actions_show_actual_state_and_do_not_fake_default_changes(qtbot, monkeypatch):
    registered, default, changes, opened = [False], [False], [], []
    monkeypatch.setattr(desktop.sys, 'platform', 'win32')
    monkeypatch.setattr(desktop, 'windows_registration_status', lambda: registered[0])
    monkeypatch.setattr(desktop, 'pdf_default_status', lambda: default[0])
    def register():
        registered[0] = True
        changes.append(True)
    def unregister():
        registered[0] = False
        changes.append(False)
    monkeypatch.setattr(desktop.integration, 'register_windows', register)
    monkeypatch.setattr(desktop.integration, 'unregister_windows', unregister)
    monkeypatch.setattr(desktop.QDesktopServices, 'openUrl', lambda url: opened.append(url.toString()))
    window = MainWindow()
    qtbot.addWidget(window)
    assert window.preferences_menu.actions()[:2] == [window.integration_action, window.default_pdf_action]
    def icon(action):
        from PySide6.QtGui import QIcon
        return action.icon().pixmap(20, 20, QIcon.Mode.Normal, QIcon.State.On).toImage()
    unregistered_icon = icon(window.integration_action)
    not_default_icon = icon(window.default_pdf_action)
    window.integration_action.trigger()
    assert window.integration_action.isChecked() and changes == [True]
    assert '已註冊' in window.integration_action.text()
    assert icon(window.integration_action) != unregistered_icon
    registered_icon = icon(window.integration_action)
    window._refresh_toolbar_icons()
    assert icon(window.integration_action) == registered_icon
    window.default_pdf_action.trigger()
    assert not window.default_pdf_action.isChecked()
    assert opened == ['ms-settings:defaultapps?registeredAppUser=RePDF']
    default[0] = True
    window.preferences_menu.aboutToShow.emit()
    assert window.default_pdf_action.isChecked()
    assert '已設定' in window.default_pdf_action.text()
    assert icon(window.default_pdf_action) != not_default_icon
    window.integration_action.trigger()
    assert not window.integration_action.isChecked() and changes == [True, False]
    assert icon(window.integration_action) == unregistered_icon


def test_registration_status_detects_partial_registration_without_writing():
    integration = desktop.integration
    values = {
        (r'Software\RegisteredApplications', 'RePDF'): integration.APP_KEY,
        (integration.APP_KEY + r'\FileAssociations', '.pdf'): integration.PROG_ID,
        (r'Software\Classes\.pdf\OpenWithProgids', integration.PROG_ID): '',
        (rf'Software\Classes\{integration.PROG_ID}\shell\open\command', ''): 'repdf.exe "%1"',
        (integration.CONTEXT_KEY + r'\command', ''): 'repdf.exe "%1"',
    }
    def read(path, name):
        try:
            return values[path, name]
        except KeyError:
            raise FileNotFoundError
    assert desktop.windows_registration_status(read)
    values.pop((integration.CONTEXT_KEY + r'\command', ''))
    assert not desktop.windows_registration_status(read)


def test_default_checkbox_keeps_actual_state_when_opening_settings(qtbot, monkeypatch):
    monkeypatch.setattr(desktop.sys, 'platform', 'win32')
    monkeypatch.setattr(desktop, 'windows_registration_status', lambda: True)
    monkeypatch.setattr(desktop, 'pdf_default_status', lambda: True)
    opened = []
    monkeypatch.setattr(desktop.QDesktopServices, 'openUrl', lambda url: opened.append(url.toString()))
    dialog = desktop.integration.DesktopIntegrationDialog()
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.mouseClick(dialog.default_checkbox, Qt.MouseButton.LeftButton,
                     pos=QPoint(8, dialog.default_checkbox.height() // 2))
    assert dialog.default_checkbox.isChecked()
    assert opened
