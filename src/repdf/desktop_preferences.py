"""Read actual desktop integration state; defaults remain a system choice."""
import sys

from PySide6.QtCore import QObject, QUrl
from PySide6.QtGui import QAction, QDesktopServices
from PySide6.QtWidgets import QMessageBox

from repdf import desktop_integration as integration
from repdf.icons import toolbar_icon
from repdf.strings import tr


def windows_registration_status(read_value=None):
    if read_value is None:
        import winreg

        def read_value(path, name):
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
                return winreg.QueryValueEx(key, name)[0]
    try:
        return (read_value(r'Software\RegisteredApplications', 'RePDF') == integration.APP_KEY
                and read_value(integration.APP_KEY + r'\FileAssociations', '.pdf') == integration.PROG_ID
                and read_value(r'Software\Classes\.pdf\OpenWithProgids', integration.PROG_ID) is not None
                and bool(read_value(rf'Software\Classes\{integration.PROG_ID}\shell\open\command', ''))
                and bool(read_value(integration.CONTEXT_KEY + r'\command', '')))
    except FileNotFoundError:
        return False
    except OSError:
        return None


def pdf_default_status():
    """Query the effective association instead of writing Windows UserChoice."""
    if sys.platform == 'win32':
        import ctypes
        from ctypes import wintypes
        query = ctypes.WinDLL('shlwapi').AssocQueryStringW
        query.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.LPCWSTR,
                          wintypes.LPCWSTR, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
        query.restype = ctypes.c_long
        length = wintypes.DWORD()
        query(0, 20, '.pdf', None, None, ctypes.byref(length))  # ASSOCSTR_PROGID
        if not 0 < length.value < 32768:
            return None
        buffer = ctypes.create_unicode_buffer(length.value)
        if query(0, 20, '.pdf', None, buffer, ctypes.byref(length)) != 0:
            return None
        return buffer.value.casefold() in (integration.PROG_ID.casefold(), r'applications\repdf.exe')
    if sys.platform == 'darwin':
        import ctypes as c
        core = c.CDLL('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')
        launch = c.CDLL('/System/Library/Frameworks/CoreServices.framework/CoreServices')
        core.CFStringCreateWithCString.argtypes = [c.c_void_p, c.c_char_p, c.c_uint32]
        core.CFStringCreateWithCString.restype = c.c_void_p
        core.CFStringGetCString.argtypes = [c.c_void_p, c.c_void_p, c.c_long, c.c_uint32]
        core.CFStringGetCString.restype = c.c_bool
        core.CFRelease.argtypes = [c.c_void_p]
        launch.LSCopyDefaultRoleHandlerForContentType.argtypes = [c.c_void_p, c.c_uint32]
        launch.LSCopyDefaultRoleHandlerForContentType.restype = c.c_void_p
        content_type = core.CFStringCreateWithCString(None, b'com.adobe.pdf', 0x08000100)
        if not content_type:
            return None
        handler = None
        try:
            handler = launch.LSCopyDefaultRoleHandlerForContentType(content_type, 0xFFFFFFFF)
            if not handler:
                return None
            buffer = c.create_string_buffer(4096)
            if not core.CFStringGetCString(handler, buffer, len(buffer), 0x08000100):
                return None
            return buffer.value.decode('utf-8') == 'io.github.codemee.repdf'
        finally:
            if handler:
                core.CFRelease(handler)
            core.CFRelease(content_type)
    return None


class DesktopPreferenceActions(QObject):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.registration = QAction(owner)
        self.registration.setCheckable(True)
        self.registration.triggered.connect(self.set_registered)
        self.default = QAction(owner)
        self.default.setCheckable(True)
        self.default.triggered.connect(self.open_defaults)
        self.refresh()

    def refresh(self):
        try:
            registered = windows_registration_status() if sys.platform == 'win32' else None
        except (OSError, AttributeError):
            registered = None
        try:
            default = pdf_default_status()
        except (OSError, AttributeError):
            default = None
        self.registration.setText(tr('PDF 開啟功能：{state}', state=tr(
            '已註冊' if registered is True else '尚未註冊' if registered is False else '無法判定')))
        self.registration.setChecked(registered is True)
        self.registration.setEnabled(sys.platform == 'win32' and registered is not None)
        self.registration.setToolTip(tr('已註冊' if registered else '尚未註冊') if registered is not None
                                     else tr('PDF 開啟整合由系統管理'))
        self.default.setText(tr('預設 PDF 應用程式：{state}', state=tr(
            '已設定' if default is True else '未設定' if default is False else '無法判定')))
        self.default.setChecked(default is True)
        self.default.setEnabled(sys.platform in ('win32', 'darwin'))
        self.default.setToolTip(tr('勾選代表目前由 RePDF 預設開啟 PDF；點擊開啟系統設定'))
        self.refresh_icons()

    def refresh_icons(self):
        self.registration.setIcon(toolbar_icon('integration_checked' if self.registration.isChecked() else 'integration'))
        self.default.setIcon(toolbar_icon('open_checked' if self.default.isChecked() else 'open'))

    def set_registered(self, checked):
        if sys.platform != 'win32':
            return
        try:
            (integration.register_windows if checked else integration.unregister_windows)()
        except OSError as error:
            QMessageBox.warning(self.owner, tr('系統整合'), str(error))
        self.refresh()

    def open_defaults(self, _checked=False):
        self.refresh()
        if sys.platform == 'win32':
            QDesktopServices.openUrl(QUrl('ms-settings:defaultapps?registeredAppUser=RePDF'))
        elif sys.platform == 'darwin':
            QMessageBox.information(self.owner, tr('系統整合'), tr(
                '將 RePDF.app 放入「應用程式」。在 Finder 選取 PDF，開啟「取得資訊」，於「打開檔案的應用程式」選擇 RePDF，再按「全部更改」。'))
