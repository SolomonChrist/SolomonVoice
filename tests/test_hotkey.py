import pytest
import sys

from hotkey import MOD_CONTROL, MOD_NOREPEAT, MOD_SHIFT, NativeHotkey, modifier_mask, virtual_key


def test_virtual_key_mapping():
    assert virtual_key("space") == 0x20
    assert virtual_key("f9") == 0x78
    assert virtual_key("v") == ord("V")


def test_modifier_mask_always_disables_repeat():
    assert modifier_mask(["ctrl", "shift"]) == MOD_NOREPEAT | MOD_CONTROL | MOD_SHIFT


def test_unknown_key_is_rejected():
    with pytest.raises(ValueError, match="Unsupported hotkey key"):
        virtual_key("not-a-key")


@pytest.mark.skipif(sys.platform != "win32", reason="Win32 integration test")
def test_native_hotkey_can_be_repeatedly_registered_and_confirmed_unregistered():
    hotkey = NativeHotkey("f23", ["ctrl", "shift"], lambda: None, lambda: None)
    for _ in range(20):
        hotkey.start()
        assert hotkey.active
        hotkey.stop()
        assert not hotkey.active
