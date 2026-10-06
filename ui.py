"""System tray and passive recording overlay for SolomonVoice."""

from __future__ import annotations

import ctypes
import math
import queue
import threading
import time
import tkinter as tk
from ctypes import wintypes

import pystray
from PIL import Image, ImageDraw


COLORS = {
    "starting": "#94A3B8",
    "ready": "#19C6B3",
    "recording": "#FB4B6B",
    "transcribing": "#F6B84A",
    "paused": "#7C8799",
    "error": "#FF5364",
    "stopped": "#596273",
}

GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_LAYERED = 0x00080000
WS_EX_NOACTIVATE = 0x08000000
SW_SHOWNOACTIVATE = 4
SPI_GETWORKAREA = 0x0030
MONITOR_DEFAULTTONEAREST = 2
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040


class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
    ]


def tray_image(state="ready", size=64):
    """Render a crisp stateful microphone mark suitable for small tray sizes."""
    color = COLORS.get(state, COLORS["ready"])
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((3, 3, size - 4, size - 4), fill="#101827", outline="#27364D", width=2)
    draw.rounded_rectangle((25, 12, 39, 38), radius=7, fill=color)
    draw.arc((18, 21, 46, 48), 0, 180, fill="#E9F2FF", width=4)
    draw.line((32, 46, 32, 53), fill="#E9F2FF", width=4)
    draw.line((24, 53, 40, 53), fill="#E9F2FF", width=4)
    if state == "paused":
        draw.line((14, 49, 49, 14), fill="#F8FAFC", width=6)
    elif state == "recording":
        draw.ellipse((45, 7, 58, 20), fill="#FF355E", outline="#FFFFFF", width=2)
    elif state == "error":
        draw.polygon(((50, 7), (61, 27), (39, 27)), fill="#FFCF4A")
        draw.line((50, 13, 50, 20), fill="#101827", width=2)
        draw.point((50, 23), fill="#101827")
    return image


