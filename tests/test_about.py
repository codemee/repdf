from importlib.metadata import PackagePath
from types import SimpleNamespace

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction

from repdf.about import AboutDialog, license_documents
from repdf.app import MainWindow
from repdf.system_menu import ABOUT_COMMAND, WM_SYSCOMMAND, is_about_command


def test_about_displays_project_and_selectable_offline_licenses(qtbot, monkeypatch):
    opened = []
    monkeypatch.setattr('repdf.about.QDesktopServices.openUrl', lambda url: opened.append(url.toString()))
    dialog = AboutDialog()
    qtbot.addWidget(dialog)
    dialog.show()
    assert 'GNU GENERAL PUBLIC LICENSE' in dialog.license_text.toPlainText()
    assert 'Version 3' in dialog.license_text.toPlainText()
    assert 'GPL-3.0-only' in dialog.summary.text()
    assert 'Third-party notices' in dialog.notice_text.toPlainText()
    items = dialog.notice_tree.findItems('MODEL_LICENSES.md', Qt.MatchFlag.MatchExactly | Qt.MatchFlag.MatchRecursive, 0)
    assert items
    dialog.notice_tree.setCurrentItem(items[0])
    assert 'Baidu' in dialog.notice_text.toPlainText()
    dialog.source_button.click()
    assert opened == ['https://github.com/codemee/repdf']


def test_about_action_reuses_dialog_and_retranslates(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    assert window.about_action.menuRole() == QAction.MenuRole.AboutRole
    window.about_action.trigger()
    dialog = window._about_dialog
    assert dialog.isVisible()
    dialog.close()
    window.about_action.trigger()
    assert window._about_dialog is dialog and dialog.isVisible()
    window.language_controller.set_mode('en')
    assert window.about_action.text() == 'About RePDF'
    assert dialog.windowTitle() == 'About RePDF'
    assert dialog.tabs.tabText(2) == 'Third-party licenses'
    assert 'without any warranty' in dialog.summary.text()
    dialog.close()


def test_license_resolution_from_frozen_bundle_and_python_metadata(tmp_path):
    package = tmp_path / 'bundle/repdf'
    legal = package / 'licenses'
    third_party = legal / 'third-party'
    third_party.mkdir(parents=True)
    (legal / 'LICENSE').write_text('frozen GPL')
    (third_party / 'THIRD_PARTY_NOTICES.md').write_text('frozen summary')
    notice = third_party / 'third_party/notices/vendor/LICENSE'
    notice.parent.mkdir(parents=True)
    notice.write_text('vendor terms')
    docs = license_documents(package, SimpleNamespace(files=[]))
    assert docs['LICENSE'].read_text() == 'frozen GPL'
    assert docs['THIRD_PARTY_NOTICES.md'].read_text() == 'frozen summary'
    assert docs['third_party/vendor/LICENSE'].read_text() == 'vendor terms'
    installed = tmp_path / 'wheel'
    path = PackagePath('repdf-1.0.dist-info/licenses/LICENSE')
    (installed / path).parent.mkdir(parents=True)
    (installed / path).write_text('wheel GPL')
    dist = SimpleNamespace(files=[path], locate_file=lambda file: installed / file)
    docs = license_documents(tmp_path / 'site-packages/repdf', dist)
    assert docs['LICENSE'].read_text() == 'wheel GPL'


def test_missing_license_is_explained_and_native_command_is_scoped(qtbot):
    dialog = AboutDialog(documents={})
    qtbot.addWidget(dialog)
    assert 'LICENSE' in dialog.license_text.toPlainText()
    assert is_about_command(WM_SYSCOMMAND, ABOUT_COMMAND)
    assert is_about_command(WM_SYSCOMMAND, ABOUT_COMMAND | 3)
    assert not is_about_command(WM_SYSCOMMAND, 0xF060)  # SC_CLOSE must remain Qt's.
    assert not is_about_command(0x0111, ABOUT_COMMAND)
