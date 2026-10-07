"""Read selected or document text through UI Automation with a safe Copy fallback."""

from __future__ import annotations

import os
from pathlib import Path
import time

import ctypes
from ctypes import wintypes

from injector import GUITHREADINFO, INPUT, KEYBDINPUT, INPUT_KEYBOARD, KEYEVENTF_KEYUP


class TextCaptureError(RuntimeError):
    pass


VK_CONTROL = 0x11
VK_C = 0x43
WM_COPY = 0x0301
SMTO_ABORTIFHUNG = 0x0002
CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002


def _copy_focused_control(target_window=None) -> None:
    """Ask a standard focused control to copy without synthesizing keys."""
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    foreground = target_window[0] if target_window else user32.GetForegroundWindow()
    if not foreground:
        return
    target = (target_window[1] or foreground) if target_window else foreground
    if not target_window:
        thread_id = user32.GetWindowThreadProcessId(foreground, None)
        info = GUITHREADINFO(cbSize=ctypes.sizeof(GUITHREADINFO))
        if thread_id and user32.GetGUIThreadInfo(thread_id, ctypes.byref(info)):
            target = info.hwndFocus or foreground
    result = ctypes.c_size_t()
    user32.SendMessageTimeoutW(
        target,
        WM_COPY,
        0,
        0,
        SMTO_ABORTIFHUNG,
        300,
        ctypes.byref(result),
    )


def _send_copy_shortcut() -> None:
    """Send Ctrl+C after the Read Aloud chord has been fully released."""
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
    user32.SendInput.restype = wintypes.UINT
    events = (INPUT * 4)(
        INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(VK_CONTROL, 0, 0, 0, 0)),
        INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(VK_C, 0, 0, 0, 0)),
        INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(VK_C, 0, KEYEVENTF_KEYUP, 0, 0)),
        INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0, 0)),
    )
    sent = int(user32.SendInput(len(events), events, ctypes.sizeof(INPUT)))
    if sent != len(events):
        raise TextCaptureError("Windows did not accept the local Copy shortcut")


def _open_clipboard(user32, attempts=20):
    for _attempt in range(attempts):
        if user32.OpenClipboard(None):
            return
        time.sleep(0.025)
    raise TextCaptureError("Windows clipboard is busy")


def _configure_clipboard_apis(user32, kernel32):
    user32.GetClipboardData.argtypes = [wintypes.UINT]
    user32.GetClipboardData.restype = ctypes.c_void_p
    user32.SetClipboardData.argtypes = [wintypes.UINT, ctypes.c_void_p]
    user32.SetClipboardData.restype = ctypes.c_void_p
    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = ctypes.c_void_p
    kernel32.GlobalSize.argtypes = [ctypes.c_void_p]
    kernel32.GlobalSize.restype = ctypes.c_size_t
    kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalFree.argtypes = [ctypes.c_void_p]


def _clipboard_snapshot():
    """Copy every HGLOBAL clipboard format before a temporary selection copy."""
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _configure_clipboard_apis(user32, kernel32)
    snapshot = []
    _open_clipboard(user32)
    try:
        clipboard_format = 0
        while True:
            clipboard_format = int(user32.EnumClipboardFormats(clipboard_format))
            if not clipboard_format:
                break
            handle = user32.GetClipboardData(clipboard_format)
            size = int(kernel32.GlobalSize(handle)) if handle else 0
            if not size:
                raise TextCaptureError(
                    "The clipboard contains a non-memory format, so SolomonVoice left it untouched"
                )
            pointer = kernel32.GlobalLock(handle)
            if not pointer:
                raise TextCaptureError("The existing clipboard could not be preserved safely")
            try:
                snapshot.append((clipboard_format, ctypes.string_at(pointer, size)))
            finally:
                kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()
    return snapshot


def _restore_clipboard(snapshot) -> None:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _configure_clipboard_apis(user32, kernel32)
    _open_clipboard(user32)
    try:
        if not user32.EmptyClipboard():
            raise TextCaptureError("The original clipboard could not be restored")
        for clipboard_format, data in snapshot:
            handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
            if not handle:
                raise TextCaptureError("The original clipboard could not be restored")
            pointer = kernel32.GlobalLock(handle)
            if not pointer:
                kernel32.GlobalFree(handle)
                raise TextCaptureError("The original clipboard could not be restored")
            ctypes.memmove(pointer, data, len(data))
            kernel32.GlobalUnlock(handle)
            if not user32.SetClipboardData(clipboard_format, handle):
                kernel32.GlobalFree(handle)
                raise TextCaptureError("The original clipboard could not be restored")
    finally:
        user32.CloseClipboard()


def _clipboard_unicode_text(limit) -> str:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _configure_clipboard_apis(user32, kernel32)
    _open_clipboard(user32)
    try:
        if not user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
            raise TextCaptureError("The active application did not provide selected text")
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        pointer = kernel32.GlobalLock(handle) if handle else None
        if not pointer:
            raise TextCaptureError("The selected text could not be read from Windows")
        try:
            return _clean_text(ctypes.wstring_at(pointer), limit)
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


