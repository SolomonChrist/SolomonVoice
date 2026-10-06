import sys

import pytest

from config import Config
from ui import DesktopUI


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
