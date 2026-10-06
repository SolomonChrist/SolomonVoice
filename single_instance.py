"""Windows single-instance guard for SolomonVoice."""

import ctypes
from ctypes import wintypes


ERROR_ALREADY_EXISTS = 183


class SingleInstance:
    """Keep a named mutex open for the lifetime of the application."""

    def __init__(self, name="Local\\SolomonVoice-4A9B891A"):
        if not hasattr(ctypes, "WinDLL"):
            self._kernel32 = None
            self._handle = None
            return
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        self._kernel32.CreateMutexW.restype = ctypes.c_void_p
        self._kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        self._handle = self._kernel32.CreateMutexW(None, False, name)
        if not self._handle:
            raise OSError(ctypes.get_last_error(), "Unable to create the SolomonVoice instance lock")
        if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
            self.close()
            raise RuntimeError("SolomonVoice is already running in the system tray")

    def close(self):
        if self._kernel32 and self._handle:
            self._kernel32.CloseHandle(self._handle)
            self._handle = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()
