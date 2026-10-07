import threading

import numpy as np
import pytest

import listener_v2
from listener_v2 import ListenerV2, State


class FakeConfig:
    data = {
        "shortcut": {"key": "space", "modifiers": ["ctrl"]},
        "whisper": {"model": "tiny", "task": "transcribe", "language": "en"},
        "read_aloud": {
            "enabled": True,
            "shortcut": {"key": "space", "modifiers": ["ctrl", "shift"]},
            "model": "kokoro-v1.0-fp16",
            "model_directory": None,
            "voice": "af_heart",
            "speed": 1.0,
            "read_full_document": True,
            "max_characters": 100000,
            "output_device": None,
        },
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

    def recording_canceled(self):
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
        self.args = _args
        self.started = threading.Event()
        self.release = threading.Event()

    def warm_up(self):
        pass

    def transcribe(self, _audio, language=None):
        self.started.set()
        self.release.wait(timeout=2)
        return "private text"


class FakeReader:
    def __init__(self, *_args):
        self.args = _args
        self.stop_calls = 0

    def stop(self):
        self.stop_calls += 1

    def speak(self, *_args, **_kwargs):
        return True


def make_listener(monkeypatch):
    monkeypatch.setattr(listener_v2, "NativeHotkey", FakeHotkey)
    monkeypatch.setattr(listener_v2, "Injector", FakeInjector)
    monkeypatch.setattr(listener_v2, "Transcriber", FakeTranscriber)
    monkeypatch.setattr(listener_v2, "TTSReader", FakeReader)
    return ListenerV2(FakeConfig(), FakeFeedback())


def test_pause_unregisters_hotkey(monkeypatch):
    listener = make_listener(monkeypatch)
    listener._running = True
    listener.state = State.IDLE
    listener.hotkey.start()
    listener.read_hotkey.start()

    listener.pause()

    assert listener.state == State.PAUSED
    assert listener.hotkey.active is False
    assert listener.read_hotkey.active is False
    assert listener.reader.stop_calls == 1


def test_read_hotkey_toggles_and_second_press_stops(monkeypatch):
    listener = make_listener(monkeypatch)
    listener._running = True
    listener.state = State.IDLE
    listener._spawn_worker = lambda *_args: None

    listener._start_reading()
    assert listener.state == State.READING

    listener._stop_reading()
    assert listener.state == State.IDLE
    assert listener.reader.stop_calls == 1


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


def test_toggle_mode_ignores_release_and_second_press_stops(monkeypatch):
    listener = make_listener(monkeypatch)
    listener.config.data["behavior"]["recording_mode"] = "toggle"
    listener._running = True
    listener.state = State.IDLE
    transitions = []

    def start():
        transitions.append("start")
        listener.state = State.RECORDING

    def stop(expected_generation=None):
        transitions.append("stop")
        listener.state = State.TRANSCRIBING

    listener._start_recording = start
    listener._stop_recording = stop
    controller = threading.Thread(target=listener._controller_loop)
    controller.start()
    epoch = listener._hotkey_epoch
    listener._commands.put(("press", epoch))
    listener._commands.put(("release", epoch))
    listener._commands.put(("press", epoch))
    listener._commands.put(None)
    controller.join(timeout=1)

    assert transitions == ["start", "stop"]


def test_cancel_discards_audio_without_transcription(monkeypatch):
    listener = make_listener(monkeypatch)
    listener._running = True
    listener.state = State.RECORDING
    listener._generation = 4
    listener.audio_chunks = [np.ones((16, 1), dtype=np.float32)]
    listener._close_stream = lambda: True
    listener._stop_cancel_hotkey = lambda: True

    listener._cancel_recording(expected_generation=4)

    assert listener.state == State.IDLE
    assert listener.audio_chunks == []
    assert listener._generation == 5


def test_configure_shortcut_probes_candidate_before_replacing(monkeypatch):
    listener = make_listener(monkeypatch)
    listener._running = True
    listener.state = State.PAUSED
    old_hotkey = listener.hotkey

    listener.configure_shortcut("f9", ["ctrl", "shift"])

    assert listener.hotkey is not old_hotkey
    assert listener.hotkey.active is False


def test_configure_model_uses_existing_checkpoint_while_paused(monkeypatch, tmp_path):
    listener = make_listener(monkeypatch)
    listener.state = State.PAUSED
    checkpoint = tmp_path / "custom-english.pt"
    checkpoint.write_bytes(b"local checkpoint")

    listener.configure_model("custom-english", str(tmp_path))

    assert listener.transcriber.args == ("custom-english", "transcribe", str(tmp_path))


def test_configure_model_requires_an_installed_checkpoint(monkeypatch, tmp_path):
    listener = make_listener(monkeypatch)
    listener.state = State.PAUSED

    with pytest.raises(RuntimeError, match="not installed"):
        listener.configure_model("small", str(tmp_path))


def test_retry_keeps_audio_in_memory_and_adds_session_history(monkeypatch):
    listener = make_listener(monkeypatch)
    listener._running = True
    listener.state = State.IDLE
    listener._last_audio = np.ones(1600, dtype=np.float32)
    listener.transcriber.release.set()

    assert listener.retry_last(insert=False) is True
    for worker in list(listener._workers):
        worker.join(timeout=2)

    history = listener.history_snapshot()
    assert history[0]["status"] == "Rerun"
    assert history[0]["text"] == "private text"
    assert "audio" not in history[0]


def test_recording_waits_for_first_microphone_block_and_keeps_it(monkeypatch):
    listener = make_listener(monkeypatch)
    listener._running = True
    listener.state = State.IDLE
    listener.config.data["audio"]["sample_rate"] = 16000

    class ReadyStream:
        def __init__(self, **kwargs):
            self.callback = kwargs["callback"]

        def start(self):
            self.callback(np.ones((320, 1), dtype=np.float32), 320, None, None)

        def stop(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(listener_v2.sd, "InputStream", ReadyStream)
    monkeypatch.setattr(listener_v2, "capture_sample_rate", lambda *_args: 16000)
    monkeypatch.setattr(listener_v2, "resolve_input_device", lambda *_args: None)

    listener._start_recording()

    assert listener.state == State.RECORDING
    assert listener._capture_ready.is_set()
    assert len(listener.audio_chunks) == 1
    assert len(listener.audio_chunks[0]) == 320


def test_stale_escape_registration_is_immediately_released(monkeypatch):
    listener = make_listener(monkeypatch)
    listener._running = True
    listener.state = State.RECORDING
    listener._generation = 9
    created = []

    class RacingHotkey(FakeHotkey):
        def __init__(self, *_args):
            super().__init__()
            self.stop_calls = 0
            created.append(self)

        def start(self):
            super().start()
            listener._running = False
            listener.state = State.STOPPED

        def stop(self):
            self.stop_calls += 1
            super().stop()

    monkeypatch.setattr(listener_v2, "NativeHotkey", RacingHotkey)
    listener._start_cancel_hotkey(9)

    assert listener.cancel_hotkey is None
    assert created[0].stop_calls == 1
    assert created[0].active is False


def test_failed_escape_teardown_retains_handle_for_retry(monkeypatch):
    listener = make_listener(monkeypatch)

    class FailingHotkey(FakeHotkey):
        def stop(self):
            raise RuntimeError("unregister failed")

    candidate = FailingHotkey()
    listener.cancel_hotkey = candidate

    assert listener._stop_cancel_hotkey() is False
    assert listener.cancel_hotkey is candidate


def test_failed_shortcut_probe_is_retained_for_exit_cleanup(monkeypatch):
    listener = make_listener(monkeypatch)
    listener._running = True
    listener.state = State.PAUSED

    class FailingHotkey(FakeHotkey):
        def stop(self):
            raise RuntimeError("unregister failed")

    monkeypatch.setattr(listener_v2, "NativeHotkey", FailingHotkey)
    with pytest.raises(RuntimeError, match="unregister failed"):
        listener.configure_shortcut("f9", ["ctrl"])

    assert len(listener._pending_hotkeys) == 1
    assert listener.state == State.ERROR
