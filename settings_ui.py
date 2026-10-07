"""Native settings window for microphone, shortcut, and desktop preferences."""

from __future__ import annotations

import copy
import ctypes
import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import numpy as np
import sounddevice as sd
from PIL import Image, ImageDraw, ImageTk

from audio_devices import capture_sample_rate, input_microphones, selected_microphone
from hotkey import modifier_mask, virtual_key
from listener_v2 import State
from startup import set_start_with_windows, starts_with_windows
from whisper_models import (
    DEFAULT_MODEL,
    MODEL_DESCRIPTIONS,
    OFFICIAL_MODELS,
    available_model_names,
    model_path,
    resolve_model_directory,
)
from tts_models import (
    DEFAULT_TTS_MODEL,
    MAX_READ_SPEED,
    MIN_READ_SPEED,
    TTS_MODELS,
    VOICE_BY_ID,
    VOICE_BY_LABEL,
    VOICE_CHOICES,
    install_tts_model,
    model_file as tts_model_file,
    model_is_installed as tts_model_is_installed,
    resolve_tts_directory,
    voices_file,
)
from tts_reader import TTSReader


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
        self._capture_target = "dictation"
        self._model_installing = False
        self._voice_preview_reader = None
        self._voice_preview_cancel = None
        self._voice_previewing = False
        self._voice_preview_generation = 0
        self._meter_after_id = None
        self.status_var = tk.StringVar(master=parent, value="Changes are saved only on this Windows account.")

        if listener.state != State.PAUSED:
            raise RuntimeError("SolomonVoice could not safely pause before opening Settings")

        self.window = tk.Toplevel(parent)
        self.window.title("SolomonVoice Settings")
        self.window.geometry("780x850")
        self.window.minsize(740, 800)
        self.window.configure(bg=BG)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self._meter_after_id = self.window.after(40, self._update_meter)
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
            "SV.TEntry", fieldbackground=INPUT, foreground=TEXT, insertcolor=TEXT,
            bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER, padding=7,
        )
        style.map(
            "SV.TEntry",
            fieldbackground=[("disabled", "#0B1727"), ("focus", INPUT), ("!focus", INPUT)],
            foreground=[("disabled", MUTED), ("!disabled", TEXT)],
            bordercolor=[("focus", TEAL), ("!focus", BORDER)],
        )
        style.configure(
            "Mic.Horizontal.TProgressbar", troughcolor=INPUT, background=TEAL,
            lightcolor=TEAL, darkcolor=TEAL, bordercolor=INPUT, thickness=7,
        )
        style.configure(
            "SV.Vertical.TScrollbar", troughcolor=BG, background=SURFACE_HOVER,
            bordercolor=BG, lightcolor=SURFACE_HOVER, darkcolor=SURFACE_HOVER,
            arrowcolor=MUTED, relief="flat", width=11,
        )
        style.map(
            "SV.Vertical.TScrollbar",
            background=[("pressed", TEAL), ("active", "#203855"), ("!active", SURFACE_HOVER)],
            arrowcolor=[("pressed", BG), ("active", TEAL), ("!active", MUTED)],
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
            header, text="●  SHORTCUTS PAUSED", bg=SURFACE, fg=TEAL,
            font=("Segoe UI Semibold", 8), padx=12, pady=7,
        ).pack(side="right", anchor="n", pady=(7, 0))
        ttk.Label(
            shell,
            text="Dictation and Read Aloud shortcuts are disabled while Settings is open. Close this window to resume them.",
            style="SV.TLabel",
        ).pack(anchor="w", pady=(0, 16))

        footer = ttk.Frame(shell, style="SV.TFrame")
        footer.pack(side="bottom", fill="x")
        footer_rule = tk.Frame(footer, bg=BORDER, height=1)
        footer_rule.pack(fill="x", pady=(9, 12))
        ttk.Label(footer, textvariable=self.status_var, style="SV.TLabel").pack(anchor="w", pady=(0, 9))
        buttons = ttk.Frame(footer, style="SV.TFrame")
        buttons.pack(fill="x")
        cancel_text = "Cancel" if self.was_paused else "Cancel & resume"
        apply_text = "Apply changes" if self.was_paused else "Apply & resume"
        self.cancel_button = ttk.Button(buttons, text=cancel_text, command=self.close, style="SV.TButton")
        self.cancel_button.pack(side="right")
        self.apply_button = ttk.Button(buttons, text=apply_text, command=self.apply, style="Accent.TButton")
        self.apply_button.pack(side="right", padx=(0, 10))
        self.defaults_button = ttk.Button(buttons, text="Restore defaults", command=self.restore_defaults, style="SV.TButton")
        self.defaults_button.pack(side="left")

        content_host = tk.Frame(shell, bg=BG)
        content_host.pack(fill="both", expand=True)
        self.content_canvas = tk.Canvas(content_host, bg=BG, highlightthickness=0, bd=0)
        scrollbar = ttk.Scrollbar(
            content_host,
            orient="vertical",
            command=self.content_canvas.yview,
            style="SV.Vertical.TScrollbar",
        )
        self.content_canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.content_canvas.pack(side="left", fill="both", expand=True)
        content = ttk.Frame(self.content_canvas, style="SV.TFrame")
        content_window = self.content_canvas.create_window((0, 0), window=content, anchor="nw")
        content.bind(
            "<Configure>",
            lambda _event: self.content_canvas.configure(scrollregion=self.content_canvas.bbox("all")),
        )
        self.content_canvas.bind(
            "<Configure>",
            lambda event: self.content_canvas.itemconfigure(content_window, width=event.width),
        )
        self.content_canvas.bind("<Enter>", lambda _event: self.content_canvas.bind_all("<MouseWheel>", self._scroll_content))
        self.content_canvas.bind("<Leave>", lambda _event: self.content_canvas.unbind_all("<MouseWheel>"))

        self._build_model(content)
        self._build_read_aloud(content)
        self._build_microphone(content)
        self._build_shortcut(content)
        self._build_behavior(content)

    def _card(self, parent):
        border = tk.Frame(parent, bg=BORDER, padx=1, pady=1)
        border.pack(fill="x", pady=(0, 11))
        card = ttk.Frame(border, style="Card.TFrame", padding=(18, 14))
        card.pack(fill="both", expand=True)
        return card

    def _scroll_content(self, event):
        self.content_canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")

    def _build_model(self, parent):
        card = self._card(parent)
        ttk.Label(card, text="Speech model", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            card,
            text="Choose the local Whisper checkpoint used for transcription.",
            style="Muted.TLabel",
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(2, 9))

        current_model = self.config.get("whisper.model", DEFAULT_MODEL)
        current_directory = resolve_model_directory(self.config.get("whisper.model_directory"))
        self.model_var = tk.StringVar(value=current_model)
        self.model_dir_var = tk.StringVar(value=str(current_directory))
        self.model_status = tk.StringVar()
        self.model_combo = ttk.Combobox(
            card,
            textvariable=self.model_var,
            values=available_model_names(current_directory, current_model),
            state="readonly",
            width=24,
            style="SV.TCombobox",
        )
        self.model_combo.grid(row=2, column=0, sticky="ew")
        self.model_combo.bind("<<ComboboxSelected>>", lambda _event: self._update_model_status())
        self.install_model_button = ttk.Button(
            card,
            text="Install selected model",
            command=self.install_selected_model,
            style="SV.TButton",
        )
        self.install_model_button.grid(row=2, column=1, columnspan=2, sticky="e", padx=(10, 0))

        ttk.Label(card, text="Model folder", style="Muted.TLabel").grid(
            row=3, column=0, columnspan=3, sticky="w", pady=(10, 4)
        )
        self.model_dir_entry = ttk.Entry(card, textvariable=self.model_dir_var, style="SV.TEntry")
        self.model_dir_entry.grid(row=4, column=0, columnspan=2, sticky="ew")
        self.model_dir_entry.bind("<FocusOut>", lambda _event: self._model_directory_changed())
        self.model_dir_entry.bind("<Return>", lambda _event: self._model_directory_changed())
        self.browse_model_button = ttk.Button(
            card, text="Browse…", command=self.choose_model_directory, style="SV.TButton"
        )
        self.browse_model_button.grid(row=4, column=2, padx=(10, 0))
        ttk.Label(card, textvariable=self.model_status, style="Muted.TLabel").grid(
            row=5, column=0, columnspan=3, sticky="w", pady=(6, 0)
        )
        card.columnconfigure(0, weight=1)
        self._update_model_status()

    def _selected_model_directory(self):
        value = self.model_dir_var.get().strip()
        if not value:
            return resolve_model_directory(None)
        return resolve_model_directory(value)

    def _model_directory_changed(self):
        directory = self._selected_model_directory()
        self.model_dir_var.set(str(directory))
        self.model_combo.configure(values=available_model_names(directory, self.model_var.get()))
        self._update_model_status()

    def choose_model_directory(self):
        selected = filedialog.askdirectory(
            parent=self.window,
            title="Choose SolomonVoice model folder",
            initialdir=str(self._selected_model_directory()),
            mustexist=False,
        )
        if selected:
            self.model_dir_var.set(os.path.abspath(selected))
            self._model_directory_changed()

    def _update_model_status(self):
        name = self.model_var.get().strip()
        checkpoint = model_path(name, self._selected_model_directory())
        description = MODEL_DESCRIPTIONS.get(name, "Local Whisper-compatible checkpoint")
        installed = checkpoint.is_file()
        state = "Installed" if installed else "Not installed"
        self.model_status.set(f"{description}  •  {state}  •  {checkpoint.name}")
        if hasattr(self, "install_model_button"):
            can_install = name in OFFICIAL_MODELS and not installed and not self._model_installing
            if self._model_installing:
                button_text = "Installing…"
            elif installed:
                button_text = "Installed"
            elif name in OFFICIAL_MODELS:
                button_text = "Install selected model"
            else:
                button_text = "Local model only"
            self.install_model_button.configure(
                state="normal" if can_install else "disabled",
                text=button_text,
            )

    def install_selected_model(self):
        if self._model_installing:
            return
        name = self.model_var.get().strip()
        if name not in OFFICIAL_MODELS:
            messagebox.showinfo(
                "Local model",
                "Custom checkpoints cannot be downloaded automatically. Copy the compatible .pt file into the selected model folder.",
                parent=self.window,
            )
            return
        directory = self._selected_model_directory()
        self._model_installing = True
        self.status_var.set(f"Installing {name}… Keep SolomonVoice open while the download completes.")
        self.apply_button.configure(state="disabled")
        self.model_combo.configure(state="disabled")
        self.browse_model_button.configure(state="disabled")
        self._update_model_status()

        def worker():
            try:
                directory.mkdir(parents=True, exist_ok=True)
                import whisper

                loaded = whisper.load_model(name, download_root=str(directory))
                del loaded
                error = None
            except Exception as exc:
                error = exc
            try:
                self.window.after(0, lambda: self._finish_model_install(name, directory, error))
            except tk.TclError:
                pass

        threading.Thread(target=worker, name="SolomonVoiceModelInstaller", daemon=True).start()

    def _finish_model_install(self, name, directory, error):
        if self._closed:
            return
        self._model_installing = False
        self.apply_button.configure(state="normal")
        self.model_combo.configure(state="readonly")
        self.browse_model_button.configure(state="normal")
        self.model_combo.configure(values=available_model_names(directory, name))
        self._update_model_status()
        if error is not None:
            self.status_var.set(f"Could not install {name}.")
            messagebox.showerror("Model installation failed", str(error), parent=self.window)
            return
        self.status_var.set(f"{name} is installed locally. Click Apply changes to use it.")

    def _build_read_aloud(self, parent):
        card = self._card(parent)
        ttk.Label(card, text="Read Aloud", style="Section.TLabel").grid(row=0, column=0, columnspan=6, sticky="w")
        ttk.Label(
            card,
            text="Read highlighted text—or the active document—with a completely local Kokoro voice.",
            style="Muted.TLabel",
        ).grid(row=1, column=0, columnspan=6, sticky="w", pady=(2, 9))

        self.read_enabled_var = tk.BooleanVar(value=self.config.get("read_aloud.enabled", True))
        self._toggle_chip(card, "Enable Read Aloud", self.read_enabled_var).grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(0, 9)
        )

        current_model = self.config.get("read_aloud.model", DEFAULT_TTS_MODEL)
        current_directory = resolve_tts_directory(self.config.get("read_aloud.model_directory"))
        self.tts_model_var = tk.StringVar(value=current_model)
        self.tts_model_dir_var = tk.StringVar(value=str(current_directory))
        self.tts_model_status = tk.StringVar()
        ttk.Label(card, text="Voice model", style="Muted.TLabel").grid(row=3, column=0, columnspan=3, sticky="w")
        self.tts_model_combo = ttk.Combobox(
            card,
            textvariable=self.tts_model_var,
            values=tuple(TTS_MODELS),
            state="readonly",
            width=27,
            style="SV.TCombobox",
        )
        self.tts_model_combo.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(4, 0))
        self.tts_model_combo.bind("<<ComboboxSelected>>", lambda _event: self._update_tts_model_status())
        self.install_tts_button = ttk.Button(
            card, text="Install voice model", command=self.install_selected_tts_model, style="SV.TButton"
        )
        self.install_tts_button.grid(row=4, column=3, columnspan=3, sticky="e", padx=(10, 0), pady=(4, 0))

        ttk.Label(card, text="Voice model folder", style="Muted.TLabel").grid(
            row=5, column=0, columnspan=6, sticky="w", pady=(10, 4)
        )
        self.tts_model_dir_entry = ttk.Entry(card, textvariable=self.tts_model_dir_var, style="SV.TEntry")
        self.tts_model_dir_entry.grid(row=6, column=0, columnspan=5, sticky="ew")
        self.tts_model_dir_entry.bind("<FocusOut>", lambda _event: self._tts_directory_changed())
        self.tts_model_dir_entry.bind("<Return>", lambda _event: self._tts_directory_changed())
        self.browse_tts_button = ttk.Button(
            card, text="Browse…", command=self.choose_tts_directory, style="SV.TButton"
        )
        self.browse_tts_button.grid(row=6, column=5, padx=(10, 0))
        ttk.Label(card, textvariable=self.tts_model_status, style="Muted.TLabel").grid(
            row=7, column=0, columnspan=6, sticky="w", pady=(6, 10)
        )

        ttk.Label(card, text="Voice", style="Muted.TLabel").grid(row=8, column=0, columnspan=3, sticky="w")
        ttk.Label(card, text="Reading speed · clear pitch-preserving playback", style="Muted.TLabel").grid(
            row=8, column=3, columnspan=3, sticky="w"
        )
        current_voice = self.config.get("read_aloud.voice", "af_heart")
        voice_label = VOICE_BY_ID.get(current_voice, VOICE_BY_ID["af_heart"])[0]
        self.voice_var = tk.StringVar(value=voice_label)
        self.voice_combo = ttk.Combobox(
            card,
            textvariable=self.voice_var,
            values=tuple(label for label, _voice, _language in VOICE_CHOICES),
            state="readonly",
            width=30,
            style="SV.TCombobox",
        )
        self.voice_combo.grid(row=9, column=0, columnspan=2, sticky="ew", pady=(4, 0), padx=(0, 8))
        self.voice_combo.bind("<<ComboboxSelected>>", self._voice_selection_changed)
        self.preview_voice_button = ttk.Button(
            card, text="Preview voice", command=self.toggle_voice_preview, style="SV.TButton"
        )
        self.preview_voice_button.grid(row=9, column=2, sticky="ew", pady=(4, 0), padx=(0, 10))
        self.speed_var = tk.DoubleVar(value=self.config.get("read_aloud.speed", 1.0))
        speed_row = tk.Frame(card, bg=SURFACE)
        speed_row.grid(row=9, column=3, columnspan=3, sticky="ew", pady=(4, 0))
        self.speed_scale = tk.Scale(
            speed_row, from_=MIN_READ_SPEED, to=MAX_READ_SPEED, resolution=0.1, orient="horizontal",
            variable=self.speed_var, showvalue=False, bg=SURFACE, fg=TEXT,
            troughcolor=INPUT, activebackground=TEAL, highlightthickness=0,
            bd=0, sliderrelief="flat", sliderlength=16,
        )
        self.speed_scale.pack(side="left", fill="x", expand=True)
        self.speed_label = tk.Label(speed_row, bg=SURFACE, fg=TEXT_SOFT, width=5, font=("Segoe UI", 9))
        self.speed_label.pack(side="right", padx=(8, 0))
        self.speed_var.trace_add("write", lambda *_args: self.speed_label.configure(text=f"{self.speed_var.get():.2g}×"))
        self.speed_label.configure(text=f"{self.speed_var.get():.2g}×")

        self.read_full_var = tk.BooleanVar(value=self.config.get("read_aloud.read_full_document", True))
        self._toggle_chip(card, "Read full document when nothing is highlighted", self.read_full_var).grid(
            row=10, column=0, columnspan=6, sticky="ew", pady=(10, 8)
        )

        ttk.Label(card, text="Read Aloud shortcut", style="Muted.TLabel").grid(
            row=11, column=0, columnspan=6, sticky="w", pady=(2, 5)
        )
        shortcut = self.config.get("read_aloud.shortcut", {"key": "space", "modifiers": ["ctrl", "shift"]})
        configured = {item.lower() for item in shortcut["modifiers"]}
        self.read_ctrl_var = tk.BooleanVar(value=bool(configured & {"ctrl", "control"}))
        self.read_alt_var = tk.BooleanVar(value="alt" in configured)
        self.read_shift_var = tk.BooleanVar(value="shift" in configured)
        self.read_win_var = tk.BooleanVar(value=bool(configured & {"win", "windows"}))
        for column, (text, variable) in enumerate((
            ("Ctrl", self.read_ctrl_var), ("Alt", self.read_alt_var),
            ("Shift", self.read_shift_var), ("Win", self.read_win_var),
        )):
            self._toggle_chip(card, text, variable).grid(row=12, column=column, sticky="w", padx=(0, 7))
        self.read_key_var = tk.StringVar(value=shortcut["key"].lower())
        ttk.Combobox(
            card, textvariable=self.read_key_var, values=SUPPORTED_KEYS,
            state="readonly", width=12, style="SV.TCombobox",
        ).grid(row=12, column=4, padx=(6, 10))
        self.read_capture_button = ttk.Button(
            card, text="Record shortcut", command=lambda: self.begin_shortcut_capture("read"), style="SV.TButton"
        )
        self.read_capture_button.grid(row=12, column=5, sticky="e")
        card.columnconfigure(0, weight=1)
        card.columnconfigure(1, weight=1)
        card.columnconfigure(2, weight=1)
        card.columnconfigure(3, weight=1)
        card.columnconfigure(4, weight=1)
        self._update_tts_model_status()

    def _voice_selection_changed(self, _event=None):
        if self._voice_previewing:
            self._stop_voice_preview()
        self.status_var.set(f"Selected {self.voice_var.get()}. Click Preview voice to hear it.")

    def toggle_voice_preview(self):
        if self._voice_previewing:
            self._stop_voice_preview()
            self.status_var.set("Voice preview stopped.")
            return
        name = self.tts_model_var.get()
        directory = self._selected_tts_directory()
        if not tts_model_is_installed(name, directory):
            messagebox.showinfo(
                "Install voice model",
                "Install the selected voice model before previewing a voice.",
                parent=self.window,
            )
            return
        voice_label = self.voice_var.get()
        voice_id = VOICE_BY_LABEL[voice_label][0]
        self._voice_preview_generation += 1
        generation = self._voice_preview_generation
        reader = TTSReader(
            name,
            str(directory),
            voice_id,
            float(self.speed_var.get()),
            self.config.get("read_aloud.output_device"),
        )
        cancel = threading.Event()
        self._voice_preview_reader = reader
        self._voice_preview_cancel = cancel
        self._voice_previewing = True
        self.preview_voice_button.configure(text="Stop preview")
        self.status_var.set(f"Previewing {voice_label} at {self.speed_var.get():.2g}×…")

        sample = (
            "Hello. This is SolomonVoice reading completely offline. "
            "Choose the voice and speed that feel most comfortable to you."
        )

        def worker():
            try:
                reader.speak(sample, cancel)
                error = None
            except Exception as exc:
                error = exc
            try:
                self.window.after(0, lambda: self._finish_voice_preview(generation, voice_label, error))
            except tk.TclError:
                pass

        threading.Thread(target=worker, name="SolomonVoiceVoicePreview", daemon=True).start()

    def _finish_voice_preview(self, generation, voice_label, error):
        if self._closed or generation != self._voice_preview_generation:
            return
        self._voice_preview_reader = None
        self._voice_preview_cancel = None
        self._voice_previewing = False
        self.preview_voice_button.configure(text="Preview voice")
        if error:
            self.status_var.set("Voice preview failed.")
            messagebox.showerror("Voice preview failed", str(error), parent=self.window)
        else:
            self.status_var.set(f"Finished previewing {voice_label}.")

    def _stop_voice_preview(self):
        self._voice_preview_generation += 1
        reader = self._voice_preview_reader
        cancel = self._voice_preview_cancel
        self._voice_preview_reader = None
        self._voice_preview_cancel = None
        self._voice_previewing = False
        if cancel is not None:
            cancel.set()
        if reader is not None:
            reader.stop()
        if hasattr(self, "preview_voice_button"):
            self.preview_voice_button.configure(text="Preview voice")

    def _selected_tts_directory(self):
        return resolve_tts_directory(self.tts_model_dir_var.get().strip() or None)

    def _tts_directory_changed(self):
        self.tts_model_dir_var.set(str(self._selected_tts_directory()))
        self._update_tts_model_status()

    def choose_tts_directory(self):
        selected = filedialog.askdirectory(
            parent=self.window,
            title="Choose SolomonVoice voice model folder",
            initialdir=str(self._selected_tts_directory()),
            mustexist=False,
        )
        if selected:
            self.tts_model_dir_var.set(os.path.abspath(selected))
            self._tts_directory_changed()

    def _update_tts_model_status(self):
        name = self.tts_model_var.get()
        directory = self._selected_tts_directory()
        installed = tts_model_is_installed(name, directory)
        description = TTS_MODELS[name]["description"]
        state = "Installed" if installed else "Not installed"
        self.tts_model_status.set(
            f"{description}  •  {state}  •  {tts_model_file(name, directory).name} + {voices_file(directory).name}"
        )
        if hasattr(self, "install_tts_button"):
            self.install_tts_button.configure(
                state="disabled" if installed or self._model_installing else "normal",
                text="Installed" if installed else ("Installing…" if self._model_installing else "Install voice model"),
            )
        if hasattr(self, "preview_voice_button"):
            self.preview_voice_button.configure(
                state="normal" if installed and not self._model_installing else "disabled"
            )

    def install_selected_tts_model(self):
        if self._model_installing:
            return
        name = self.tts_model_var.get()
        directory = self._selected_tts_directory()
        self._model_installing = True
        self.status_var.set(f"Installing {name} and its local voice pack…")
        self.apply_button.configure(state="disabled")
        self.tts_model_combo.configure(state="disabled")
        self.browse_tts_button.configure(state="disabled")
        self._update_tts_model_status()

        def progress(filename, copied, total):
            if total:
                status = f"Installing {filename}… {copied * 100 // total}%"
            else:
                status = f"Installing {filename}… {copied // (1024 * 1024)} MB"
            try:
                self.window.after(0, lambda value=status: self.status_var.set(value))
            except tk.TclError:
                pass

        def worker():
            try:
                install_tts_model(name, directory, progress)
                error = None
            except Exception as exc:
                error = exc
            try:
                self.window.after(0, lambda: self._finish_tts_install(error))
            except tk.TclError:
                pass

        threading.Thread(target=worker, name="SolomonVoiceVoiceModelInstaller", daemon=True).start()

    def _finish_tts_install(self, error):
        if self._closed:
            return
        self._model_installing = False
        self.apply_button.configure(state="normal")
        self.tts_model_combo.configure(state="readonly")
        self.browse_tts_button.configure(state="normal")
        self._update_tts_model_status()
        if error:
            self.status_var.set("Could not install the Read Aloud model.")
            messagebox.showerror("Voice model installation failed", str(error), parent=self.window)
        else:
            self.status_var.set("The Read Aloud model and voices are installed locally.")

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
        self.capture_button = ttk.Button(
            card, text="Record shortcut", command=lambda: self.begin_shortcut_capture("dictation"), style="SV.TButton"
        )
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
        self._meter_after_id = self.window.after(40, self._update_meter)

    def _cancel_meter_update(self):
        if self._meter_after_id is None:
            return
        try:
            self.window.after_cancel(self._meter_after_id)
        except tk.TclError:
            pass
        self._meter_after_id = None

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

    def begin_shortcut_capture(self, target="dictation"):
        self._capture_target = target
        button = self.read_capture_button if target == "read" else self.capture_button
        button.configure(text="Press shortcut now…", state="disabled")
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
            self.status_var.set(f"{event.keysym} is not supported as a SolomonVoice shortcut.")
            self._end_shortcut_capture()
            return "break"
        state = int(event.state)
        if self._capture_target == "read":
            self.read_ctrl_var.set(bool(state & 0x0004))
            self.read_shift_var.set(bool(state & 0x0001))
            self.read_alt_var.set(bool(state & 0x0008 or state & 0x20000))
            self.read_win_var.set(bool(state & 0x0040))
            self.read_key_var.set(key)
            display = self._read_shortcut_display()
        else:
            self.ctrl_var.set(bool(state & 0x0004))
            self.shift_var.set(bool(state & 0x0001))
            self.alt_var.set(bool(state & 0x0008 or state & 0x20000))
            self.win_var.set(bool(state & 0x0040))
            self.key_var.set(key)
            display = self._shortcut_display()
        self.status_var.set(f"Captured {display} — Apply to test it for conflicts.")
        self._end_shortcut_capture()
        return "break"

    def _end_shortcut_capture(self):
        if self._capture_binding is not None:
            self.window.unbind("<KeyPress>", self._capture_binding)
            self._capture_binding = None
        if hasattr(self, "capture_button"):
            self.capture_button.configure(text="Record shortcut", state="normal")
        if hasattr(self, "read_capture_button"):
            self.read_capture_button.configure(text="Record shortcut", state="normal")

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

    def _read_shortcut(self):
        modifiers = []
        if self.read_ctrl_var.get():
            modifiers.append("ctrl")
        if self.read_alt_var.get():
            modifiers.append("alt")
        if self.read_shift_var.get():
            modifiers.append("shift")
        if self.read_win_var.get():
            modifiers.append("win")
        return self.read_key_var.get().lower(), modifiers

    def _read_shortcut_display(self):
        key, modifiers = self._read_shortcut()
        return "+".join([item.title() for item in modifiers] + [key.title()])

    def apply(self):
        if self._model_installing:
            messagebox.showinfo(
                "Model installation in progress",
                "Wait for the selected model to finish installing before applying settings.",
                parent=self.window,
            )
            return
        self._stop_voice_preview()
        if not self._stop_microphone_test():
            messagebox.showerror(
                "Microphone still in use",
                "The microphone test could not be closed safely. Exit SolomonVoice to release it.",
                parent=self.window,
            )
            return
        key, modifiers = self._shortcut()
        read_key, read_modifiers = self._read_shortcut()
        old_hotkey = self.listener.hotkey
        old_read_hotkey = self.listener.read_hotkey
        old_reader = self.listener.reader
        old_transcriber = self.listener.transcriber
        old_startup = self.original_startup
        try:
            virtual_key(key)
            modifier_mask(modifiers)
            virtual_key(read_key)
            modifier_mask(read_modifiers)
            if not modifiers and key not in {f"f{number}" for number in range(13, 25)}:
                raise ValueError("Use Ctrl, Alt, or Shift with this key so normal typing is not blocked.")
            if self.read_enabled_var.get() and not read_modifiers and read_key not in {f"f{number}" for number in range(13, 25)}:
                raise ValueError("Use Ctrl, Alt, or Shift with the Read Aloud key so normal typing is not blocked.")

            candidate = copy.deepcopy(self.original)
            candidate["shortcut"] = {"key": key, "modifiers": modifiers}
            candidate["whisper"]["model"] = self.model_var.get().strip()
            candidate["whisper"]["model_directory"] = str(self._selected_model_directory())
            candidate["read_aloud"]["enabled"] = bool(self.read_enabled_var.get())
            candidate["read_aloud"]["shortcut"] = {"key": read_key, "modifiers": read_modifiers}
            candidate["read_aloud"]["model"] = self.tts_model_var.get()
            candidate["read_aloud"]["model_directory"] = str(self._selected_tts_directory())
            candidate["read_aloud"]["voice"] = VOICE_BY_LABEL[self.voice_var.get()][0]
            candidate["read_aloud"]["speed"] = float(self.speed_var.get())
            candidate["read_aloud"]["read_full_document"] = bool(self.read_full_var.get())
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
            self.listener.configure_model(
                candidate["whisper"]["model"],
                candidate["whisper"]["model_directory"],
            )
            self.listener.configure_read_aloud(candidate["read_aloud"])
            set_start_with_windows(candidate["behavior"]["start_with_windows"])
            self.config.replace(candidate)
            self.config.save_user()
            self.listener.feedback.sound_enabled = candidate["feedback"]["sound_enabled"]
        except Exception as exc:
            self.config.replace(self.original)
            self.listener.hotkey = old_hotkey
            self.listener.read_hotkey = old_read_hotkey
            self.listener.reader = old_reader
            self.listener.transcriber = old_transcriber
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
        self.model_var.set(defaults["whisper"].get("model", DEFAULT_MODEL))
        self.model_dir_var.set(str(resolve_model_directory(defaults["whisper"].get("model_directory"))))
        self._model_directory_changed()
        read_defaults = defaults.get("read_aloud", {})
        self.read_enabled_var.set(read_defaults.get("enabled", True))
        self.tts_model_var.set(read_defaults.get("model", DEFAULT_TTS_MODEL))
        self.tts_model_dir_var.set(str(resolve_tts_directory(read_defaults.get("model_directory"))))
        self.voice_var.set(VOICE_BY_ID[read_defaults.get("voice", "af_heart")][0])
        self.speed_var.set(read_defaults.get("speed", 1.0))
        self.read_full_var.set(read_defaults.get("read_full_document", True))
        read_shortcut = read_defaults.get("shortcut", {"key": "space", "modifiers": ["ctrl", "shift"]})
        read_configured = {item.lower() for item in read_shortcut["modifiers"]}
        self.read_ctrl_var.set(bool(read_configured & {"ctrl", "control"}))
        self.read_alt_var.set("alt" in read_configured)
        self.read_shift_var.set("shift" in read_configured)
        self.read_win_var.set(bool(read_configured & {"win", "windows"}))
        self.read_key_var.set(read_shortcut["key"])
        self._tts_directory_changed()
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
        if self._model_installing:
            messagebox.showinfo(
                "Model installation in progress",
                "Wait for the model installation to finish before closing Settings.",
                parent=self.window,
            )
            return
        self._stop_voice_preview()
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
            self._stop_voice_preview()
            self._stop_microphone_test()
        except Exception:
            pass
        self._closed = True
        self._cancel_meter_update()
        self._end_shortcut_capture()
        self.window.destroy()

    def _finish(self):
        if self._closed:
            return
        self._closed = True
        self._cancel_meter_update()
        self._end_shortcut_capture()
        self.window.destroy()
        if not self.was_paused:
            self.listener.resume()
        self.on_closed()
