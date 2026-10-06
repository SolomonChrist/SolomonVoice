"""Thread-safe recording controller for SolomonVoice."""

from __future__ import annotations

import threading
import time
import queue
from enum import Enum

import numpy as np
import sounddevice as sd

from hotkey import NativeHotkey
from injector import Injector
from transcriber import Transcriber


class State(Enum):
    STARTING = "starting"
    IDLE = "ready"
    RECORDING = "recording"
    TRANSCRIBING = "transcribing"
    PAUSED = "paused"
    ERROR = "error"
    STOPPED = "stopped"


class ListenerV2:
    """Own the hotkey, microphone, transcription worker, and state transitions."""

    def __init__(self, config, feedback, on_state=None, on_level=None):
        self.config = config
        self.feedback = feedback
        self.on_state = on_state or (lambda _state, _detail=None: None)
        self.on_level = on_level or (lambda _level: None)

        self.state = State.STARTING
        self.audio_chunks: list[np.ndarray] = []
        self.stream = None
        self.start_time = 0.0
        self.target_window = 0
        self._last_stream_error = None
        self._lock = threading.RLock()
        self._running = False
        self._generation = 0
        self._hotkey_epoch = 0
        self._workers: set[threading.Thread] = set()
        self._commands = queue.Queue()
        self._controller_thread: threading.Thread | None = None

        self.transcriber = Transcriber(
            config.get("whisper.model"),
            config.get("whisper.task", "transcribe"),
        )
        self.injector = Injector(
            config.get("behavior.append_space"),
            config.get("behavior.require_same_window", True),
        )
        self.hotkey = NativeHotkey(
            config["shortcut"]["key"],
            config["shortcut"]["modifiers"],
            self._on_hotkey_press,
            self._on_hotkey_release,
        )

    def start(self) -> None:
        with self._lock:
            if self._running:
                return
            self._running = True
            self._hotkey_epoch += 1
            self._controller_thread = threading.Thread(
                target=self._controller_loop,
                name="SolomonVoiceController",
                daemon=True,
            )
            self._controller_thread.start()
        try:
            self.hotkey.start()
        except Exception:
            with self._lock:
                self._running = False
            self._commands.put(None)
            raise
        self._set_state(State.IDLE)
        self._spawn_worker(self._warm_model, "SolomonVoiceModelLoader")

    def pause(self) -> None:
        """Release the hotkey and microphone while keeping the tray app available."""
        with self._lock:
            if not self._running or self.state == State.PAUSED:
                return
            self._generation += 1
            self._hotkey_epoch += 1
        hotkey_error = None
        try:
            self.hotkey.stop()
        except Exception as exc:
            hotkey_error = exc
        finally:
            microphone_closed = self._close_stream()
        with self._lock:
            self.audio_chunks = []
        if hotkey_error or not microphone_closed:
            message = str(hotkey_error or self._last_stream_error or "Microphone did not close")
            self._set_state(State.ERROR, message)
            self.feedback.error(message)
            return
        self._set_state(State.PAUSED)

    def resume(self) -> None:
        with self._lock:
            if not self._running or self.state != State.PAUSED:
                return
            self._hotkey_epoch += 1
        try:
            self.hotkey.start()
            self._set_state(State.IDLE)
        except Exception as exc:
            self._set_state(State.ERROR, str(exc))
            self.feedback.error(str(exc))

    def stop(self) -> None:
        """Idempotently release every OS resource owned by the listener."""
        with self._lock:
            if not self._running and self.state == State.STOPPED:
                return
            self._running = False
            self._generation += 1
        try:
            self.hotkey.stop()
        except Exception as exc:
            self.feedback.error(str(exc))
        microphone_closed = self._close_stream()
        with self._lock:
            self.audio_chunks = []
        self._commands.put(None)
        controller = self._controller_thread
        if controller and controller is not threading.current_thread():
            controller.join(timeout=2)
        self._controller_thread = None
        if not microphone_closed and self._last_stream_error:
            self.feedback.error(str(self._last_stream_error))
        self._set_state(State.STOPPED)

    def toggle_paused(self) -> None:
        if self.state == State.PAUSED:
            self.resume()
        else:
            self.pause()

    def _on_hotkey_press(self) -> None:
        with self._lock:
            if self._running:
                self._commands.put(("press", self._hotkey_epoch))

    def _on_hotkey_release(self) -> None:
        with self._lock:
            if self._running:
                self._commands.put(("release", self._hotkey_epoch))

    def _controller_loop(self) -> None:
        """Serialize input transitions so a quick release cannot overtake press."""
        while True:
            command = self._commands.get()
            if command is None:
                return
            kind, token = command
            if kind in {"press", "release"}:
                with self._lock:
                    if token != self._hotkey_epoch:
                        continue
                if kind == "press":
                    self._start_recording()
                else:
                    self._stop_recording()
            elif kind == "timeout":
                self._stop_recording(expected_generation=token)

    def _start_recording(self) -> None:
        stream = None
        with self._lock:
            if not self._running or self.state != State.IDLE:
                return
            self._generation += 1
            generation = self._generation
            self.audio_chunks = []
            self.start_time = time.monotonic()
            self.target_window = self.injector.capture_target()
            self.state = State.RECORDING

            # The tone finishes before the microphone opens, so it is not transcribed.
            self.feedback.recording_start()
            self.on_state(State.RECORDING, None)
            try:
                stream = sd.InputStream(
                    channels=self.config.get("audio.channels"),
                    samplerate=self.config.get("audio.sample_rate"),
                    device=self.config.get("audio.device"),
                    dtype="float32",
                    callback=self._audio_callback,
                )
                stream.start()
                self.stream = stream
            except Exception as exc:
                if stream is not None:
                    self.stream = stream
                microphone_closed = self._close_stream()
                self.state = State.IDLE if microphone_closed else State.ERROR
                detail = f"Microphone error: {exc}"
                if not microphone_closed and self._last_stream_error:
                    detail += f"; cleanup failed: {self._last_stream_error}"
                self.on_state(State.ERROR, detail)
                self.feedback.error(detail)
                return

        self._spawn_worker(
            lambda: self._recording_timeout(generation),
            "SolomonVoiceRecordingTimeout",
        )

    def _stop_recording(self, expected_generation=None) -> None:
        with self._lock:
            if self.state != State.RECORDING:
                return
            if expected_generation is not None and self._generation != expected_generation:
                return
            generation = self._generation
            duration = time.monotonic() - self.start_time
            target_window = self.target_window
            self.state = State.TRANSCRIBING

        if not self._close_stream():
            message = str(self._last_stream_error or "Microphone did not close")
            with self._lock:
                self._generation += 1
                self.state = State.ERROR
                self.audio_chunks = []
            self.feedback.error(message)
            self.on_state(State.ERROR, message)
            return
        with self._lock:
            if not self._running or self._generation != generation or self.state != State.TRANSCRIBING:
                self.audio_chunks = []
                return
            chunks = self.audio_chunks
            self.audio_chunks = []
            # Hold transition ownership until the UI event is queued, so Pause
            # can never be overwritten by an older transcribing notification.
            self.feedback.recording_stop()
            self.on_state(State.TRANSCRIBING, None)
        self._spawn_worker(
            lambda: self._finish_recording(generation, duration, chunks, target_window),
            "SolomonVoiceTranscriber",
        )

    def _finish_recording(self, generation, duration, chunks, target_window) -> None:
        error_notified = False
        try:
            if not self._generation_is_current(generation):
                return
            if duration < self.config.get("behavior.min_recording_seconds"):
                return
            if not chunks:
                raise RuntimeError("No audio was captured")
            audio = np.concatenate(chunks, axis=0).reshape(-1)
            rms = float(np.sqrt(np.mean(np.square(audio, dtype=np.float64))))
            if rms < self.config.get("audio.silence_rms", 0.003):
                raise RuntimeError("No speech detected")

            text = self.transcriber.transcribe(
                audio,
                language=self.config.get("whisper.language"),
            )
            if not text:
                raise RuntimeError("Could not understand the recording")
            if not self._generation_is_current(generation):
                return
            if not self.hotkey.wait_until_released(timeout=3):
                raise RuntimeError("Release the dictation shortcut before text can be inserted")
            # Injection and lifecycle invalidation share this lock. If Pause/Exit
            # wins, insertion is canceled; if insertion wins, Pause waits for the
            # few milliseconds needed to finish before reporting success.
            with self._lock:
                if not self._generation_is_current(generation):
                    return
                self.injector.inject(text, target_window=target_window)
                self.feedback.transcription_done(text)
        except Exception as exc:
            if self._generation_is_current(generation):
                error_notified = True
                self.feedback.error(str(exc))
                self.on_state(State.ERROR, str(exc))
        finally:
            with self._lock:
                if self._running and self._generation == generation and self.state != State.PAUSED:
                    self.state = State.IDLE
                    if not error_notified:
                        self.on_state(State.IDLE, None)

    def _recording_timeout(self, generation) -> None:
        maximum = self.config.get("behavior.max_recording_seconds", 30)
        deadline = time.monotonic() + maximum
        while time.monotonic() < deadline:
            with self._lock:
                if self._generation != generation or self.state != State.RECORDING:
                    return
            time.sleep(0.05)
        if self._running:
            self._commands.put(("timeout", generation))

    def _audio_callback(self, indata, _frames, _time_info, status) -> None:
        if self.state != State.RECORDING:
            return
        if status:
            print(f"[SolomonVoice] Audio status: {status}", flush=True)
        chunk = indata.copy()
        self.audio_chunks.append(chunk)
        rms = float(np.sqrt(np.mean(np.square(chunk, dtype=np.float64))))
        self.on_level(min(1.0, rms * 18.0))

    def _close_stream(self) -> bool:
        """Close PortAudio ownership, using abort as a stop fallback.

        The stream reference is retained when close fails so a later Pause/Exit
        can retry and the UI never falsely claims the microphone is released.
        """
        with self._lock:
            stream = self.stream
            self._last_stream_error = None
        if stream is None:
            return True
        stop_error = None
        try:
            stream.stop()
        except Exception as exc:
            stop_error = exc
            try:
                stream.abort()
            except Exception as abort_error:
                print(
                    f"[SolomonVoice] Microphone stop/abort warning: {stop_error}; {abort_error}",
                    flush=True,
                )
        try:
            stream.close()
        except Exception as exc:
            with self._lock:
                self._last_stream_error = RuntimeError(f"Failed to close microphone: {exc}")
            return False
        with self._lock:
            if self.stream is stream:
                self.stream = None
        return True

    def _warm_model(self) -> None:
        try:
            self.transcriber.warm_up()
        except Exception as exc:
            if self._running:
                self.feedback.error(f"Model load failed: {exc}")
                self.on_state(State.ERROR, f"Model load failed: {exc}")

    def _generation_is_current(self, generation) -> bool:
        with self._lock:
            return self._running and self._generation == generation and self.state == State.TRANSCRIBING

    def _set_state(self, state, detail=None) -> None:
        with self._lock:
            self.state = state
        self.on_state(state, detail)

    def _spawn_worker(self, target, name) -> None:
        def run():
            try:
                target()
            finally:
                with self._lock:
                    self._workers.discard(threading.current_thread())

        thread = threading.Thread(target=run, name=name, daemon=True)
        with self._lock:
            self._workers.add(thread)
        thread.start()

    def hotkey_display(self) -> str:
        return self.hotkey.display_name
