"""Private, session-only transcript history for SolomonVoice."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from settings_ui import BG, BORDER, INPUT, MUTED, SURFACE, SURFACE_HOVER, TEAL, TEXT, TEXT_SOFT


class HistoryWindow:
    """Show recent attempts without persisting transcript or audio to disk."""

    def __init__(self, parent, listener, was_paused=False, on_closed=None):
        self.listener = listener
        self.was_paused = bool(was_paused)
        self.on_closed = on_closed or (lambda: None)
        self._closed = False
        self._entries = {}

        self.window = tk.Toplevel(parent)
        self.window.title("SolomonVoice Session History")
        self.window.geometry("720x540")
        self.window.minsize(620, 460)
        self.window.configure(bg=BG)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self._configure_style()
        self._build()
        self.refresh()
        self.window.update_idletasks()
        x = max(20, (self.window.winfo_screenwidth() - 720) // 2)
        y = max(20, (self.window.winfo_screenheight() - 540) // 2)
        self.window.geometry(f"720x540+{x}+{y}")
        self.window.lift()
        self.window.focus_force()

    def _configure_style(self):
        style = ttk.Style(self.window)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("History.TFrame", background=BG)
        style.configure("History.TLabel", background=BG, foreground=TEXT_SOFT, font=("Segoe UI", 10))
        style.configure("HistoryTitle.TLabel", background=BG, foreground=TEXT, font=("Segoe UI Semibold", 22))
        style.configure(
            "History.Treeview",
            background=INPUT,
            fieldbackground=INPUT,
            foreground=TEXT_SOFT,
            bordercolor=BORDER,
            rowheight=29,
            font=("Segoe UI", 9),
        )
        style.map(
            "History.Treeview",
            background=[("selected", SURFACE_HOVER)],
            foreground=[("selected", TEXT)],
        )
        style.configure(
            "History.Treeview.Heading",
            background=SURFACE,
            foreground=MUTED,
            bordercolor=BORDER,
            font=("Segoe UI Semibold", 9),
        )
        style.map("History.Treeview.Heading", background=[("active", SURFACE_HOVER)])
        style.configure(
            "History.TButton",
            background=SURFACE_HOVER,
            foreground=TEXT,
            bordercolor=BORDER,
            focuscolor=BORDER,
            relief="flat",
            font=("Segoe UI Semibold", 9),
            padding=(14, 9),
        )
        style.map(
            "History.TButton",
            background=[("pressed", INPUT), ("active", "#203855"), ("disabled", "#132238")],
            foreground=[("disabled", "#60748D"), ("!disabled", TEXT)],
        )

    def _build(self):
        shell = ttk.Frame(self.window, style="History.TFrame", padding=(26, 22))
        shell.pack(fill="both", expand=True)
        ttk.Label(shell, text="SOLOMON VOICE  •  PRIVATE SESSION", foreground=TEAL, style="History.TLabel").pack(anchor="w")
        ttk.Label(shell, text="Session history", style="HistoryTitle.TLabel").pack(anchor="w", pady=(1, 2))
        ttk.Label(
            shell,
            text="Recent attempts stay in memory and disappear when SolomonVoice exits. Only the latest audio can be rerun.",
            style="History.TLabel",
        ).pack(anchor="w", pady=(0, 14))

        table_frame = tk.Frame(shell, bg=BORDER, padx=1, pady=1)
        table_frame.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(
            table_frame,
            columns=("time", "model", "status", "text"),
            show="headings",
            selectmode="browse",
            height=5,
            style="History.Treeview",
        )
        for key, title, width in (
            ("time", "Time", 100),
            ("model", "Model", 80),
            ("status", "Result", 110),
            ("text", "Transcript", 360),
        ):
            self.tree.heading(key, text=title)
            self.tree.column(key, width=width, minwidth=60, stretch=key == "text")
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self._selection_changed)

        self.detail = tk.Text(
            shell,
            height=5,
            bg=INPUT,
            fg=TEXT_SOFT,
            insertbackground=TEAL,
            selectbackground=SURFACE_HOVER,
            selectforeground=TEXT,
            relief="flat",
            highlightthickness=1,
            highlightbackground=BORDER,
            wrap="word",
            font=("Segoe UI", 10),
            padx=10,
            pady=8,
        )
        self.detail.pack(fill="x", pady=(12, 10))
        self.detail.configure(state="disabled")

        controls = ttk.Frame(shell, style="History.TFrame")
        controls.pack(fill="x")
        self.status = tk.StringVar(value="Select an attempt to inspect its full text.")
        ttk.Button(controls, text="Close", command=self.close, style="History.TButton").pack(side="right")
        self.copy_button = ttk.Button(
            controls, text="Copy text", command=self.copy_selected, state="disabled", style="History.TButton"
        )
        self.copy_button.pack(side="right", padx=(0, 8))
        self.retry_button = ttk.Button(
            controls, text="Rerun last", command=self.retry_last, style="History.TButton"
        )
        self.retry_button.pack(side="right", padx=(0, 8))
        ttk.Label(controls, textvariable=self.status, style="History.TLabel").pack(
            side="left", fill="x", expand=True
        )

    def refresh(self):
        selected = self.tree.selection()
        selected_id = selected[0] if selected else None
        self._entries = {str(item["id"]): item for item in self.listener.history_snapshot()}
        for child in self.tree.get_children():
            self.tree.delete(child)
        for item_id, item in self._entries.items():
            preview = item["text"] or item["detail"] or "No transcript"
            preview = preview.replace("\n", " ")
            if len(preview) > 80:
                preview = preview[:77] + "…"
            self.tree.insert(
                "", "end", iid=item_id,
                values=(item["time"], item["model"], item["status"], preview),
            )
        if selected_id in self._entries:
            self.tree.selection_set(selected_id)
        elif self._entries:
            first = next(iter(self._entries))
            self.tree.selection_set(first)
            self.tree.focus(first)
        self.retry_button.configure(state="normal" if self.listener.has_retry_audio() else "disabled")
        self._selection_changed()

    def _selection_changed(self, _event=None):
        selection = self.tree.selection()
        entry = self._entries.get(selection[0]) if selection else None
        body = ""
        if entry:
            body = entry["text"]
            if entry["detail"]:
                body += ("\n\n" if body else "") + entry["detail"]
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        self.detail.insert("1.0", body)
        self.detail.configure(state="disabled")
        self.copy_button.configure(state="normal" if entry and entry["text"] else "disabled")

    def copy_selected(self):
        selection = self.tree.selection()
        entry = self._entries.get(selection[0]) if selection else None
        if not entry or not entry["text"]:
            return
        self.window.clipboard_clear()
        self.window.clipboard_append(entry["text"])
        self.status.set("Transcript copied by your request.")

    def retry_last(self):
        if self.listener.retry_last(insert=False):
            self.status.set("Rerunning the latest in-memory audio with the active model…")
            self.retry_button.configure(state="disabled")
        else:
            self.status.set("The last recording is unavailable or SolomonVoice is busy.")

    def close(self):
        if self._closed:
            return
        self._closed = True
        self.window.destroy()
        if not self.was_paused:
            self.listener.resume()
        self.on_closed()

    def shutdown(self):
        if self._closed:
            return
        self._closed = True
        self.window.destroy()
