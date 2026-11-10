from pathlib import Path
import subprocess
import sys

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QMessageBox, QWidget

from repdf.recent_files import RecentFiles
from repdf import windows_recent


def history(qtbot, tmp_path):
    owner = QWidget()
    qtbot.addWidget(owner)
    owner.settings = QSettings(str(tmp_path / 'history.ini'), QSettings.Format.IniFormat)
    owner.load_pdf = lambda path: None
    return RecentFiles(owner)


def test_ten_unique_files_persist_and_reopening_moves_to_front(qtbot, tmp_path, monkeypatch):
    recent = history(qtbot, tmp_path)
    notified = []
    monkeypatch.setattr('repdf.recent_files.publish_recent_document', notified.append)
    paths = [tmp_path / f'文件 {i}.pdf' for i in range(12)]
    for path in paths:
        path.touch()
        recent.record(path)
    assert recent.paths() == paths[:1:-1]
    recent.record(paths[4])
    assert recent.paths() == [paths[4], *[p for p in paths[:1:-1] if p != paths[4]]]
    assert history(qtbot, tmp_path).paths() == recent.paths()
    assert notified[-1] == paths[4]
    recent.record(tmp_path / 'missing.pdf')
    assert len(recent.paths()) == 10 and notified[-1] == paths[4]


def test_menu_paths_open_and_missing_files_warn_without_loading(qtbot, tmp_path, monkeypatch):
    recent = history(qtbot, tmp_path)
    recent.populate()
    assert not recent.menu.actions()[0].isEnabled()
    paths = [tmp_path / folder / 'A&B.pdf' for folder in ('one', 'two')]
    for path in paths:
        path.parent.mkdir()
        path.touch()
        recent.record(path)
    opened, warnings = [], []
    recent.owner.load_pdf = opened.append
    monkeypatch.setattr(QMessageBox, 'warning', lambda *args: warnings.append(args[-1]))
    recent.populate()
    actions = recent.menu.actions()
    assert [a.data() for a in actions] == [str(p) for p in reversed(paths)]
    assert all('&&' in a.text() and a.toolTip() == a.data() for a in actions)
    assert [a.text() for a in actions] == ['&1  A&&B.pdf', '&2  A&&B.pdf']
    actions[0].trigger()
    assert opened == [paths[1]]
    paths[0].unlink()
    actions[1].trigger()
    assert len(opened) == 1 and str(paths[0]) in warnings[0]


def test_successful_open_and_existing_tab_update_history(qtbot, tmp_path):
    from test_navigation import load_window, navigation_pdf
    from test_preview import wait_for_preview
    first, second = (tmp_path / name for name in ('first.pdf', 'second.pdf'))
    navigation_pdf(first)
    navigation_pdf(second)
    window, doc = load_window(qtbot, first)
    assert window.recent_files.paths() == [first]
    window.load_pdf(second)
    wait_for_preview(qtbot, window.current_document())
    assert window.recent_files.paths() == [second, first]
    window.load_pdf(first)
    assert window.current_document() is doc
    assert window.recent_files.paths() == [first, second]
    window.recent_files.menu.aboutToShow.emit()
    assert window.recent_files_button.menu() is window.recent_files.menu


def test_failed_pdf_does_not_enter_history(qtbot, tmp_path, monkeypatch):
    from repdf.app import MainWindow
    window = MainWindow()
    qtbot.addWidget(window)
    errors = []
    monkeypatch.setattr(QMessageBox, 'critical', lambda *args: errors.append(args[-1]))
    path = tmp_path / 'invalid.pdf'
    path.write_text('not a PDF')
    window.load_pdf(path)
    qtbot.waitUntil(lambda: bool(errors), timeout=15000)
    assert window.recent_files.paths() == []


