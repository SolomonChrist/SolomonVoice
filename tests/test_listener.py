import threading

import numpy as np

import listener_v2
from listener_v2 import ListenerV2, State


class FakeConfig:
    data = {
        "shortcut": {"key": "space", "modifiers": ["ctrl"]},
        "whisper": {"model": "tiny", "task": "transcribe", "language": "en"},
        "audio": {"channels": 1, "sample_rate": 16000, "device": None, "silence_rms": 0.003},
        "behavior": {
            "append_space": True,
            "require_same_window": True,
            "min_recording_seconds": 0.1,
            "max_recording_seconds": 30,
        },
    }

    def get(self, key, default=None):
        value = self.data
        for part in key.split("."):
            if part not in value:
                return default
            value = value[part]
        return value

    def __getitem__(self, key):
        return self.data[key]


class FakeFeedback:
    def recording_start(self):
        pass

    def recording_stop(self):
        pass

    def transcription_done(self, _text):
        pass

    def error(self, _message):
        pass


class FakeHotkey:
    def __init__(self, *_args):
        self.active = False
        self.display_name = "Ctrl+Space"

    def start(self):
        self.active = True

    def stop(self):
        self.active = False

    def wait_until_released(self, timeout=3):
        return True


class FakeInjector:
    def __init__(self, *_args):
        self.injected = []

    def foreground_window(self):
        return 42

    def capture_target(self):
        return (42, 42, 0)

    def inject(self, text, target_window=None):
        self.injected.append((text, target_window))


class FakeTranscriber:
    def __init__(self, *_args):
        self.started = threading.Event()
        self.release = threading.Event()

    def warm_up(self):
        pass

    def transcribe(self, _audio, language=None):
        self.started.set()
        self.release.wait(timeout=2)
        return "private text"


def make_listener(monkeypatch):
    monkeypatch.setattr(listener_v2, "NativeHotkey", FakeHotkey)
    monkeypatch.setattr(listener_v2, "Injector", FakeInjector)
    monkeypatch.setattr(listener_v2, "Transcriber", FakeTranscriber)
    return ListenerV2(FakeConfig(), FakeFeedback())


def test_pause_unregisters_hotkey(monkeypatch):
    listener = make_listener(monkeypatch)
    listener._running = True
    listener.state = State.IDLE
    listener.hotkey.start()

    listener.pause()

    assert listener.state == State.PAUSED
    assert listener.hotkey.active is False


def test_stop_invalidates_in_flight_transcription_and_prevents_late_insert(monkeypatch):
    listener = make_listener(monkeypatch)
    listener._running = True
    listener.state = State.TRANSCRIBING
    listener._generation = 3
    audio = [np.full((1600, 1), 0.1, dtype=np.float32)]

    worker = threading.Thread(target=listener._finish_recording, args=(3, 1.0, audio, 42))
    worker.start()
    assert listener.transcriber.started.wait(timeout=1)
    listener.stop()
    listener.transcriber.release.set()
    worker.join(timeout=2)

    assert listener.injector.injected == []
    assert listener.state == State.STOPPED


def test_controller_preserves_quick_press_release_order(monkeypatch):
    listener = make_listener(monkeypatch)
    listener._running = True
    transitions = []
    listener._start_recording = lambda: transitions.append("press")
    listener._stop_recording = lambda expected_generation=None: transitions.append("release")
    controller = threading.Thread(target=listener._controller_loop)
    controller.start()

    listener._on_hotkey_press()
    listener._on_hotkey_release()
    listener._commands.put(None)
    controller.join(timeout=1)

    assert transitions == ["press", "release"]


def test_stale_timeout_cannot_stop_new_generation(monkeypatch):
    listener = make_listener(monkeypatch)
    listener._running = True
    listener.state = State.RECORDING
    listener._generation = 8

    listener._stop_recording(expected_generation=7)

    assert listener.state == State.RECORDING


def test_pause_cannot_return_before_in_progress_insertion_finishes(monkeypatch):
    listener = make_listener(monkeypatch)
    listener._running = True
    listener.state = State.TRANSCRIBING
    listener._generation = 2
    listener.transcriber.release.set()
    insertion_started = threading.Event()
    allow_insertion = threading.Event()

    def blocking_inject(text, target_window=None):
        insertion_started.set()
        allow_insertion.wait(timeout=2)
        listener.injector.injected.append((text, target_window))

    listener.injector.inject = blocking_inject
    audio = [np.full((1600, 1), 0.1, dtype=np.float32)]
    worker = threading.Thread(target=listener._finish_recording, args=(2, 1.0, audio, (42, 42, 0)))
    worker.start()
    assert insertion_started.wait(timeout=1)

    pauser = threading.Thread(target=listener.pause)
    pauser.start()
    assert pauser.is_alive()
    allow_insertion.set()
    worker.join(timeout=2)
    pauser.join(timeout=2)

    assert listener.injector.injected == [("private text", (42, 42, 0))]
    assert listener.state == State.PAUSED


class BrokenStream:
    def stop(self):
        raise RuntimeError("stop failed")

    def abort(self):
        raise RuntimeError("abort failed")

    def close(self):
        raise RuntimeError("close failed")


class AbortableStream:
    def __init__(self):
        self.aborted = False
        self.closed = False

    def stop(self):
        raise RuntimeError("stop failed")

    def abort(self):
        self.aborted = True

    def close(self):
        self.closed = True


def test_pause_reports_error_and_retains_stream_when_close_fails(monkeypatch):
    listener = make_listener(monkeypatch)
    listener._running = True
    listener.state = State.IDLE
    listener.stream = BrokenStream()

    listener.pause()

    assert listener.state == State.ERROR
    assert isinstance(listener.stream, BrokenStream)
    assert "Failed to close microphone" in str(listener._last_stream_error)


def test_pause_uses_abort_fallback_before_confirming_success(monkeypatch):
    listener = make_listener(monkeypatch)
    listener._running = True
    listener.state = State.IDLE
    stream = AbortableStream()
    listener.stream = stream

    listener.pause()

    assert listener.state == State.PAUSED
    assert listener.stream is None
    assert stream.aborted and stream.closed
