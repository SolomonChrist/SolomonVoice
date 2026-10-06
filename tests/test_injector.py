import ctypes

from injector import INPUT, Injector, utf16_code_units


def test_utf16_code_units_preserve_unicode_and_surrogate_pairs():
    assert utf16_code_units("Aé") == [0x0041, 0x00E9]
    assert utf16_code_units("😀") == [0xD83D, 0xDE00]


def test_windows_input_structure_has_native_64_bit_size():
    assert ctypes.sizeof(INPUT) == 40


def test_inject_constructs_and_sends_unicode_events():
    class FakeUser32:
        def __init__(self):
            self.call = None

        def SendInput(self, count, events, size):
            self.call = (count, size, [events[index].ki.dwFlags for index in range(count)])
            return count

    injector = object.__new__(Injector)
    injector.append_space = False
    injector.require_same_window = True
    injector.capture_target = lambda: (10, 20, 30)
    injector._user32 = FakeUser32()

    injector.inject("A", target_window=(10, 20, 30))

    assert injector._user32.call == (2, 40, [0x0004, 0x0006])