def test_recent_menu_survives_toolbar_overflow_and_export_guard(qtbot, tmp_path):
    from repdf.app import MainWindow
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    arrow = window.recent_files_button
    button = window.toolbar.widgetForAction(window.open_action)
    assert arrow.size() == window.fullscreen_menu_button.size()
    assert arrow.width() == 14 and arrow.parentWidget() is button.parentWidget()
    assert arrow.x() - button.geometry().right() - 1 == 2
    window.resize(320, 400)
    window.toolbar.setFixedWidth(100)
    qtbot.waitUntil(lambda: not window.toolbar.widgetForAction(window.open_action).isVisible())
    window.toolbar._populate_overflow()
    assert any(a.menu() is window.recent_files.menu for a in window.toolbar.overflow_menu.actions())
    window._set_export_running(True)
    assert not window.recent_files_button.isEnabled()
    window._set_export_running(False)
    assert window.recent_files_button.isEnabled()


def test_jump_link_targets_repdf_and_quotes_paths(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, 'executable', str(tmp_path / 'Program Files' / 'repdf.exe'))
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    path = tmp_path / 'PDF 文件' / 'file name.pdf'
    executable, arguments = windows_recent.launch_target(path)
    assert Path(executable).name == 'repdf.exe'
    assert arguments == subprocess.list2cmdline([str(path)])
    monkeypatch.setattr(sys, 'frozen', False)
    assert windows_recent.launch_target(path)[1] == subprocess.list2cmdline(['-m', 'repdf', str(path)])


def test_recent_icon_uses_persistent_application_icon_once_per_process(monkeypatch, tmp_path):
    calls = []
    icon = tmp_path / 'RePDF icon.ico'
    def install():
        calls.append(True)
        return f'"{icon}",0'
    monkeypatch.setattr('repdf.desktop_integration.install_application_icon', install)
    windows_recent.recent_icon_path.cache_clear()
    try:
        assert windows_recent.recent_icon_path() == str(icon)
        assert windows_recent.recent_icon_path() == str(icon)
        assert calls == [True]
    finally:
        windows_recent.recent_icon_path.cache_clear()


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows Shell COM')
def test_native_shell_link_has_pdf_title_target_and_arguments_without_updating_history(tmp_path, monkeypatch):
    import ctypes as c
    path = tmp_path / '中文 & document.pdf'
    icon = tmp_path / 'RePDF icon.ico'
    monkeypatch.setattr(windows_recent, 'recent_icon_path', lambda: str(icon))
    seen = []

    def inspect(link, store, key):
        table = c.cast(link, c.POINTER(c.POINTER(c.c_void_p))).contents
        buffer = c.create_unicode_buffer(32768)
        get_arguments = c.WINFUNCTYPE(c.c_long, c.c_void_p, c.c_wchar_p, c.c_int)(table[10])
        assert get_arguments(link, buffer, len(buffer)) >= 0
        assert buffer.value == windows_recent.launch_target(path)[1]
        get_path = c.WINFUNCTYPE(c.c_long, c.c_void_p, c.c_wchar_p, c.c_int, c.c_void_p, c.c_uint)(table[3])
        assert get_path(link, buffer, len(buffer), None, 0) >= 0
        assert buffer.value == windows_recent.launch_target(path)[0]
        get_icon = c.WINFUNCTYPE(c.c_long, c.c_void_p, c.c_wchar_p, c.c_int, c.POINTER(c.c_int))(table[16])
        icon_index = c.c_int(-1)
        assert get_icon(link, buffer, len(buffer), c.byref(icon_index)) >= 0
        assert buffer.value == str(icon) and icon_index.value == 0
        value = c.create_string_buffer(24)
        store_table = c.cast(store, c.POINTER(c.POINTER(c.c_void_p))).contents
        get_value = c.WINFUNCTYPE(c.c_long, c.c_void_p, c.c_void_p, c.c_void_p)(store_table[5])
        assert get_value(store, c.byref(key), value) >= 0
        try:
            assert c.c_ushort.from_buffer(value).value == 31
            assert c.wstring_at(c.c_void_p.from_buffer(value, 8).value) == path.name
        finally:
            c.WinDLL('ole32').PropVariantClear(c.byref(value))
        seen.append(True)

    windows_recent._publish_link(path, inspect)
    assert seen == [True]
