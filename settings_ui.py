"""Native settings window for microphone, shortcut, and desktop preferences."""

from __future__ import annotations

import copy
import ctypes
import tkinter as tk
from tkinter import messagebox, ttk

import numpy as np
import sounddevice as sd
from PIL import Image, ImageDraw, ImageTk

from audio_devices import capture_sample_rate, input_microphones, selected_microphone
from hotkey import modifier_mask, virtual_key
from listener_v2 import State
from startup import set_start_with_windows, starts_with_windows


SUPPORTED_KEYS = (
    ["space"]
    + [chr(code) for code in range(ord("a"), ord("z") + 1)]
    + [str(number) for number in range(10)]
    + [f"f{number}" for number in range(1, 25)]
    + ["tab", "insert", "delete", "home", "end", "page_up", "page_down", "up", "down", "left", "right"]
)

BG = "#07111F"
SURFACE = "#0E1B2E"
SURFACE_HOVER = "#172A43"
INPUT = "#091626"
BORDER = "#233A57"
TEXT = "#F3F7FC"
TEXT_SOFT = "#C7D5E7"
MUTED = "#89A0BB"
TEAL = "#28D7C3"
TEAL_HOVER = "#52E5D4"
RED = "#FB5D76"


class SettingsWindow:
    """Modal-by-convention settings surface that never owns global hooks."""

    def __init__(self, parent, config, listener, was_paused=False, on_saved=None, on_closed=None):
        self.parent = parent
        self.config = config
        self.listener = listener
        self.on_saved = on_saved or (lambda: None)
        self.on_closed = on_closed or (lambda: None)
        self.original = copy.deepcopy(config.data)
        self.was_paused = bool(was_paused)
        self._closed = False
        self._test_stream = None
        self._test_level = 0.0
        self._capture_binding = None
        self.status_var = tk.StringVar(master=parent, value="Changes are saved only on this Windows account.")

        if listener.state != State.PAUSED:
            raise RuntimeError("SolomonVoice could not safely pause before opening Settings")

        self.window = tk.Toplevel(parent)
        self.window.title("SolomonVoice Settings")
        self.window.geometry("780x850")
        self.window.minsize(740, 800)
        self.window.configure(bg=BG)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.after(40, self._update_meter)
        self._configure_style()
        self._apply_window_branding()
        self._build()
        self.window.update_idletasks()
        x = max(20, (self.window.winfo_screenwidth() - 780) // 2)
        y = max(20, (self.window.winfo_screenheight() - 850) // 2)
        self.window.geometry(f"780x850+{x}+{y}")
        self.window.deiconify()
        self.window.lift()
        self.window.focus_force()

    def _configure_style(self):
        style = ttk.Style(self.window)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("SV.TFrame", background=BG)
        style.configure("Card.TFrame", background=SURFACE)
        style.configure("SV.TLabel", background=BG, foreground=TEXT_SOFT, font=("Segoe UI", 10))
        style.configure("Header.TLabel", background=BG, foreground=TEAL, font=("Segoe UI Semibold", 9))
        style.configure("Muted.TLabel", background=SURFACE, foreground=MUTED, font=("Segoe UI", 9))
        style.configure("Card.TLabel", background=SURFACE, foreground=TEXT_SOFT, font=("Segoe UI", 10))
        style.configure("Section.TLabel", background=SURFACE, foreground=TEXT, font=("Segoe UI Semibold", 11))
        style.configure("Title.TLabel", background=BG, foreground=TEXT, font=("Segoe UI Semibold", 24))
        style.configure(
            "Accent.TButton", background=TEAL, foreground=BG, bordercolor=TEAL,
            focuscolor=TEAL, relief="flat", font=("Segoe UI Semibold", 10), padding=(18, 10),
        )
        style.map(
            "Accent.TButton",
            background=[("pressed", "#18B7A6"), ("active", TEAL_HOVER), ("disabled", "#345D61")],
            foreground=[("disabled", "#91A7A7"), ("!disabled", BG)],
            bordercolor=[("focus", TEAL_HOVER), ("!focus", TEAL)],
        )
        style.configure(
            "SV.TButton", background=SURFACE_HOVER, foreground=TEXT, bordercolor=BORDER,
            focuscolor=BORDER, relief="flat", font=("Segoe UI Semibold", 9), padding=(14, 9),
        )
        style.map(
            "SV.TButton",
            background=[("pressed", INPUT), ("active", "#203855"), ("disabled", "#132238")],
            foreground=[("disabled", "#60748D"), ("!disabled", TEXT)],
            bordercolor=[("focus", TEAL), ("active", "#365474"), ("!focus", BORDER)],
        )
        style.configure(
            "SV.TCombobox", fieldbackground=INPUT, background=SURFACE_HOVER, foreground=TEXT,
            arrowcolor=TEXT_SOFT, bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER,
            insertcolor=TEXT, selectbackground=TEAL, selectforeground=BG, padding=7,
        )
        style.map(
            "SV.TCombobox",
            fieldbackground=[("readonly", INPUT), ("focus", INPUT), ("active", INPUT)],
            foreground=[("readonly", TEXT), ("disabled", MUTED)],
            background=[("pressed", "#203855"), ("active", "#203855"), ("readonly", SURFACE_HOVER)],
            arrowcolor=[("active", TEAL), ("!active", TEXT_SOFT)],
            bordercolor=[("focus", TEAL), ("active", "#365474"), ("!focus", BORDER)],
        )
        style.configure(
            "Mic.Horizontal.TProgressbar", troughcolor=INPUT, background=TEAL,
            lightcolor=TEAL, darkcolor=TEAL, bordercolor=INPUT, thickness=7,
        )
        self.window.option_add("*TCombobox*Listbox.background", SURFACE)
        self.window.option_add("*TCombobox*Listbox.foreground", TEXT)
        self.window.option_add("*TCombobox*Listbox.selectBackground", TEAL)
        self.window.option_add("*TCombobox*Listbox.selectForeground", BG)
        self.window.option_add("*TCombobox*Listbox.font", ("Segoe UI", 9))

    def _apply_window_branding(self):
        image = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.ellipse((1, 1, 30, 30), fill=SURFACE, outline=TEAL, width=2)
        draw.rounded_rectangle((12, 6, 20, 19), radius=4, fill=TEAL)
        draw.arc((8, 11, 24, 25), 0, 180, fill=TEXT, width=2)
        draw.line((16, 24, 16, 27), fill=TEXT, width=2)
        self._window_icon = ImageTk.PhotoImage(image)
        self.window.iconphoto(True, self._window_icon)
        self.window.update_idletasks()
        try:
            hwnd = ctypes.windll.user32.GetParent(self.window.winfo_id()) or self.window.winfo_id()
            enabled = ctypes.c_int(1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(enabled), ctypes.sizeof(enabled))
        except Exception:
            pass

    def _build(self):
        shell = ttk.Frame(self.window, style="SV.TFrame", padding=(30, 22))
        shell.pack(fill="both", expand=True)

        header = tk.Frame(shell, bg=BG)
        header.pack(fill="x", pady=(0, 18))
        logo = tk.Canvas(header, width=54, height=54, bg=BG, highlightthickness=0)
        logo.pack(side="left", padx=(0, 14))
        logo.create_oval(2, 2, 52, 52, fill=SURFACE, outline=BORDER, width=1)
        logo.create_oval(21, 12, 33, 28, fill=TEAL, outline="")
        logo.create_rectangle(21, 20, 33, 31, fill=TEAL, outline="")
        logo.create_arc(15, 19, 39, 41, start=0, extent=180, style="arc", outline=TEXT, width=2)
        logo.create_line(27, 40, 27, 45, fill=TEXT, width=2)
        logo.create_line(21, 45, 33, 45, fill=TEXT, width=2)
        heading = tk.Frame(header, bg=BG)
        heading.pack(side="left", fill="both", expand=True)
        ttk.Label(heading, text="SOLOMON VOICE  •  OFFLINE", style="Header.TLabel").pack(anchor="w")
        ttk.Label(heading, text="Settings", style="Title.TLabel").pack(anchor="w", pady=(1, 0))
        tk.Label(
            header, text="●  LISTENING PAUSED", bg=SURFACE, fg=TEAL,
            font=("Segoe UI Semibold", 8), padx=12, pady=7,
        ).pack(side="right", anchor="n", pady=(7, 0))
        ttk.Label(
            shell,
            text="Choose how SolomonVoice listens, responds, and appears. Your keyboard is fully released while this window is open.",
            style="SV.TLabel",
        ).pack(anchor="w", pady=(0, 16))

        self._build_microphone(shell)
        self._build_shortcut(shell)
        self._build_behavior(shell)

        footer_rule = tk.Frame(shell, bg=BORDER, height=1)
        footer_rule.pack(fill="x", pady=(8, 14))
        ttk.Label(shell, textvariable=self.status_var, style="SV.TLabel").pack(anchor="w", pady=(0, 10))
        buttons = ttk.Frame(shell, style="SV.TFrame")
        buttons.pack(fill="x")
        self.cancel_button = ttk.Button(buttons, text="Cancel", command=self.close, style="SV.TButton")
        self.cancel_button.pack(side="right")
        self.apply_button = ttk.Button(buttons, text="Apply changes", command=self.apply, style="Accent.TButton")
        self.apply_button.pack(side="right", padx=(0, 10))
        self.defaults_button = ttk.Button(buttons, text="Restore defaults", command=self.restore_defaults, style="SV.TButton")
        self.defaults_button.pack(side="left")

    def _card(self, parent):
        border = tk.Frame(parent, bg=BORDER, padx=1, pady=1)
        border.pack(fill="x", pady=(0, 11))
        card = ttk.Frame(border, style="Card.TFrame", padding=(18, 14))
        card.pack(fill="both", expand=True)
        return card

    def _toggle_chip(self, parent, text, variable, width=None):
        widget = tk.Checkbutton(
            parent,
            text=text,
            variable=variable,
            indicatoron=False,
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground=BORDER,
            highlightcolor=TEAL,
            font=("Segoe UI Semibold", 9),
            padx=11,
            pady=6,
            cursor="hand2",
            anchor="w",
            width=width or 0,
        )

        def refresh(*_args):
            selected = bool(variable.get())
            widget.configure(
                bg=TEAL if selected else INPUT,
                fg=BG if selected else TEXT_SOFT,
                activebackground=TEAL_HOVER if selected else SURFACE_HOVER,
                activeforeground=BG if selected else TEXT,
                selectcolor=TEAL if selected else INPUT,
            )

        variable.trace_add("write", refresh)
        refresh()
        return widget

    def _radio_chip(self, parent, text, variable, value):
        widget = tk.Radiobutton(
            parent,
            text=text,
            variable=variable,
            value=value,
            indicatoron=False,
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground=BORDER,
            highlightcolor=TEAL,
            font=("Segoe UI Semibold", 9),
            padx=13,
            pady=7,
            cursor="hand2",
        )

        def refresh(*_args):
            selected = variable.get() == value
            widget.configure(
                bg=TEAL if selected else INPUT,
                fg=BG if selected else TEXT_SOFT,
                activebackground=TEAL_HOVER if selected else SURFACE_HOVER,
                activeforeground=BG if selected else TEXT,
                selectcolor=TEAL if selected else INPUT,
            )

        variable.trace_add("write", refresh)
        refresh()
        return widget

    def _build_microphone(self, parent):
        card = self._card(parent)
        ttk.Label(card, text="Microphone", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(card, text="Choose the input SolomonVoice uses while dictating.", style="Muted.TLabel").grid(
            row=1, column=0, columnspan=3, sticky="w", pady=(2, 10)
        )
        try:
            self.microphones = input_microphones()
            current_default = next((item for item in self.microphones if item.is_default), None)
            default_name = current_default.name if current_default else "unavailable"
            self.default_label = f"Windows default  —  {default_name}"
            labels = [self.default_label] + [item.label for item in self.microphones]
        except Exception as exc:
            self.microphones = []
            self.default_label = "Windows default"
            labels = [self.default_label]
            self.status_var.set(f"Microphone discovery failed: {exc}")
        current = selected_microphone(self.config.get("audio.device"), self.microphones)
        selected_label = self.default_label if self.config.get("audio.device") is None else (
            current.label if current else self.default_label
        )
        self.mic_var = tk.StringVar(value=selected_label)
        self.mic_combo = ttk.Combobox(
            card, textvariable=self.mic_var, values=labels, state="readonly", width=66, style="SV.TCombobox"
        )
        self.mic_combo.grid(row=2, column=0, columnspan=2, sticky="ew")
        self.test_button = ttk.Button(card, text="Test microphone", command=self.toggle_microphone_test, style="SV.TButton")
        self.test_button.grid(row=2, column=2, padx=(10, 0))
        self.meter = ttk.Progressbar(card, maximum=100, style="Mic.Horizontal.TProgressbar")
        self.meter.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        self.mic_status = tk.StringVar(value="Select a microphone, then test your speaking level.")
        ttk.Label(card, textvariable=self.mic_status, style="Muted.TLabel").grid(
            row=4, column=0, columnspan=3, sticky="w", pady=(5, 0)
        )
        card.columnconfigure(0, weight=1)

    def _build_shortcut(self, parent):
        card = self._card(parent)
        ttk.Label(card, text="Dictation shortcut", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(card, text="Select modifiers and a key, or capture the combination directly.", style="Muted.TLabel").grid(
            row=1, column=0, columnspan=6, sticky="w", pady=(2, 10)
        )
        configured = {item.lower() for item in self.config["shortcut"]["modifiers"]}
        self.ctrl_var = tk.BooleanVar(value=bool(configured & {"ctrl", "control"}))
        self.alt_var = tk.BooleanVar(value="alt" in configured)
        self.shift_var = tk.BooleanVar(value="shift" in configured)
        self.win_var = tk.BooleanVar(value=bool(configured & {"win", "windows"}))
        for column, (text, variable) in enumerate(
            (("Ctrl", self.ctrl_var), ("Alt", self.alt_var), ("Shift", self.shift_var), ("Win", self.win_var))
        ):
            self._toggle_chip(card, text, variable).grid(row=2, column=column, sticky="w", padx=(0, 7))
        self.key_var = tk.StringVar(value=self.config["shortcut"]["key"].lower())
        ttk.Combobox(
            card, textvariable=self.key_var, values=SUPPORTED_KEYS, state="readonly", width=13, style="SV.TCombobox"
        ).grid(
            row=2, column=4, padx=(6, 10)
        )
        self.capture_button = ttk.Button(card, text="Record shortcut", command=self.begin_shortcut_capture, style="SV.TButton")
        self.capture_button.grid(row=2, column=5, sticky="e")
        card.columnconfigure(5, weight=1)

    def _build_behavior(self, parent):
        card = self._card(parent)
        ttk.Label(card, text="Behavior & feedback", style="Section.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(card, text="Recording mode", style="Muted.TLabel").grid(row=1, column=0, columnspan=2, sticky="w", pady=(7, 5))
        self.mode_var = tk.StringVar(value=self.config.get("behavior.recording_mode", "hold"))
        mode_row = tk.Frame(card, bg=SURFACE)
        mode_row.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        self._radio_chip(mode_row, "Hold shortcut", self.mode_var, "hold").pack(side="left", padx=(0, 8))
        self._radio_chip(mode_row, "Press once to start • press again to stop", self.mode_var, "toggle").pack(side="left")
        self.escape_var = tk.BooleanVar(value=self.config.get("behavior.escape_to_cancel", True))
        try:
            startup_enabled = starts_with_windows()
        except Exception:
            startup_enabled = self.config.get("behavior.start_with_windows", False)
        self.original_startup = bool(startup_enabled)
        self.startup_var = tk.BooleanVar(value=startup_enabled)
        self.visual_var = tk.BooleanVar(value=self.config.get("visual.enabled", True))
        self.motion_var = tk.BooleanVar(value=self.config.get("visual.reduced_motion", False))
        self.sound_var = tk.BooleanVar(value=self.config.get("feedback.sound_enabled", True))
        checks = (
            ("Escape cancels recording", self.escape_var),
            ("Launch at Windows sign-in", self.startup_var),
            ("Show waveform overlay", self.visual_var),
            ("Reduce animation", self.motion_var),
            ("Play feedback sounds", self.sound_var),
        )
        options = tk.Frame(card, bg=SURFACE)
        options.grid(row=3, column=0, columnspan=2, sticky="ew")
        for index, (text, variable) in enumerate(checks):
            column = index % 3
            self._toggle_chip(options, text, variable, width=22).grid(
                row=index // 3, column=column, sticky="ew",
                padx=(0 if column == 0 else 4, 0 if column == 2 else 4), pady=3
            )
        options.columnconfigure(0, weight=1)
        options.columnconfigure(1, weight=1)
        options.columnconfigure(2, weight=1)
        position_row = tk.Frame(card, bg=SURFACE)
        position_row.grid(row=4, column=0, columnspan=2, sticky="w", pady=(8, 0))
        tk.Label(position_row, text="Overlay position", bg=SURFACE, fg=MUTED, font=("Segoe UI", 9)).pack(side="left", padx=(0, 10))
        self.position_var = tk.StringVar(value=self.config.get("visual.position", "bottom"))
        ttk.Combobox(
            position_row, textvariable=self.position_var, values=("bottom", "top"),
            state="readonly", width=11, style="SV.TCombobox",
        ).pack(side="left")
        card.columnconfigure(0, weight=1)
        card.columnconfigure(1, weight=1)

    def _selected_identity(self):
        if self.mic_var.get() == self.default_label:
            return None
        microphone = next((item for item in self.microphones if item.label == self.mic_var.get()), None)
        if microphone is None:
            raise RuntimeError("Select an available microphone")
        return microphone.identity

    def toggle_microphone_test(self):
        if self._test_stream is not None:
            self._stop_microphone_test()
            return
        try:
            selection = self._selected_identity()
            microphone = selected_microphone(selection, self.microphones)
            device = None if selection is None else microphone.index
            sample_rate = capture_sample_rate(
                selection,
                self.config.get("audio.sample_rate", 16000),
                self.microphones,
            )
            stream = sd.InputStream(
                channels=1,
                samplerate=sample_rate,
                device=device,
                dtype="float32",
                callback=self._test_callback,
            )
            self._test_stream = stream
            stream.start()
            self.test_button.configure(text="Stop test")
            self.mic_status.set("Speak normally — the meter should move without clipping.")
        except Exception as exc:
            cleanup_ok = self._stop_microphone_test()
            suffix = "" if cleanup_ok else "\n\nThe test stream could not be released; exit SolomonVoice before using another microphone."
            messagebox.showerror("Microphone test", f"Could not open that microphone.\n\n{exc}{suffix}", parent=self.window)

    def _test_callback(self, indata, _frames, _time_info, _status):
        rms = float(np.sqrt(np.mean(np.square(indata, dtype=np.float64))))
        self._test_level = min(1.0, rms * 18.0)

    def _update_meter(self):
        if self._closed:
            return
        current = float(self.meter["value"]) / 100.0
        current += (self._test_level - current) * 0.35
        if self._test_stream is None:
            self._test_level *= 0.65
        self.meter["value"] = int(max(0.0, min(1.0, current)) * 100)
        self.window.after(40, self._update_meter)

    def _stop_microphone_test(self):
        stream = self._test_stream
        if stream is not None:
            try:
                stream.stop()
            except Exception:
                try:
                    stream.abort()
                except Exception:
                    pass
            try:
                stream.close()
            except Exception as exc:
                self.mic_status.set(f"Could not release microphone test: {exc}")
                return False
            self._test_stream = None
        self._test_level = 0.0
        self.test_button.configure(text="Test microphone")
        self.mic_status.set("Microphone test stopped.")
        return True

    def begin_shortcut_capture(self):
        self.capture_button.configure(text="Press shortcut now…", state="disabled")
        self.window.focus_force()
        self._capture_binding = self.window.bind("<KeyPress>", self._capture_shortcut, add="+")

    def _capture_shortcut(self, event):
        keysym = str(event.keysym).lower()
        if keysym in {"control_l", "control_r", "alt_l", "alt_r", "shift_l", "shift_r", "win_l", "win_r", "super_l", "super_r"}:
            return "break"
        key_map = {
            "prior": "page_up", "next": "page_down", "return": "enter",
            "escape": "escape", "space": "space",
        }
        key = key_map.get(keysym, keysym)
        if key not in SUPPORTED_KEYS:
            self.status_var.set(f"{event.keysym} is not supported as a dictation shortcut.")
            self._end_shortcut_capture()
            return "break"
        state = int(event.state)
        self.ctrl_var.set(bool(state & 0x0004))
        self.shift_var.set(bool(state & 0x0001))
        self.alt_var.set(bool(state & 0x0008 or state & 0x20000))
        self.win_var.set(bool(state & 0x0040))
        self.key_var.set(key)
        self.status_var.set(f"Captured {self._shortcut_display()} — Apply to test it for conflicts.")
        self._end_shortcut_capture()
        return "break"

    def _end_shortcut_capture(self):
        if self._capture_binding is not None:
            self.window.unbind("<KeyPress>", self._capture_binding)
            self._capture_binding = None
        self.capture_button.configure(text="Record shortcut", state="normal")

    def _shortcut(self):
        modifiers = []
        if self.ctrl_var.get():
            modifiers.append("ctrl")
        if self.alt_var.get():
            modifiers.append("alt")
        if self.shift_var.get():
            modifiers.append("shift")
        if self.win_var.get():
            modifiers.append("win")
        return self.key_var.get().lower(), modifiers

    def _shortcut_display(self):
        key, modifiers = self._shortcut()
        return "+".join([item.title() for item in modifiers] + [key.title()])

    def apply(self):
        if not self._stop_microphone_test():
            messagebox.showerror(
                "Microphone still in use",
                "The microphone test could not be closed safely. Exit SolomonVoice to release it.",
                parent=self.window,
            )
            return
        key, modifiers = self._shortcut()
        old_hotkey = self.listener.hotkey
        old_startup = self.original_startup
        try:
            virtual_key(key)
            modifier_mask(modifiers)
            if not modifiers and key not in {f"f{number}" for number in range(13, 25)}:
                raise ValueError("Use Ctrl, Alt, or Shift with this key so normal typing is not blocked.")

            candidate = copy.deepcopy(self.original)
            candidate["shortcut"] = {"key": key, "modifiers": modifiers}
            candidate["audio"]["device"] = self._selected_identity()
            candidate["behavior"]["recording_mode"] = self.mode_var.get()
            candidate["behavior"]["escape_to_cancel"] = bool(self.escape_var.get())
            candidate["behavior"]["start_with_windows"] = bool(self.startup_var.get())
            candidate["visual"]["enabled"] = bool(self.visual_var.get())
            candidate["visual"]["position"] = self.position_var.get()
            candidate["visual"]["reduced_motion"] = bool(self.motion_var.get())
            candidate["feedback"]["sound_enabled"] = bool(self.sound_var.get())

            # Validate the whole snapshot first, then probe the exact Windows
            # shortcut before any persisted setting is changed.
            candidate = self.config.validated(candidate)
            self.listener.configure_shortcut(key, modifiers)
            set_start_with_windows(candidate["behavior"]["start_with_windows"])
            self.config.replace(candidate)
            self.config.save_user()
            self.listener.feedback.sound_enabled = candidate["feedback"]["sound_enabled"]
        except Exception as exc:
            self.config.replace(self.original)
            self.listener.hotkey = old_hotkey
            rollback_errors = []
            try:
                set_start_with_windows(old_startup)
            except Exception as rollback_exc:
                rollback_errors.append(f"Windows startup rollback failed: {rollback_exc}")
            # A failed shortcut teardown is retained by ListenerV2. Pausing
            # retries that cleanup and prevents the old shortcut from resuming
            # until Windows confirms every probe was released.
            self.listener.pause()
            detail = str(exc)
            if rollback_errors:
                detail += "\n\n" + "\n".join(rollback_errors)
            messagebox.showerror("Could not apply settings", detail, parent=self.window)
            self.status_var.set("The change was not committed. Review the error and try again.")
            return
        self.original = copy.deepcopy(self.config.data)
        self.original_startup = bool(self.startup_var.get())
        try:
            self.on_saved()
        except Exception as exc:
            messagebox.showwarning(
                "Settings saved",
                f"Your settings were saved, but the display could not refresh immediately.\n\n{exc}",
                parent=self.window,
            )
        self._finish()

    def restore_defaults(self):
        defaults = self.config.base_data
        shortcut = defaults["shortcut"]
        configured = {item.lower() for item in shortcut["modifiers"]}
        self.ctrl_var.set(bool(configured & {"ctrl", "control"}))
        self.alt_var.set("alt" in configured)
        self.shift_var.set("shift" in configured)
        self.win_var.set(bool(configured & {"win", "windows"}))
        self.key_var.set(shortcut["key"])
        self.mic_var.set(self.default_label)
        self.mode_var.set(defaults["behavior"].get("recording_mode", "hold"))
        self.escape_var.set(defaults["behavior"].get("escape_to_cancel", True))
        self.startup_var.set(defaults["behavior"].get("start_with_windows", False))
        self.visual_var.set(defaults["visual"].get("enabled", True))
        self.position_var.set(defaults["visual"].get("position", "bottom"))
        self.motion_var.set(defaults["visual"].get("reduced_motion", False))
        self.sound_var.set(defaults["feedback"].get("sound_enabled", True))
        self.status_var.set("Product defaults loaded. Click Apply changes to save them.")

    def close(self):
        if not self._stop_microphone_test():
            messagebox.showerror(
                "Microphone still in use",
                "The microphone test could not be closed safely. Exit SolomonVoice to release it.",
                parent=self.window,
            )
            return
        self.config.replace(self.original)
        self._finish()

    def shutdown(self):
        """Close during app exit without resuming the listener."""
        if self._closed:
            return
        try:
            self._stop_microphone_test()
        except Exception:
            pass
        self._closed = True
        self._end_shortcut_capture()
        self.window.destroy()

    def _finish(self):
        if self._closed:
            return
        self._closed = True
        self._end_shortcut_capture()
        self.window.destroy()
        if not self.was_paused:
            self.listener.resume()
        self.on_closed()
