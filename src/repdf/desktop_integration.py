"""Opt-in Windows registration. Never writes the user's default association."""
from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile
from importlib.resources import files

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton

from repdf.strings import tr

PROG_ID = 'RePDF.PDF'
APP_KEY = r'Software\RePDF\Capabilities'
CONTEXT_KEY = r'Software\Classes\SystemFileAssociations\.pdf\shell\RePDF'


def registration_entries(command, icon):
    """Declarative HKCU values, also testable on non-Windows platforms."""
    return [
        (rf'Software\Classes\{PROG_ID}', '', 'PDF — Read the PDF'),
        (rf'Software\Classes\{PROG_ID}\DefaultIcon', '', icon),
        (rf'Software\Classes\{PROG_ID}\Application', 'ApplicationName', 'RePDF'),
        (rf'Software\Classes\{PROG_ID}\Application', 'ApplicationDescription', 'Read the PDF'),
        (rf'Software\Classes\{PROG_ID}\Application', 'ApplicationIcon', icon),
        (rf'Software\Classes\{PROG_ID}\shell\open\command', '', command),
        (r'Software\Classes\.pdf\OpenWithProgids', PROG_ID, ''),
        (APP_KEY, 'ApplicationName', 'RePDF'),
        (APP_KEY, 'ApplicationDescription', 'Read the PDF'),
        (APP_KEY, 'ApplicationIcon', icon),
        (APP_KEY + r'\FileAssociations', '.pdf', PROG_ID),
        (r'Software\RegisteredApplications', 'RePDF', APP_KEY),
        (CONTEXT_KEY, '', 'Open with RePDF'),
        (CONTEXT_KEY, 'Icon', icon),
        (CONTEXT_KEY + r'\command', '', command),
    ]


def launch_command():
    if getattr(sys, 'frozen', False):
        # Keep the registered executable path stable across versioned downloads.
        destination = Path(os.environ['LOCALAPPDATA']) / 'Programs/RePDF/repdf.exe'
        destination.parent.mkdir(parents=True, exist_ok=True)
        source = Path(sys.executable).resolve()
        if source != destination.resolve():
            with tempfile.NamedTemporaryFile(dir=destination.parent, suffix='.new', delete=False) as stream:
                staging = Path(stream.name)
            try:
                shutil.copy2(source, staging)
                os.replace(staging, destination)
            finally:
                staging.unlink(missing_ok=True)
        executable = str(destination)
        return subprocess.list2cmdline([executable]) + ' "%1"', '"' + executable + '",0'
    executable = Path(sys.executable)
    windowed = executable.with_name('pythonw.exe')
    if windowed.is_file():
        executable = windowed
    return subprocess.list2cmdline([str(executable), '-m', 'repdf']) + ' "%1"', '"' + str(executable) + '",0'


def notify_shell():
    import ctypes
    ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)


def install_application_icon(directory=None):
    """Keep shell icons independent of Python and the one-file extraction path."""
    from repdf.icon_layout import fitted_icon
    directory = Path(directory) if directory else Path(os.environ['LOCALAPPDATA']) / 'Programs/RePDF'
    directory.mkdir(parents=True, exist_ok=True)
    icon = directory / 'repdf.ico'
    image = fitted_icon(files('repdf').joinpath('assets', 'repdf.png'))
    with tempfile.NamedTemporaryFile(dir=directory, suffix='.ico', delete=False) as stream:
        staging = Path(stream.name)
    try:
        image.save(staging, format='ICO', sizes=[(n, n) for n in (16, 20, 24, 32, 40, 48, 64, 128, 256)])
        os.replace(staging, icon)
    finally:
        staging.unlink(missing_ok=True)
    return f'"{icon}",0'


def register_windows():
    import winreg
    command, _executable_icon = launch_command()
    icon = install_application_icon()
    for path, name, value in registration_entries(command, icon):
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, path) as key:
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
    notify_shell()


def unregister_windows():
    import winreg
    # Delete only our named values and exclusively owned leaf keys.
    for path, name in ((r'Software\Classes\.pdf\OpenWithProgids', PROG_ID),
                       (r'Software\RegisteredApplications', 'RePDF')):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, name)
        except FileNotFoundError:
            pass
    paths = [CONTEXT_KEY + r'\command', CONTEXT_KEY,
             rf'Software\Classes\{PROG_ID}\shell\open\command',
             rf'Software\Classes\{PROG_ID}\shell\open',
             rf'Software\Classes\{PROG_ID}\shell',
             rf'Software\Classes\{PROG_ID}\Application',
             rf'Software\Classes\{PROG_ID}\DefaultIcon', rf'Software\Classes\{PROG_ID}',
             APP_KEY + r'\FileAssociations', APP_KEY]
    for path in paths:
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
        except FileNotFoundError:
            pass
    notify_shell()


class DesktopIntegrationDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr('系統整合'))
        self.setMinimumWidth(440)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)
        self.message = QLabel()
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        if sys.platform == 'win32':
            self.message.setText(tr('將 RePDF 加入 PDF 的「開啟方式」與快顯選單。預設應用程式仍由您在 Windows 設定中選擇。免安裝版會複製至目前使用者的 Programs/RePDF 固定位置；更新後請再次註冊。'))
            for label, callback in [('註冊 PDF 開啟功能', register_windows),
                                    ('取消註冊', unregister_windows)]:
                button = QPushButton(tr(label))
                button.setMinimumHeight(34)
                button.clicked.connect(lambda _checked=False, fn=callback: self.run_action(fn))
                layout.addWidget(button)
            settings = QPushButton(tr('開啟預設應用程式設定'))
            settings.setMinimumHeight(34)
            settings.clicked.connect(lambda: QDesktopServices.openUrl(QUrl('ms-settings:defaultapps?registeredAppUser=RePDF')))
            layout.addWidget(settings)
            hint = QLabel(tr('設定頁會顯示目前的 PDF 預設程式；點選 .pdf 那一列，再選 RePDF。'))
            hint.setWordWrap(True)
            layout.addWidget(hint)
        else:
            self.message.setText(tr('將 RePDF.app 放入「應用程式」。在 Finder 選取 PDF，開啟「取得資訊」，於「打開檔案的應用程式」選擇 RePDF，再按「全部更改」。'))
        close = QPushButton(tr('關閉'))
        close.setMinimumHeight(34)
        close.clicked.connect(self.accept)
        layout.addWidget(close)

    def run_action(self, callback):
        try:
            callback()
            self.message.setText(tr('設定已完成。取消註冊不會刪除程式或 PDF；如需更換預設程式，請使用系統設定。'))
        except OSError as error:
            self.message.setText(tr('無法完成系統整合設定：') + str(error))
