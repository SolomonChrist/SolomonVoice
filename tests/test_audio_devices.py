import pytest

from audio_devices import (
    Microphone,
    Speaker,
    capture_sample_rate,
    resolve_input_device,
    resolve_output_device,
    selected_microphone,
    selected_speaker,
)


MICROPHONES = [
    Microphone(2, "Laptop Array", "WASAPI", 2, 48000, True),
    Microphone(7, "USB Podcast Mic", "WASAPI", 1, 48000, False),
]

SPEAKERS = [
    Speaker(4, "Desk Speakers", "MME", 2, 48000, True),
    Speaker(14, "Bluetooth Headphones", "WASAPI", 2, 48000, False),
]


def test_stable_identity_resolves_after_device_index_changes():
    selection = {"name": "USB Podcast Mic", "hostapi": "WASAPI"}
    assert resolve_input_device(selection, MICROPHONES) == 7


def test_missing_saved_microphone_fails_closed():
    with pytest.raises(RuntimeError, match="not connected"):
        resolve_input_device({"name": "Old Headset", "hostapi": "WASAPI"}, MICROPHONES)


def test_none_selects_current_default_for_display():
    assert selected_microphone(None, MICROPHONES).name == "Laptop Array"


def test_duplicate_identity_fails_instead_of_silently_selecting_first():
    duplicates = MICROPHONES + [Microphone(9, "USB Podcast Mic", "WASAPI", 1, 48000, False)]
    with pytest.raises(RuntimeError, match="ambiguous"):
        resolve_input_device({"name": "USB Podcast Mic", "hostapi": "WASAPI"}, duplicates)


def test_capture_rate_falls_back_to_native_rate():
    class FakeSoundDevice:
        def check_input_settings(self, **kwargs):
            if kwargs["samplerate"] == 16000:
                raise RuntimeError("unsupported")

    rate = capture_sample_rate(
        {"name": "USB Podcast Mic", "hostapi": "WASAPI"},
        16000,
        MICROPHONES,
        FakeSoundDevice(),
    )
    assert rate == 48000


def test_capture_rate_prefers_native_to_avoid_driver_buffering():
    checked = []

    class FakeSoundDevice:
        def check_input_settings(self, **kwargs):
            checked.append(kwargs["samplerate"])

    rate = capture_sample_rate(
        {"name": "USB Podcast Mic", "hostapi": "WASAPI"},
        16000,
        MICROPHONES,
        FakeSoundDevice(),
    )

    assert rate == 48000
    assert checked == [48000]


def test_capture_rate_uses_whisper_rate_if_native_is_unavailable():
    class FakeSoundDevice:
        def check_input_settings(self, **kwargs):
            if kwargs["samplerate"] == 48000:
                raise RuntimeError("native unavailable")

    rate = capture_sample_rate(
        {"name": "USB Podcast Mic", "hostapi": "WASAPI"},
        16000,
        MICROPHONES,
        FakeSoundDevice(),
    )

    assert rate == 16000


def test_stable_output_identity_resolves_after_device_index_changes():
    selection = {"name": "Bluetooth Headphones", "hostapi": "WASAPI"}
    assert resolve_output_device(selection, SPEAKERS) == 14


def test_none_selects_current_default_speaker_for_display():
    assert selected_speaker(None, SPEAKERS).name == "Desk Speakers"


def test_missing_saved_speaker_fails_closed():
    with pytest.raises(RuntimeError, match="not connected"):
        resolve_output_device({"name": "Old Monitor", "hostapi": "WASAPI"}, SPEAKERS)
