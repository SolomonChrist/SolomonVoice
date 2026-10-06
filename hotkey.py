"""Owned Windows global-hotkey registration for push-to-talk.

This deliberately uses RegisterHotKey instead of a low-level keyboard hook.  Windows
owns suppression of the configured chord and gives it back immediately when the
registration is removed, so SolomonVoice cannot leave a dangling key hook behind.
"""

from __future__ import annotations

import ctypes
import threading
import time
from ctypes import wintypes


WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
PM_NOREMOVE = 0x0000
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000
HOTKEY_ID = 0x534F

MODIFIERS = {
    "alt": MOD_ALT,
    "ctrl": MOD_CONTROL,
    "control": MOD_CONTROL,
    "shift": MOD_SHIFT,
    "win": MOD_WIN,
    "windows": MOD_WIN,
}

MODIFIER_VKS = {
    "alt": (0x12, 0xA4, 0xA5),
    "ctrl": (0x11, 0xA2, 0xA3),
    "control": (0x11, 0xA2, 0xA3),
    "shift": (0x10, 0xA0, 0xA1),
    "win": (0x5B, 0x5C),
    "windows": (0x5B, 0x5C),
}

NAMED_KEYS = {
    "space": 0x20,
    "tab": 0x09,
    "escape": 0x1B,
    "esc": 0x1B,
    "insert": 0x2D,
    "delete": 0x2E,
    "home": 0x24,
    "end": 0x23,
    "page_up": 0x21,
    "page_down": 0x22,
    "up": 0x26,
    "down": 0x28,
    "left": 0x25,
    "right": 0x27,
}
NAMED_KEYS.update({f"f{number}": 0x6F + number for number in range(1, 25)})


class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt", wintypes.POINT),
        ("lPrivate", wintypes.DWORD),
    ]


def virtual_key(key_name: str) -> int:
    """Translate a configured key name to a Windows virtual-key code."""
    name = key_name.lower().strip()
    if name in NAMED_KEYS:
        return NAMED_KEYS[name]
    if len(name) == 1 and name.isalnum():
        return ord(name.upper())
    raise ValueError(f"Unsupported hotkey key: {key_name}")


def modifier_mask(modifiers: list[str]) -> int:
    """Translate configured modifier names to a RegisterHotKey mask."""
    mask = MOD_NOREPEAT
    for modifier in modifiers:
        name = modifier.lower().strip()
        if name not in MODIFIERS:
            raise ValueError(f"Unsupported hotkey modifier: {modifier}")
        mask |= MODIFIERS[name]
    return mask


