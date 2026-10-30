"""Windows system menu integration; other platforms use Qt menu roles."""
import sys

from PySide6.QtCore import QEvent, QObject, QTimer
from PySide6.QtGui import QGuiApplication
from shiboken6 import isValid

from repdf.strings import tr

ABOUT_COMMAND = 0x1F00  # Below SC_SIZE; low four bits reserved by WM_SYSCOMMAND.
INTEGRATION_COMMAND = 0x1F10
WM_SYSCOMMAND = 0x0112


def is_about_command(message, command):
    return message == WM_SYSCOMMAND and command & 0xFFF0 == ABOUT_COMMAND


class WindowsSystemMenu(QObject):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.api = None
        self.menu = None
        if sys.platform == 'win32' and QGuiApplication.platformName() == 'windows':
            import ctypes
            from ctypes import wintypes
            self.api = ctypes.WinDLL('user32', use_last_error=True)
            self.api.GetSystemMenu.argtypes = [wintypes.HWND, wintypes.BOOL]
            self.api.GetSystemMenu.restype = wintypes.HMENU
            self.api.GetMenuState.argtypes = [wintypes.HMENU, wintypes.UINT, wintypes.UINT]
            self.api.GetMenuState.restype = wintypes.UINT
            self.api.AppendMenuW.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_size_t, wintypes.LPCWSTR]
            self.api.AppendMenuW.restype = wintypes.BOOL
            self.api.ModifyMenuW.argtypes = [wintypes.HMENU, wintypes.UINT, wintypes.UINT, ctypes.c_size_t, wintypes.LPCWSTR]
            self.api.ModifyMenuW.restype = wintypes.BOOL
            owner.installEventFilter(self)

    def eventFilter(self, watched, event):
        if watched is self.owner and event.type() == QEvent.Type.WinIdChange:
            QTimer.singleShot(0, self.refresh)
        return False

    def refresh(self):
        if self.api is None or not isValid(self.owner) or getattr(self.owner, '_closing', False):
            return
        menu = self.api.GetSystemMenu(int(self.owner.winId()), False)
        if not menu:
            return
        self.menu = menu
        if self.api.GetMenuState(menu, ABOUT_COMMAND, 0) == 0xFFFFFFFF:
            self.api.AppendMenuW(menu, 0x0800, 0, None)  # MF_SEPARATOR
            self.api.AppendMenuW(menu, 0, ABOUT_COMMAND, tr('關於 RePDF'))
        else:
            self.api.ModifyMenuW(menu, ABOUT_COMMAND, 0, ABOUT_COMMAND, tr('關於 RePDF'))
        if self.api.GetMenuState(menu, INTEGRATION_COMMAND, 0) == 0xFFFFFFFF:
            self.api.AppendMenuW(menu, 0, INTEGRATION_COMMAND, tr('系統整合'))
        else:
            self.api.ModifyMenuW(menu, INTEGRATION_COMMAND, 0, INTEGRATION_COMMAND, tr('系統整合'))

    def native_event(self, event_type, address):
        if self.api is None or bytes(event_type) not in (b'windows_generic_MSG', b'windows_dispatcher_MSG'):
            return False
        import ctypes
        from ctypes import wintypes
        message = ctypes.cast(int(address), ctypes.POINTER(wintypes.MSG)).contents
        if message.message == WM_SYSCOMMAND and message.wParam & 0xFFF0 == INTEGRATION_COMMAND:
            QTimer.singleShot(0, self.owner.integration_action.trigger)
            return True
        if is_about_command(message.message, message.wParam):
            QTimer.singleShot(0, self.owner.about_action.trigger)
            return True
        return False
