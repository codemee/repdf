"""Windows automatic Recent Jump List, using explicit RePDF shell links."""
from pathlib import Path
from functools import lru_cache
import subprocess
import sys

APP_ID = 'codemee.RePDF'


@lru_cache(maxsize=1)
def recent_icon_path():
    # Shell icons need a persistent ICO, independent of Python and extraction.
    from repdf.desktop_integration import install_application_icon
    return install_application_icon().rsplit(',', 1)[0].strip('"')


def set_application_id():
    if sys.platform == 'win32':
        import ctypes
        shell = ctypes.WinDLL('shell32')
        shell.SetCurrentProcessExplicitAppUserModelID.argtypes = [ctypes.c_wchar_p]
        shell.SetCurrentProcessExplicitAppUserModelID(APP_ID)


def launch_target(path):
    executable = Path(sys.executable).resolve()
    args = []
    if not getattr(sys, 'frozen', False):
        windowed = executable.with_name('pythonw.exe')
        if windowed.is_file():
            executable = windowed
        args = ['-m', 'repdf']
    return str(executable), subprocess.list2cmdline([*args, str(path)])


def publish_recent_document(path):
    if sys.platform != 'win32':
        return False
    try:
        _publish_link(Path(path))
        return True
    except (OSError, ValueError):
        # Shell history can be disabled or unavailable; opening a PDF still works.
        return False


def _publish_link(path, notify=None):
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

    class AppLink(c.Structure):
        _fields_ = [('link', c.c_void_p), ('appid', c.c_wchar_p)]

    def check(result):
        if result < 0:
            raise OSError(f'Windows Shell HRESULT 0x{result & 0xffffffff:08x}')

    def method(pointer, slot, result_type, *argtypes):
        table = c.cast(pointer, c.POINTER(c.POINTER(c.c_void_p))).contents
        return c.WINFUNCTYPE(result_type, c.c_void_p, *argtypes)(table[slot])

    ole = c.WinDLL('ole32')
    ole.CoInitializeEx.argtypes = [c.c_void_p, c.c_uint32]
    ole.CoInitializeEx.restype = c.c_long
    initialized = ole.CoInitializeEx(None, 2)
    # RPC_E_CHANGED_MODE means Qt already initialized a different apartment.
    if initialized < 0 and initialized != -2147417850:
        check(initialized)
    link, store = c.c_void_p(), c.c_void_p()
    try:
        ole.CoCreateInstance.argtypes = [c.POINTER(GUID), c.c_void_p, c.c_uint32,
                                        c.POINTER(GUID), c.POINTER(c.c_void_p)]
        ole.CoCreateInstance.restype = c.c_long
        check(ole.CoCreateInstance(c.byref(GUID('00021401-0000-0000-c000-000000000046')),
              None, 1, c.byref(GUID('000214f9-0000-0000-c000-000000000046')), c.byref(link)))
        executable, arguments = launch_target(path)
        for slot, text in ((20, executable), (11, arguments), (7, str(path))):
            check(method(link, slot, c.c_long, c.c_wchar_p)(link, text))
        check(method(link, 17, c.c_long, c.c_wchar_p, c.c_int)(link, recent_icon_path(), 0))
        check(method(link, 0, c.c_long, c.POINTER(GUID), c.POINTER(c.c_void_p))(
            link, c.byref(GUID('886d8eeb-8cf2-4446-8d02-cdba1dbdcf99')), c.byref(store)))
        key = PropertyKey(GUID('f29f85e0-4ff9-1068-ab91-08002b27b3d9'), 2)  # PKEY_Title
        title = PropVariant()
        title.vt, title.value.text = 31, path.name  # VT_LPWSTR, borrowed until SetValue copies it.
        check(method(store, 6, c.c_long, c.POINTER(PropertyKey), c.POINTER(PropVariant))(
            store, c.byref(key), c.byref(title)))
        check(method(store, 7, c.c_long)(store))
        shell = c.WinDLL('shell32')
        shell.SHAddToRecentDocs.argtypes = [c.c_uint, c.c_void_p]
        shell.SHAddToRecentDocs.restype = None
        # SHARD_APPIDINFOLINK = 7. A link explicitly opens RePDF even if another
        # PDF reader is the default application. It does not change associations.
        if notify is None:
            shell.SHAddToRecentDocs(7, c.byref(AppLink(link, APP_ID)))
        else:
            notify(link, store, key)
    finally:
        for pointer in (store, link):
            if pointer:
                method(pointer, 2, c.c_ulong)(pointer)
        if initialized >= 0:
            ole.CoUninitialize()
