"""Forward Windows launches before loading Qt or PDF libraries."""
import argparse
import hashlib
import json
import sys
from pathlib import Path


def instance_name():
    identity = hashlib.sha256(str(Path.home()).encode()).hexdigest()[:20]
    return f'io.github.codemee.repdf-{identity}'


def file_arguments(arguments):
    parser = argparse.ArgumentParser(prog='repdf', description='Read the PDF')
    parser.add_argument('files', nargs='*', type=lambda value: str(Path(value).resolve()))
    return parser.parse_args(arguments).files


def forward_to_running(paths, name=None):
    """Best-effort bounded native pipe write; normal startup handles any failure."""
    if sys.platform != 'win32':
        return False
    import ctypes as c
    from ctypes import wintypes as w

    class Overlapped(c.Structure):
        _fields_ = [('Internal', c.c_size_t), ('InternalHigh', c.c_size_t),
                    ('Offset', w.DWORD), ('OffsetHigh', w.DWORD), ('hEvent', w.HANDLE)]

    kernel = c.WinDLL('kernel32', use_last_error=True)
    kernel.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, c.c_void_p,
                                   w.DWORD, w.DWORD, w.HANDLE]
    kernel.CreateFileW.restype = w.HANDLE
    kernel.CreateEventW.argtypes = [c.c_void_p, w.BOOL, w.BOOL, w.LPCWSTR]
    kernel.CreateEventW.restype = w.HANDLE
    kernel.CloseHandle.argtypes = [w.HANDLE]
    kernel.WriteFile.argtypes = [w.HANDLE, c.c_void_p, w.DWORD,
                                 c.POINTER(w.DWORD), c.POINTER(Overlapped)]
    kernel.WaitForSingleObject.argtypes = [w.HANDLE, w.DWORD]
    kernel.GetOverlappedResult.argtypes = [w.HANDLE, c.POINTER(Overlapped),
                                           c.POINTER(w.DWORD), w.BOOL]
    kernel.CancelIoEx.argtypes = [w.HANDLE, c.POINTER(Overlapped)]
    kernel.GetNamedPipeServerProcessId.argtypes = [w.HANDLE, c.POINTER(w.ULONG)]
    payload = json.dumps(paths, ensure_ascii=False).encode('utf-8') + b'\n'
    if len(payload) > 1024 * 1024:
        return False
    pipe = kernel.CreateFileW('\\\\.\\pipe\\' + (name or instance_name()),
                              0x40000000, 0, None, 3, 0x40000000, None)
    if pipe == c.c_void_p(-1).value:
        return False
    event = kernel.CreateEventW(None, True, False, None)
    try:
        if not event:
            return False
        server_pid = w.ULONG()
        if kernel.GetNamedPipeServerProcessId(pipe, c.byref(server_pid)):
            # Pass foreground activation rights from the Explorer launch.
            user = c.WinDLL('user32', use_last_error=True)
            user.AllowSetForegroundWindow.argtypes = [w.DWORD]
            user.AllowSetForegroundWindow(server_pid.value)
        operation = Overlapped(hEvent=event)
        buffer = c.create_string_buffer(payload)
        count = w.DWORD()
        if not kernel.WriteFile(pipe, buffer, len(payload), c.byref(count), c.byref(operation)):
            if c.get_last_error() != 997:  # ERROR_IO_PENDING
                return False
            if kernel.WaitForSingleObject(event, 1500) != 0:
                kernel.CancelIoEx(pipe, c.byref(operation))
                # Keep the buffer and OVERLAPPED alive until cancellation completes.
                kernel.GetOverlappedResult(pipe, c.byref(operation), c.byref(count), True)
                return False
            if not kernel.GetOverlappedResult(pipe, c.byref(operation), c.byref(count), False):
                return False
        return count.value == len(payload)
    finally:
        if event:
            kernel.CloseHandle(event)
        kernel.CloseHandle(pipe)
