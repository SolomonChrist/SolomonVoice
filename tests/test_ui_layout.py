import sys

import pytest

from config import Config
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
        style = __import__("tkinter.ttk", fromlist=["Style"]).Style(settings.window)
        assert style.lookup("SV.TButton", "background", ("active",)) == "#203855"
        assert style.lookup("SV.TCombobox", "fieldbackground", ("readonly",)) == INPUT
        assert style.lookup("Accent.TButton", "foreground", ("active",)) == BG
    finally:
        settings.shutdown()
        root.destroy()
