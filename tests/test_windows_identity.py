import ast
import ctypes as c
import runpy
import sys
from pathlib import Path

import pytest


def test_packaged_product_name_and_version():
    generate = runpy.run_path(str(Path(__file__).parents[1] / 'scripts/windows_version.py'))['version_info_text']
    tree = ast.parse(generate('1.2.3.dev1'))
    entries = {node.args[0].value: node.args[1].value for node in ast.walk(tree)
               if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
               and node.func.id == 'StringStruct'}
    assert entries['ProductName'] == entries['FileDescription'] == 'RePDF'
    assert entries['OriginalFilename'] == 'repdf.exe'
    assert entries['ProductVersion'] == '1.2.3.dev1'
    fixed = next(node for node in ast.walk(tree) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Name) and node.func.id == 'FixedFileInfo')
    assert ast.literal_eval(fixed.keywords[0].value) == (1, 2, 3, 0)


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows Shell properties')
def test_native_window_relaunch_identity():
    from repdf.windows_properties import (APP_PROPERTIES, GUID, PropertyKey,
                                         PropVariant, check, method,
                                         set_window_relaunch, window_store)
    user = c.WinDLL('user32')
    user.CreateWindowExW.argtypes = [c.c_ulong, c.c_wchar_p, c.c_wchar_p, c.c_ulong,
                                    c.c_int, c.c_int, c.c_int, c.c_int,
                                    c.c_void_p, c.c_void_p, c.c_void_p, c.c_void_p]
    user.CreateWindowExW.restype = c.c_void_p
    user.DestroyWindow.argtypes = [c.c_void_p]
    hwnd = user.CreateWindowExW(0, 'STATIC', '', 0, 0, 0, 1, 1, None, None, None, None)
    assert hwnd
    try:
        command = '"C:\\Program Files\\RePDF\\repdf.exe"'
        set_window_relaunch(hwnd, 'codemee.RePDF', command, 'C:\\icons\\repdf.ico')
        with window_store(hwnd) as store:
            clear = c.WinDLL('ole32').PropVariantClear
            clear.argtypes = [c.POINTER(PropVariant)]
            for pid, expected in ((2, command), (3, '"C:\\icons\\repdf.ico",0'),
                                  (4, 'RePDF'), (5, 'codemee.RePDF')):
                value = PropVariant()
                key = PropertyKey(GUID(APP_PROPERTIES), pid)
                check(method(store, 5, c.c_long, c.POINTER(PropertyKey), c.POINTER(PropVariant))(
                    store, c.byref(key), c.byref(value)))
                try:
                    assert value.vt == 31 and value.value.text == expected
                finally:
                    clear(c.byref(value))
    finally:
        user.DestroyWindow(hwnd)
