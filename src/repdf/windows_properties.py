"""Small, shared COM helpers for Windows Shell property stores."""
from contextlib import contextmanager
import ctypes as c
import uuid


class GUID(c.Structure):
    _fields_ = [('data', c.c_ubyte * 16)]

    def __init__(self, value):
        super().__init__((c.c_ubyte * 16).from_buffer_copy(uuid.UUID(value).bytes_le))


class PropertyKey(c.Structure):
    _fields_ = [('fmtid', GUID), ('pid', c.c_uint32)]


class Value(c.Union):
    _fields_ = [('text', c.c_wchar_p), ('padding', c.c_ubyte * (16 if c.sizeof(c.c_void_p) == 8 else 8)),
                ('alignment', c.c_uint64)]


class PropVariant(c.Structure):
    _fields_ = [('vt', c.c_ushort), ('reserved', c.c_ushort * 3), ('value', Value)]


APP_PROPERTIES = '9f4c2855-9f79-4b39-a8d0-e1d42de1d5f3'


def check(result):
    if result < 0:
        raise OSError(f'Windows Shell HRESULT 0x{result & 0xffffffff:08x}')


def method(pointer, slot, result_type, *argtypes):
    table = c.cast(pointer, c.POINTER(c.POINTER(c.c_void_p))).contents
    return c.WINFUNCTYPE(result_type, c.c_void_p, *argtypes)(table[slot])


def set_text(store, key, text):
    value = PropVariant()
    value.vt, value.value.text = 31, text
    check(method(store, 6, c.c_long, c.POINTER(PropertyKey), c.POINTER(PropVariant))(
        store, c.byref(key), c.byref(value)))


@contextmanager
def window_store(hwnd):
    ole = c.WinDLL('ole32')
    ole.CoInitializeEx.argtypes = [c.c_void_p, c.c_uint32]
    ole.CoInitializeEx.restype = c.c_long
    initialized = ole.CoInitializeEx(None, 2)
    if initialized < 0 and initialized != -2147417850:  # RPC_E_CHANGED_MODE
        check(initialized)
    store = c.c_void_p()
    try:
        shell = c.WinDLL('shell32')
        shell.SHGetPropertyStoreForWindow.argtypes = [c.c_void_p, c.POINTER(GUID), c.POINTER(c.c_void_p)]
        shell.SHGetPropertyStoreForWindow.restype = c.c_long
        check(shell.SHGetPropertyStoreForWindow(hwnd,
              c.byref(GUID('886d8eeb-8cf2-4446-8d02-cdba1dbdcf99')), c.byref(store)))
        yield store
    finally:
        if store:
            method(store, 2, c.c_ulong)(store)
        if initialized >= 0:
            ole.CoUninitialize()


def set_window_relaunch(hwnd, appid, command, icon):
    with window_store(hwnd) as store:
        # AppUserModel ID plus relaunch command/name must be set together.
        for pid, text in ((5, appid), (2, command), (3, f'"{icon}",0'), (4, 'RePDF')):
            set_text(store, PropertyKey(GUID(APP_PROPERTIES), pid), text)
        check(method(store, 7, c.c_long)(store))