def capture_selected_text_via_copy(limit=100_000, target_window=None) -> tuple[str, str]:
    """Read a selection through Copy, restoring every safe prior format."""
    if os.name != "nt":
        raise TextCaptureError("Selection copy fallback requires Windows")
    original = _clipboard_snapshot()
    try:

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.GetClipboardSequenceNumber.restype = wintypes.DWORD
        sequence = int(user32.GetClipboardSequenceNumber())
        _copy_focused_control(target_window)
        direct_deadline = time.monotonic() + 0.25
        clipboard_changed = False
        while time.monotonic() < direct_deadline:
            if int(user32.GetClipboardSequenceNumber()) != sequence:
                clipboard_changed = True
                break
            time.sleep(0.02)
        if not clipboard_changed:
            _send_copy_shortcut()
            deadline = time.monotonic() + 1.0
            while time.monotonic() < deadline:
                if int(user32.GetClipboardSequenceNumber()) != sequence:
                    clipboard_changed = True
                    break
                time.sleep(0.02)
        if not clipboard_changed:
            raise TextCaptureError("The active application did not copy a text selection")

        selected = _clipboard_unicode_text(limit)
        if not selected:
            raise TextCaptureError("No selected text was copied")
        return selected, "selection"
    finally:
        _restore_clipboard(original)


def _clean_text(value: str, limit: int) -> str:
    text = str(value or "").replace("\x00", "")
    lines = [" ".join(line.split()) for line in text.splitlines()]
    text = "\n".join(line for line in lines if line).strip()
    return text[:limit]


def _text_pattern(element, UIA):
    """Return an element's TextPattern, or None when it does not expose one."""
    try:
        unknown = element.GetCurrentPattern(UIA.UIA_TextPatternId)
        if unknown is None:
            return None
        return unknown.QueryInterface(UIA.IUIAutomationTextPattern)
    except Exception:
        return None


def _capture_from_automation(automation, UIA, read_full_document, limit):
    """Find selection from the focus outward, then optionally read its document."""
    element = automation.GetFocusedElement()
    if element is None:
        raise TextCaptureError("No focused text control was found")

    patterns = []
    walker = getattr(automation, "ControlViewWalker", None)
    for _depth in range(12):
        pattern = _text_pattern(element, UIA)
        if pattern is not None:
            patterns.append(pattern)
            try:
                selection = pattern.GetSelection()
                selected_parts = []
                for index in range(selection.Length):
                    text_range = selection.GetElement(index)
                    part = _clean_text(text_range.GetText(-1), limit)
                    if part:
                        selected_parts.append(part)
                selected = "\n".join(selected_parts).strip()
                if selected:
                    return selected[:limit], "selection"
            except Exception:
                pass

        if walker is None:
            break
        try:
            parent = walker.GetParentElement(element)
        except Exception:
            break
        if parent is None:
            break
        element = parent

    if read_full_document:
        # The outermost text provider usually represents the complete editor or
        # browser document rather than a focused leaf control.
        for pattern in reversed(patterns):
            try:
                document = _clean_text(pattern.DocumentRange.GetText(-1), limit)
            except Exception:
                continue
            if document:
                return document, "document"
    if patterns:
        raise TextCaptureError("Highlight text first, or enable full-document reading in Settings")
    raise TextCaptureError("The focused application does not expose readable text through Windows accessibility")


def capture_accessible_text(read_full_document=True, limit=100_000, target_window=None) -> tuple[str, str]:
    """Return (text, source) from the focused Windows accessibility element."""
    if os.name != "nt":
        raise TextCaptureError("Read Aloud requires Windows UI Automation")
    comtypes_module = None
    com_initialized = False
    try:
        # Keep generated COM wrappers with SolomonVoice's other per-user data.
        # This avoids depending on whether the Python installation itself is writable.
        cache_root = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "SolomonVoice" / "comtypes-cache"
        cache_root.mkdir(parents=True, exist_ok=True)
        previous_appdata = os.environ.get("APPDATA")
        try:
            os.environ["APPDATA"] = str(cache_root)
            import comtypes
            import comtypes.client
            comtypes_module = comtypes
        finally:
            if previous_appdata is None:
                os.environ.pop("APPDATA", None)
            else:
                os.environ["APPDATA"] = previous_appdata

        # Read Aloud runs on a fresh worker each time. COM initialization is
        # thread-local, so every invocation must initialize its own worker.
        comtypes_module.CoInitialize()
        com_initialized = True
        typelib = Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32" / "UIAutomationCore.dll"
        comtypes.client.GetModule(str(typelib))
        from comtypes.gen import UIAutomationClient as UIA

        automation = comtypes.client.CreateObject(UIA.CUIAutomation, interface=UIA.IUIAutomation)
        try:
            return _capture_from_automation(automation, UIA, False, limit)
        except TextCaptureError as selection_error:
            try:
                return capture_selected_text_via_copy(limit, target_window)
            except TextCaptureError as copy_error:
                if read_full_document:
                    return _capture_from_automation(automation, UIA, True, limit)
                raise TextCaptureError(f"{selection_error}. {copy_error}") from copy_error
    except TextCaptureError:
        raise
    except Exception as exc:
        raise TextCaptureError(
            "The active application does not expose readable text through Windows accessibility"
        ) from exc
    finally:
        if com_initialized and comtypes_module is not None:
            try:
                comtypes_module.CoUninitialize()
            except Exception:
                pass