class DesktopUI:
    """Own the Tk event loop, non-activating overlay, and tray icon."""

    def __init__(self, config):
        self.config = config
        self.root = tk.Tk()
        self.root.withdraw()
        self.listener = None
        self.state = "starting"
        self.detail = None
        self.level = 0.0
        self.display_level = 0.0
        self.started_at = 0.0
        self._events = queue.SimpleQueue()
        self._closing = False
        self._tray = None
        self._tray_thread = None
        self._bars = []
        self._build_overlay()
        self.root.after(25, self._poll)

    def bind_listener(self, listener) -> None:
        self.listener = listener

    def start_tray(self) -> None:
        menu = pystray.Menu(
            pystray.MenuItem(lambda _item: self._status_text(), None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                lambda _item: "Resume listening" if self.state == "paused" else "Pause listening",
                self._request_toggle,
                default=True,
            ),
            pystray.MenuItem("Exit SolomonVoice (releases hotkey)", self._request_exit),
        )
        self._tray = pystray.Icon(
            "SolomonVoice",
            tray_image("starting"),
            "SolomonVoice · Starting",
            menu,
        )
        self._tray_thread = threading.Thread(
            target=self._tray.run,
            name="SolomonVoiceTray",
            daemon=True,
        )
        self._tray_thread.start()

    def run(self) -> None:
        self.root.mainloop()

    def notify_state(self, state, detail=None) -> None:
        self._events.put(("state", getattr(state, "value", str(state)), detail))

    def notify_level(self, level) -> None:
        self._events.put(("level", float(level)))

    def shutdown(self) -> None:
        if self._closing:
            return
        self._closing = True
        if self.listener:
            self.listener.stop()
        if self._tray:
            self._tray.stop()
        if self._tray_thread and self._tray_thread is not threading.current_thread():
            self._tray_thread.join(timeout=2)
        self.overlay.withdraw()
        self.root.quit()
        self.root.destroy()

    def _build_overlay(self) -> None:
        self.overlay = tk.Toplevel(self.root)
        self.overlay.withdraw()
        self.overlay.overrideredirect(True)
        self.overlay.attributes("-topmost", True)
        self.overlay.configure(bg="#010101")
        try:
            self.overlay.attributes("-transparentcolor", "#010101")
        except tk.TclError:
            pass

        self.width, self.height = 330, 76
        self.canvas = tk.Canvas(
            self.overlay,
            width=self.width,
            height=self.height,
            bg="#010101",
            highlightthickness=0,
        )
        self.canvas.pack()
        self._rounded_rect(1, 1, self.width - 1, self.height - 1, 22, "#101827", "#2A3A51")
        self.canvas.create_oval(18, 20, 54, 56, fill="#18263A", outline="")
        self.mic = self.canvas.create_text(36, 38, text="●", fill=COLORS["ready"], font=("Segoe UI", 18, "bold"))
        self.title = self.canvas.create_text(
            70, 25, text="Listening…", fill="#F8FAFC", anchor="w", font=("Segoe UI", 11, "bold")
        )
        self.subtitle = self.canvas.create_text(
            70, 48, text="Release Ctrl+Space to transcribe", fill="#9FB0C8", anchor="w", font=("Segoe UI", 8)
        )
        for index in range(18):
            x = 210 + index * 5
            self._bars.append(self.canvas.create_line(x, 30, x, 46, fill=COLORS["recording"], width=3))

        self.overlay.update_idletasks()
        self._apply_no_activate_style()
        self._position_overlay()

    def _rounded_rect(self, x1, y1, x2, y2, radius, fill, outline):
        self.canvas.create_rectangle(x1 + radius, y1, x2 - radius, y2, fill=fill, outline="")
        self.canvas.create_rectangle(x1, y1 + radius, x2, y2 - radius, fill=fill, outline="")
        self.canvas.create_oval(x1, y1, x1 + radius * 2, y1 + radius * 2, fill=fill, outline=outline, width=1)
        self.canvas.create_oval(x2 - radius * 2, y1, x2, y1 + radius * 2, fill=fill, outline=outline, width=1)
        self.canvas.create_oval(x1, y2 - radius * 2, x1 + radius * 2, y2, fill=fill, outline=outline, width=1)
        self.canvas.create_oval(x2 - radius * 2, y2 - radius * 2, x2, y2, fill=fill, outline=outline, width=1)

    def _apply_no_activate_style(self) -> None:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.GetParent.argtypes = [wintypes.HWND]
        user32.GetParent.restype = wintypes.HWND
        user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
        user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
        user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
        user32.SetWindowPos.argtypes = [
            wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
            ctypes.c_int, ctypes.c_int, wintypes.UINT,
        ]
        user32.SetWindowPos.restype = wintypes.BOOL
        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
        user32.MonitorFromWindow.restype = wintypes.HANDLE
        user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MONITORINFO)]
        user32.GetMonitorInfoW.restype = wintypes.BOOL
        hwnd = user32.GetParent(self.overlay.winfo_id()) or self.overlay.winfo_id()
        style = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
        ctypes.set_last_error(0)
        previous = user32.SetWindowLongPtrW(
            hwnd,
            GWL_EXSTYLE,
            style | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_TRANSPARENT | WS_EX_LAYERED,
        )
        if previous == 0 and ctypes.get_last_error():
            raise RuntimeError(
                f"Could not make the recording overlay non-activating (Windows error {ctypes.get_last_error()})"
            )
        self._user32 = user32
        self._overlay_hwnd = hwnd

    def _position_overlay(self) -> None:
        try:
            user32 = getattr(self, "_user32", ctypes.WinDLL("user32", use_last_error=True))
            foreground = user32.GetForegroundWindow()
            monitor = user32.MonitorFromWindow(foreground, MONITOR_DEFAULTTONEAREST)
            info = MONITORINFO(cbSize=ctypes.sizeof(MONITORINFO))
            if not monitor or not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
                raise OSError("Could not locate active monitor")
            rect = info.rcWork
            x = rect.left + (rect.right - rect.left - self.width) // 2
            if self.config.get("visual.position", "bottom") == "top":
                y = rect.top + 24
            else:
                y = rect.bottom - self.height - 24
        except Exception:
            x = (self.root.winfo_screenwidth() - self.width) // 2
            y = self.root.winfo_screenheight() - self.height - 72
        self.overlay.geometry(f"{self.width}x{self.height}+{x}+{y}")

    def _show_overlay(self) -> None:
        if not self.config.get("visual.enabled", True):
            return
        self._position_overlay()
        if not self._user32.SetWindowPos(
            self._overlay_hwnd,
            wintypes.HWND(-1),
            0,
            0,
            0,
            0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW,
        ):
            raise RuntimeError("Could not show the recording overlay without activating it")

    def _poll(self) -> None:
        if self._closing:
            return
        while True:
            try:
                event = self._events.get_nowait()
            except queue.Empty:
                break
            if event[0] == "state":
                self._set_state(event[1], event[2])
            elif event[0] == "level":
                self.level = event[1]
            elif event[0] == "toggle" and self.listener:
                self.listener.toggle_paused()
            elif event[0] == "exit":
                self.shutdown()
                return
        self._animate()
        self.root.after(33, self._poll)

    def _set_state(self, state, detail) -> None:
        self.state, self.detail = state, detail
        if state == "recording":
            self.started_at = time.monotonic()
            self._show_overlay()
        elif state == "transcribing":
            self._show_overlay()
        elif state == "error":
            self._show_overlay()
            self.root.after(3200, self._hide_if_error)
        else:
            self.overlay.withdraw()
        self._update_overlay_text()
        self._update_tray()

    def _update_overlay_text(self) -> None:
        color = COLORS.get(self.state, COLORS["ready"])
        title = {
            "recording": "Listening…",
            "transcribing": "Transcribing locally…",
            "error": "Couldn’t complete dictation",
        }.get(self.state, self.state.title())
        subtitle = self.detail or (
            f"Release {self.listener.hotkey_display()} to transcribe"
            if self.state == "recording" and self.listener
            else "Your audio stays on this computer"
        )
        if len(subtitle) > 46:
            subtitle = subtitle[:43] + "…"
        self.canvas.itemconfigure(self.mic, fill=color)
        self.canvas.itemconfigure(self.title, text=title)
        self.canvas.itemconfigure(self.subtitle, text=subtitle)

    def _animate(self) -> None:
        self.display_level += (self.level - self.display_level) * 0.35
        if self.state != "recording":
            self.level *= 0.8
        reduced_motion = self.config.get("visual.reduced_motion", False)
        phase = 0 if reduced_motion else time.monotonic() * (8 if self.state == "transcribing" else 4)
        color = COLORS.get(self.state, COLORS["ready"])
        for index, bar in enumerate(self._bars):
            profile = 0.35 + 0.65 * abs(math.sin(index * 0.58 + phase))
            if self.state == "recording":
                amplitude = 4 + 21 * self.display_level * profile
            elif self.state == "transcribing":
                amplitude = 4 + 9 * profile
            else:
                amplitude = 3
            x = 210 + index * 5
            self.canvas.coords(bar, x, 38 - amplitude, x, 38 + amplitude)
            self.canvas.itemconfigure(bar, fill=color)

    def _status_text(self) -> str:
        hotkey = self.listener.hotkey_display() if self.listener else ""
        labels = {
            "ready": f"Ready · {hotkey}",
            "recording": "Recording · release to stop",
            "transcribing": "Transcribing locally",
            "paused": "Paused · hotkey released",
            "error": "Attention needed",
            "starting": "Starting SolomonVoice",
        }
        return labels.get(self.state, "SolomonVoice")

    def _update_tray(self) -> None:
        if not self._tray:
            return
        self._tray.icon = tray_image(self.state)
        self._tray.title = f"SolomonVoice · {self._status_text()}"
        self._tray.update_menu()

    def _request_toggle(self, _icon, _item) -> None:
        self._events.put(("toggle",))

    def _request_exit(self, _icon, _item) -> None:
        self._events.put(("exit",))

    def _hide_if_error(self) -> None:
        if self.state == "error":
            self.overlay.withdraw()
