"""Stable Windows audio input and output discovery helpers."""

from __future__ import annotations

from dataclasses import dataclass

import sounddevice as sd


@dataclass(frozen=True)
class Microphone:
    index: int
    name: str
    hostapi: str
    channels: int
    sample_rate: int
    is_default: bool = False

    @property
    def label(self) -> str:
        default = "  •  Windows default" if self.is_default else ""
        return f"{self.name}  —  {self.hostapi}  (device {self.index}){default}"

    @property
    def identity(self) -> dict:
        return {"name": self.name, "hostapi": self.hostapi}


@dataclass(frozen=True)
class Speaker:
    index: int
    name: str
    hostapi: str
    channels: int
    sample_rate: int
    is_default: bool = False

    @property
    def label(self) -> str:
        default = "  •  Windows default" if self.is_default else ""
        return f"{self.name}  —  {self.hostapi}  (device {self.index}){default}"

    @property
    def identity(self) -> dict:
        return {"name": self.name, "hostapi": self.hostapi}


def input_microphones(sd_module=sd) -> list[Microphone]:
    """Return input-capable devices with stable names and host API labels."""
    devices = sd_module.query_devices()
    hostapis = sd_module.query_hostapis()
    try:
        default_index = int(sd_module.default.device[0])
    except (TypeError, ValueError, IndexError):
        default_index = -1

    microphones = []
    for index, device in enumerate(devices):
        channels = int(device.get("max_input_channels", 0))
        if channels <= 0:
            continue
        host_index = int(device.get("hostapi", -1))
        if 0 <= host_index < len(hostapis):
            host_name = str(hostapis[host_index].get("name", "Windows audio"))
        else:
            host_name = "Windows audio"
        microphones.append(
            Microphone(
                index=index,
                name=str(device.get("name", f"Input {index}")),
                hostapi=host_name,
                channels=channels,
                sample_rate=int(float(device.get("default_samplerate", 16000))),
                is_default=index == default_index,
            )
        )
    return microphones


def output_speakers(sd_module=sd) -> list[Speaker]:
    """Return output-capable devices with stable names and host API labels."""
    devices = sd_module.query_devices()
    hostapis = sd_module.query_hostapis()
    try:
        default_index = int(sd_module.default.device[1])
    except (TypeError, ValueError, IndexError):
        default_index = -1

    speakers = []
    for index, device in enumerate(devices):
        channels = int(device.get("max_output_channels", 0))
        if channels <= 0:
            continue
        host_index = int(device.get("hostapi", -1))
        if 0 <= host_index < len(hostapis):
            host_name = str(hostapis[host_index].get("name", "Windows audio"))
        else:
            host_name = "Windows audio"
        speakers.append(
            Speaker(
                index=index,
                name=str(device.get("name", f"Output {index}")),
                hostapi=host_name,
                channels=channels,
                sample_rate=int(float(device.get("default_samplerate", 44100))),
                is_default=index == default_index,
            )
        )
    return speakers


def resolve_input_device(selection, microphones=None):
    """Resolve a persisted microphone identity to today's PortAudio index.

    Device indexes are accepted for backward compatibility. New settings store
    name + host API so reconnecting USB/Bluetooth devices does not silently
    select a different index.
    """
    if selection is None:
        return None
    if isinstance(selection, int):
        return selection
    microphones = input_microphones() if microphones is None else microphones
    if isinstance(selection, str):
        for microphone in microphones:
            if microphone.name == selection:
                return microphone.index
    elif isinstance(selection, dict):
        name = selection.get("name")
        hostapi = selection.get("hostapi")
        matches = [
            microphone
            for microphone in microphones
            if microphone.name == name and (not hostapi or microphone.hostapi == hostapi)
        ]
        if len(matches) == 1:
            return matches[0].index
        if len(matches) > 1:
            raise RuntimeError(
                "The saved microphone name is ambiguous because Windows exposes multiple identical endpoints. "
                "Choose Windows default or a uniquely named device."
            )
    raise RuntimeError(
        "The selected microphone is not connected. Choose another device in SolomonVoice Settings."
    )


def resolve_output_device(selection, speakers=None):
    """Resolve a persisted speaker identity to today's PortAudio index."""
    if selection is None:
        return None
    if isinstance(selection, int):
        return selection
    speakers = output_speakers() if speakers is None else speakers
    if isinstance(selection, str):
        for speaker in speakers:
            if speaker.name == selection:
                return speaker.index
    elif isinstance(selection, dict):
        name = selection.get("name")
        hostapi = selection.get("hostapi")
        matches = [
            speaker
            for speaker in speakers
            if speaker.name == name and (not hostapi or speaker.hostapi == hostapi)
        ]
        if len(matches) == 1:
            return matches[0].index
        if len(matches) > 1:
            raise RuntimeError(
                "The saved speaker name is ambiguous because Windows exposes multiple identical endpoints. "
                "Choose Windows default or a uniquely named device."
            )
    raise RuntimeError(
        "The selected speaker is not connected. Choose another output in SolomonVoice Settings."
    )


def capture_sample_rate(selection, requested_rate, microphones=None, sd_module=sd):
    """Prefer the endpoint's native rate, then resample in memory for Whisper.

    Bluetooth and USB drivers can report that a converted rate is supported
    while adding a large wake-up buffer or returning incomplete leading audio.
    Native capture is more reliable and SolomonVoice already resamples safely.
    """
    microphones = input_microphones(sd_module) if microphones is None else microphones
    device = resolve_input_device(selection, microphones)
    microphone = selected_microphone(selection, microphones)
    if microphone is None:
        raise RuntimeError("Windows did not return an available default microphone")
    native_rate = int(microphone.sample_rate)
    try:
        sd_module.check_input_settings(
            device=device,
            channels=1,
            dtype="float32",
            samplerate=native_rate,
        )
        return native_rate
    except Exception:
        sd_module.check_input_settings(
            device=device,
            channels=1,
            dtype="float32",
            samplerate=requested_rate,
        )
        return int(requested_rate)


def selected_microphone(selection, microphones):
    """Return the selected microphone object, or the current default."""
    if not microphones:
        return None
    if selection is None:
        return next((item for item in microphones if item.is_default), microphones[0])
    try:
        index = resolve_input_device(selection, microphones)
    except RuntimeError:
        return None
    return next((item for item in microphones if item.index == index), None)


def selected_speaker(selection, speakers):
    """Return the selected speaker object, or the current Windows default."""
    if not speakers:
        return None
    if selection is None:
        return next((item for item in speakers if item.is_default), speakers[0])
    try:
        index = resolve_output_device(selection, speakers)
    except RuntimeError:
        return None
    return next((item for item in speakers if item.index == index), None)
