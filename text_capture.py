"""Read selected or document text through Windows UI Automation without the clipboard."""

from __future__ import annotations

import os
from pathlib import Path


class TextCaptureError(RuntimeError):
    pass


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


def capture_accessible_text(read_full_document=True, limit=100_000) -> tuple[str, str]:
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
        return _capture_from_automation(automation, UIA, read_full_document, limit)
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