class NativeHotkey:
    """Register one owned system hotkey and report press/release transitions."""

    def __init__(self, key: str, modifiers: list[str], on_press, on_release):
        if not hasattr(ctypes, "WinDLL"):
            raise RuntimeError("SolomonVoice global hotkeys require Windows")
        self.key_name = key.lower()
        self.modifiers = [item.lower() for item in modifiers]
        self.vk = virtual_key(key)
        self.modifier_flags = modifier_mask(self.modifiers)
        self.on_press = on_press
        self.on_release = on_release

        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._thread: threading.Thread | None = None
        self._release_thread: threading.Thread | None = None
        self._thread_id: int | None = None
        self._ready = threading.Event()
        self._unregistered = threading.Event()
        self._running = threading.Event()
        self._start_error: Exception | None = None
        self._teardown_error: Exception | None = None
        self._pressed = threading.Event()
        self._configure_api()

    def _configure_api(self) -> None:
        self._user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
        self._user32.RegisterHotKey.restype = wintypes.BOOL
        self._user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
        self._user32.UnregisterHotKey.restype = wintypes.BOOL
        self._user32.GetMessageW.argtypes = [ctypes.POINTER(MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
        self._user32.GetMessageW.restype = wintypes.BOOL
        self._user32.PeekMessageW.argtypes = [ctypes.POINTER(MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT, wintypes.UINT]
        self._user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        self._user32.PostThreadMessageW.restype = wintypes.BOOL
        self._user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
        self._user32.GetAsyncKeyState.restype = wintypes.SHORT
        self._kernel32.GetCurrentThreadId.restype = wintypes.DWORD

    @property
    def display_name(self) -> str:
        parts = ["Ctrl" if item in ("ctrl", "control") else item.title() for item in self.modifiers]
        parts.append(self.key_name.title())
        return "+".join(parts)

    @property
    def active(self) -> bool:
        return self._running.is_set()

    def start(self) -> None:
        """Register the hotkey and start its private Windows message loop."""
        if self._thread and self._thread.is_alive():
            return
        self._ready.clear()
        self._unregistered.clear()
        self._start_error = None
        self._teardown_error = None
        self._running.set()
        self._thread = threading.Thread(target=self._message_loop, name="SolomonVoiceHotkey", daemon=True)
        self._thread.start()
        if not self._ready.wait(timeout=3):
            self._running.clear()
            raise RuntimeError("Timed out while registering the global hotkey")
        if self._start_error:
            self._running.clear()
            raise self._start_error

    def stop(self) -> None:
        """Unregister only this app's hotkey and stop all owned workers."""
        if self._thread is None:
            return
        self._running.clear()
        self._pressed.clear()
        thread_id = self._thread_id
        thread = self._thread
        if thread_id and thread and thread.is_alive():
            posted = self._user32.PostThreadMessageW(thread_id, WM_QUIT, 0, 0)
            if not posted and not self._unregistered.is_set():
                error = ctypes.get_last_error()
                raise RuntimeError(f"Could not request hotkey shutdown (Windows error {error})")
        if thread and thread is not threading.current_thread():
            thread.join(timeout=3)
        if thread and thread.is_alive():
            raise RuntimeError("Hotkey thread did not stop; keyboard release is not confirmed")
        if not self._unregistered.wait(timeout=0.2):
            raise RuntimeError("Windows did not confirm that the hotkey was unregistered")
        if self._teardown_error:
            raise self._teardown_error
        release_thread = self._release_thread
        if release_thread and release_thread is not threading.current_thread():
            release_thread.join(timeout=1)
        self._thread = None
        self._release_thread = None
        self._thread_id = None

    def wait_until_released(self, timeout: float = 3.0) -> bool:
        """Wait until every key in the configured chord is physically released."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not self.any_hotkey_key_down():
                return True
            time.sleep(0.01)
        return not self.any_hotkey_key_down()

    def any_hotkey_key_down(self) -> bool:
        if self._is_down(self.vk):
            return True
        for modifier in self.modifiers:
            if any(self._is_down(vk) for vk in MODIFIER_VKS[modifier]):
                return True
        return False

    def _is_down(self, vk: int) -> bool:
        return bool(self._user32.GetAsyncKeyState(vk) & 0x8000)

    def _message_loop(self) -> None:
        registered = False
        try:
            message = MSG()
            self._user32.PeekMessageW(ctypes.byref(message), None, 0, 0, PM_NOREMOVE)
            self._thread_id = int(self._kernel32.GetCurrentThreadId())
            registered = bool(
                self._user32.RegisterHotKey(None, HOTKEY_ID, self.modifier_flags, self.vk)
            )
            if not registered:
                error = ctypes.get_last_error()
                self._start_error = RuntimeError(
                    f"Could not register {self.display_name} (Windows error {error}). "
                    "Another application may already use it."
                )
                return
            self._ready.set()

            while self._running.is_set():
                result = self._user32.GetMessageW(ctypes.byref(message), None, 0, 0)
                if result <= 0:
                    break
                if message.message == WM_HOTKEY and message.wParam == HOTKEY_ID:
                    self._handle_press()
        except Exception as exc:
            self._start_error = exc
        finally:
            if registered:
                if not self._user32.UnregisterHotKey(None, HOTKEY_ID):
                    error = ctypes.get_last_error()
                    self._teardown_error = RuntimeError(
                        f"Windows failed to unregister the hotkey (error {error})"
                    )
            self._running.clear()
            self._unregistered.set()
            self._ready.set()

    def _handle_press(self) -> None:
        if self._pressed.is_set() or not self._running.is_set():
            return
        self._pressed.set()
        try:
            self.on_press()
        finally:
            self._release_thread = threading.Thread(
                target=self._watch_release,
                name="SolomonVoiceKeyRelease",
                daemon=True,
            )
            self._release_thread.start()

    def _watch_release(self) -> None:
        while self._running.is_set() and self._is_down(self.vk):
            time.sleep(0.01)
        was_pressed = self._pressed.is_set()
        self._pressed.clear()
        if was_pressed and self._running.is_set():
            self.on_release()
