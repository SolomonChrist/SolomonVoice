import sys

import pytest

from config import Config
from history_ui import HistoryWindow
from ui import DesktopUI
from listener_v2 import State
from settings_ui import BG, INPUT, SettingsWindow


@pytest.mark.skipif(sys.platform != "win32", reason="Windows overlay layout test")
def test_branded_overlay_columns_do_not_overlap():
    ui = DesktopUI(Config("solomonvoice_config.json"))
    try:
        ui._set_state("transcribing", None)
        ui.root.update_idletasks()
        title_box = ui.canvas.bbox(ui.title)
        subtitle_box = ui.canvas.bbox(ui.subtitle)
        brand_box = ui.canvas.bbox(ui.brand)
        first_bar_box = ui.canvas.bbox(ui._bars[0])

        assert brand_box[2] < ui.divider_x - 8
        assert title_box[2] < ui.divider_x - 8
        assert subtitle_box[2] < ui.divider_x - 8
        assert first_bar_box[0] > ui.divider_x + 8
    finally:
        ui.shutdown()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows settings layout test")
def test_settings_actions_are_visible_inside_window():
    class PausedListener:
        state = State.PAUSED

    root = __import__("tkinter").Tk()
    root.withdraw()
    settings = SettingsWindow(root, Config("solomonvoice_config.json"), PausedListener(), was_paused=True)
    try:
        settings.window.update()
        height = settings.window.winfo_height()
        for button in (settings.defaults_button, settings.apply_button, settings.cancel_button):
            assert button.winfo_ismapped()
            assert button.winfo_rooty() + button.winfo_height() <= settings.window.winfo_rooty() + height
        assert settings.model_combo.winfo_ismapped()
        assert settings.model_dir_entry.winfo_ismapped()
        assert settings.install_model_button.winfo_ismapped()
        assert settings.install_tts_button.winfo_ismapped()
        assert settings.voice_combo.winfo_ismapped()
        assert settings.preview_voice_button.winfo_ismapped()
        assert settings.output_combo.winfo_ismapped()
        assert settings.test_output_button.winfo_ismapped()
        assert settings.tts_model_dir_entry.winfo_ismapped()
        assert settings.model_var.get() == "tiny"
        assert settings.tts_model_var.get() == "kokoro-v1.0-fp16"
        assert settings.read_key_var.get() == "space"
        assert settings.read_ctrl_var.get()
        assert settings.read_shift_var.get()
        style = __import__("tkinter.ttk", fromlist=["Style"]).Style(settings.window)
        assert style.lookup("SV.TButton", "background", ("active",)) == "#203855"
        assert style.lookup("SV.TCombobox", "fieldbackground", ("readonly",)) == INPUT
        assert style.lookup("Accent.TButton", "foreground", ("active",)) == BG
        assert style.lookup("SV.Vertical.TScrollbar", "background", ("active",)) == "#203855"
    finally:
        settings.shutdown()

    class HistoryListener:
        @staticmethod
        def history_snapshot():
            return [{
                "id": 1,
                "time": "01:23:45 PM",
                "model": "base",
                "status": "Blocked",
                "text": "Repeated output was blocked.",
                "detail": "Whisper produced repeated text.",
            }]

        @staticmethod
        def has_retry_audio():
            return True

        @staticmethod
        def retry_last(insert=False):
            return not insert

    history = HistoryWindow(root, HistoryListener(), was_paused=True)
    try:
        history.window.update()
        assert history.tree.winfo_ismapped()
        assert history.retry_button.winfo_ismapped()
        assert history.copy_button.winfo_ismapped()
        style = __import__("tkinter.ttk", fromlist=["Style"]).Style(history.window)
        assert style.lookup("History.Treeview", "background", ("selected",)) == "#172A43"
    finally:
        history.shutdown()
        root.destroy()
