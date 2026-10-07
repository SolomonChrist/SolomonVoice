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


def capture_accessible_text(read_full_document=True, limit=100_000) -> tuple[str, str]:
    """Return (text, source) from the focused Windows accessibility element."""
    if os.name != "nt":
        raise TextCaptureError("Read Aloud requires Windows UI Automation")
    try:
        # Keep generated COM wrappers with SolomonVoice's other per-user data.
        # This avoids depending on whether the Python installation itself is writable.
        cache_root = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "SolomonVoice" / "comtypes-cache"
        cache_root.mkdir(parents=True, exist_ok=True)
        previous_appdata = os.environ.get("APPDATA")
        try:
            os.environ["APPDATA"] = str(cache_root)
            import comtypes.client
        finally:
            if previous_appdata is None:
                os.environ.pop("APPDATA", None)
            else:
                os.environ["APPDATA"] = previous_appdata

        typelib = Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32" / "UIAutomationCore.dll"
        comtypes.client.GetModule(str(typelib))
        from comtypes.gen import UIAutomationClient as UIA

        automation = comtypes.client.CreateObject(UIA.CUIAutomation, interface=UIA.IUIAutomation)
        element = automation.GetFocusedElement()
        if element is None:
            raise TextCaptureError("No focused text control was found")
        unknown = element.GetCurrentPattern(UIA.UIA_TextPatternId)
        pattern = unknown.QueryInterface(UIA.IUIAutomationTextPattern)

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

        if read_full_document:
            document = _clean_text(pattern.DocumentRange.GetText(-1), limit)
            if document:
                return document, "document"
        raise TextCaptureError("Highlight text first, or enable full-document reading in Settings")
    except TextCaptureError:
        raise
    except Exception as exc:
        raise TextCaptureError(
            "The active application does not expose readable text through Windows accessibility"
        ) from exc
