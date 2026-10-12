"""Find extra NTFS data streams, which a content comparison of the main stream misses."""

from __future__ import annotations

import sys
from pathlib import Path

# Streams that carry no user data of their own: the main stream, and the download
# marker Windows adds to files fetched from the internet.
_HARMLESS = {"::$DATA", ":Zone.Identifier:$DATA"}


def extra_streams(path: Path) -> list[str]:
    """Return the names of extra data streams on ``path``; always empty off Windows.

    Raises ``OSError`` when the streams cannot be listed.
    """
    if sys.platform != "win32":
        return []
    return [name for name in _list_streams(str(path)) if name not in _HARMLESS]


if sys.platform == "win32":  # pragma: no cover - Windows only

    def _list_streams(path: str) -> list[str]:
        import ctypes
        from ctypes import wintypes

        class _FindStreamData(ctypes.Structure):
            _fields_ = (("size", ctypes.c_longlong), ("name", wintypes.WCHAR * 296))

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        find_first = kernel32.FindFirstStreamW
        find_first.argtypes = (wintypes.LPCWSTR, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD)
        find_first.restype = wintypes.HANDLE
        find_next = kernel32.FindNextStreamW
        find_next.argtypes = (wintypes.HANDLE, ctypes.c_void_p)
        find_next.restype = wintypes.BOOL
        kernel32.FindClose.argtypes = (wintypes.HANDLE,)

        data = _FindStreamData()
        handle = find_first(path, 0, ctypes.byref(data), 0)
        if handle in (None, wintypes.HANDLE(-1).value):
            error = ctypes.get_last_error()
            if error == 38:  # ERROR_HANDLE_EOF: no streams at all (e.g. a FAT volume)
                return []
            raise ctypes.WinError(error)
        names = [data.name]
        try:
            while find_next(handle, ctypes.byref(data)):
                names.append(data.name)
            error = ctypes.get_last_error()
            if error != 38:
                raise ctypes.WinError(error)
        finally:
            kernel32.FindClose(handle)
        return names

else:

    def _list_streams(path: str) -> list[str]:
        return []
