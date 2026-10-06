"""Modifier-safe Unicode text injection for Windows."""

from __future__ import annotations

import ctypes
from ctypes import wintypes


INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", wintypes.WPARAM),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", wintypes.WPARAM),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class INPUT_UNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("union",)
    _fields_ = [("type", wintypes.DWORD), ("union", INPUT_UNION)]


class GUITHREADINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("hwndActive", wintypes.HWND),
        ("hwndFocus", wintypes.HWND),
        ("hwndCapture", wintypes.HWND),
        ("hwndMenuOwner", wintypes.HWND),
        ("hwndMoveSize", wintypes.HWND),
        ("hwndCaret", wintypes.HWND),
        ("rcCaret", wintypes.RECT),
    ]


def utf16_code_units(text: str) -> list[int]:
    """Return UTF-16 code units, including surrogate pairs for non-BMP text."""
    encoded = text.encode("utf-16-le")
    return [int.from_bytes(encoded[index : index + 2], "little") for index in range(0, len(encoded), 2)]


class Injector:
    """Type Unicode into the focused window without touching the clipboard."""

    def __init__(self, append_space=True, require_same_window=True):
        if not hasattr(ctypes, "WinDLL"):
            raise RuntimeError("Text injection requires Windows")
        self.append_space = append_space
        self.require_same_window = require_same_window
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
        self._user32.SendInput.restype = wintypes.UINT
        self._user32.GetForegroundWindow.restype = wintypes.HWND
        self._user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.c_void_p]
        self._user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        self._user32.GetGUIThreadInfo.argtypes = [wintypes.DWORD, ctypes.POINTER(GUITHREADINFO)]
        self._user32.GetGUIThreadInfo.restype = wintypes.BOOL

    def foreground_window(self) -> int:
        return int(self._user32.GetForegroundWindow() or 0)

    def capture_target(self) -> tuple[int, int, int]:
        """Capture the foreground window plus focused control and caret owner."""
        foreground = self.foreground_window()
        if not foreground:
            return (0, 0, 0)
        thread_id = self._user32.GetWindowThreadProcessId(foreground, None)
        info = GUITHREADINFO(cbSize=ctypes.sizeof(GUITHREADINFO))
        if thread_id and self._user32.GetGUIThreadInfo(thread_id, ctypes.byref(info)):
            return (
                foreground,
                int(info.hwndFocus or 0),
                int(info.hwndCaret or 0),
            )
        return (foreground, 0, 0)

    def inject(self, text: str, target_window: tuple[int, int, int] | int | None = None) -> None:
        """Type text at the active caret if the target window is still active."""
        if not text:
            raise ValueError("Cannot inject empty text")
        if self.append_space:
            text += " "

        if self.require_same_window:
            current_target = self.capture_target()
            if isinstance(target_window, int):
                target_matches = bool(target_window) and current_target[0] == target_window
            else:
                target_matches = bool(target_window and target_window[0]) and current_target == target_window
            if not target_matches:
                raise RuntimeError(
                    "The active text target changed while transcribing, so text was not inserted. "
                    "Dictate again with the target field focused."
                )

        units = utf16_code_units(text)
        events = (INPUT * (len(units) * 2))()
        for index, unit in enumerate(units):
            events[index * 2] = INPUT(
                type=INPUT_KEYBOARD,
                ki=KEYBDINPUT(0, unit, KEYEVENTF_UNICODE, 0, 0),
            )
            events[index * 2 + 1] = INPUT(
                type=INPUT_KEYBOARD,
                ki=KEYBDINPUT(0, unit, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0, 0),
            )

        sent = int(self._user32.SendInput(len(events), events, ctypes.sizeof(INPUT)))
        if sent != len(events):
            error = ctypes.get_last_error()
            raise RuntimeError(
                f"Windows accepted {sent} of {len(events)} text input events (error {error}). "
                "Elevated applications only accept input from another elevated application."
            )
