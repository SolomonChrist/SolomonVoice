"""Thread-safe recording controller for SolomonVoice."""

from __future__ import annotations

import threading
import time
import queue
from datetime import datetime
from enum import Enum

import numpy as np
import sounddevice as sd

from audio_devices import capture_sample_rate, resolve_input_device
from hotkey import NativeHotkey
from injector import Injector
from transcriber import Transcriber, UnsafeTranscriptionError
from whisper_models import model_path


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

    def __init__(self, config, feedback, on_state=None, on_level=None, on_history=None):
        self.config = config
        self.feedback = feedback
        self.on_state = on_state or (lambda _state, _detail=None: None)
        self.on_level = on_level or (lambda _level: None)
        self.on_history = on_history or (lambda: None)

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
        self._pending_hotkeys = []
        self._capture_ready = threading.Event()
        self._last_audio = None
        self._history = []
        self._history_sequence = 0

        self.transcriber = Transcriber(
            config.get("whisper.model"),
            config.get("whisper.task", "transcribe"),
            config.get("whisper.model_directory"),
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
        self.cancel_hotkey = None

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
            cancel_hotkey_closed = self._stop_cancel_hotkey()
            pending_hotkeys_closed = self._stop_pending_hotkeys()
            microphone_closed = self._close_stream()
        with self._lock:
            self.audio_chunks = []
        if hotkey_error or not cancel_hotkey_closed or not pending_hotkeys_closed or not microphone_closed:
            message = str(
                hotkey_error
                or ("Escape cancel hotkey did not unregister" if not cancel_hotkey_closed else None)
                or ("A shortcut probe did not unregister" if not pending_hotkeys_closed else None)
                or self._last_stream_error
                or "Microphone did not close"
            )
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
            self._spawn_worker(self._warm_model, "SolomonVoiceModelLoader")
        except Exception as exc:
            self._set_state(State.ERROR, str(exc))
            self.feedback.error(str(exc))

    def configure_model(self, model_name, model_directory=None) -> None:
        """Replace the transcriber only while listening is safely paused."""
        with self._lock:
            if self.state != State.PAUSED:
                raise RuntimeError("Pause SolomonVoice before changing the speech model")
        checkpoint = model_path(model_name, model_directory)
        if not checkpoint.is_file():
            raise RuntimeError(
                f"'{model_name}' is not installed in '{checkpoint.parent}'. "
                "Use Install selected model before applying this change."
            )
        self.transcriber = Transcriber(
            model_name,
            self.config.get("whisper.task", "transcribe"),
            str(checkpoint.parent),
        )

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
        cancel_hotkey_closed = self._stop_cancel_hotkey()
        pending_hotkeys_closed = self._stop_pending_hotkeys()
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
        if not cancel_hotkey_closed:
            self.feedback.error("Escape cancel hotkey did not unregister")
        if not pending_hotkeys_closed:
            self.feedback.error("A shortcut probe did not unregister")
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

    def _on_cancel_press(self) -> None:
        with self._lock:
            if self._running:
                self._commands.put(("cancel", self._generation))

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
                mode = self.config.get("behavior.recording_mode", "hold")
                if mode == "toggle":
                    if kind == "press":
                        if self.state == State.RECORDING:
                            self._stop_recording()
                        else:
                            self._start_recording()
                elif kind == "press":
                    self._start_recording()
                else:
                    self._stop_recording()
            elif kind == "timeout":
                self._stop_recording(expected_generation=token)
            elif kind == "cancel":
                self._cancel_recording(expected_generation=token)

    def _start_recording(self) -> None:
        stream = None
        with self._lock:
            if not self._running or self.state != State.IDLE:
                return
            self._generation += 1
            generation = self._generation
            self.audio_chunks = []
            self._capture_ready.clear()
            self.target_window = self.injector.capture_target()
            self.state = State.RECORDING
            self.on_state(State.RECORDING, "Preparing microphone…")
            try:
                selection = self.config.get("audio.device")
                capture_rate = capture_sample_rate(
                    selection,
                    self.config.get("audio.sample_rate"),
                )
                stream = sd.InputStream(
                    channels=self.config.get("audio.channels"),
                    samplerate=capture_rate,
                    device=resolve_input_device(selection),
                    dtype="float32",
                    callback=self._audio_callback,
                )
                stream.start()
                self.stream = stream
                self.capture_sample_rate = capture_rate
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

        # Some USB and Bluetooth endpoints wake slowly. Do not tell the user to
        # speak until PortAudio has delivered the first real block. The callback
        # already retains that block, so speech begun early is not discarded.
        if not self._capture_ready.wait(timeout=2.0):
            self._close_stream()
            with self._lock:
                if not self._running or self._generation != generation:
                    return
                self.state = State.ERROR
                self.audio_chunks = []
            detail = "The selected microphone opened but did not deliver audio. Choose another input in Settings."
            self.on_state(State.ERROR, detail)
            self.feedback.error(detail)
            return
        with self._lock:
            if not self._running or self._generation != generation or self.state != State.RECORDING:
                return
            self.start_time = time.monotonic()
        self.feedback.recording_start()
        self.on_state(State.RECORDING, "Microphone ready — speak now")

        self._start_cancel_hotkey(generation)

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
            target_window = self.target_window
            capture_rate = getattr(self, "capture_sample_rate", self.config.get("audio.sample_rate"))
            captured_frames = sum(len(chunk) for chunk in self.audio_chunks)
            duration = captured_frames / float(capture_rate) if capture_rate else 0.0
            self.state = State.TRANSCRIBING

        if not self._stop_cancel_hotkey():
            self._close_stream()
            with self._lock:
                self._generation += 1
                self.state = State.ERROR
                self.audio_chunks = []
            message = "Escape cancel hotkey did not unregister"
            self.feedback.error(message)
            self.on_state(State.ERROR, message)
            return
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
            lambda: self._finish_recording(generation, duration, chunks, target_window, capture_rate),
            "SolomonVoiceTranscriber",
        )

    def _cancel_recording(self, expected_generation=None) -> None:
        """Discard the active capture without running Whisper or inserting text."""
        with self._lock:
            if self.state != State.RECORDING:
                return
            if expected_generation is not None and self._generation != expected_generation:
                return
            self._generation += 1
            self.state = State.IDLE
            self.audio_chunks = []
        if not self._stop_cancel_hotkey():
            self._close_stream()
            message = "Escape cancel hotkey did not unregister"
            self._set_state(State.ERROR, message)
            self.feedback.error(message)
            return
        if not self._close_stream():
            message = str(self._last_stream_error or "Microphone did not close")
            self._set_state(State.ERROR, message)
            self.feedback.error(message)
            return
        self.feedback.recording_canceled()
        self.on_level(0.0)
        self.on_state(State.IDLE, "Recording canceled")

    def _finish_recording(self, generation, duration, chunks, target_window, capture_rate=None) -> None:
        error_notified = False
        text = ""
        audio = None
        try:
            if not self._generation_is_current(generation):
                return
            if duration < self.config.get("behavior.min_recording_seconds"):
                return
            if not chunks:
                raise RuntimeError("No audio was captured")
            audio = np.concatenate(chunks, axis=0).reshape(-1)
            target_rate = self.config.get("audio.sample_rate")
            if capture_rate and int(capture_rate) != int(target_rate):
                audio = self._resample_audio(audio, int(capture_rate), int(target_rate))
            with self._lock:
                self._last_audio = audio.copy()
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
            self._append_history(text, "Inserted", None)
        except Exception as exc:
            if self._generation_is_current(generation):
                error_notified = True
                blocked_text = exc.transcript if isinstance(exc, UnsafeTranscriptionError) else text
                if isinstance(exc, UnsafeTranscriptionError):
                    history_status = "Blocked"
                elif blocked_text:
                    history_status = "Not inserted"
                else:
                    history_status = "Failed"
                self._append_history(blocked_text, history_status, str(exc))
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

    @staticmethod
    def _resample_audio(audio, source_rate, target_rate):
        if not len(audio) or source_rate == target_rate:
            return audio
        output_length = max(1, round(len(audio) * target_rate / source_rate))
        source_positions = np.linspace(0.0, 1.0, num=len(audio), endpoint=False)
        target_positions = np.linspace(0.0, 1.0, num=output_length, endpoint=False)
        return np.interp(target_positions, source_positions, audio).astype(np.float32)

    def _audio_callback(self, indata, _frames, _time_info, status) -> None:
        if self.state != State.RECORDING:
            return
        if status:
            print(f"[SolomonVoice] Audio status: {status}", flush=True)
        chunk = indata.copy()
        self.audio_chunks.append(chunk)
        self._capture_ready.set()
        rms = float(np.sqrt(np.mean(np.square(chunk, dtype=np.float64))))
        self.on_level(min(1.0, rms * 18.0))

    def has_retry_audio(self) -> bool:
        with self._lock:
            return self._last_audio is not None and bool(len(self._last_audio))

    def history_snapshot(self):
        """Return transcript metadata without exposing retained audio buffers."""
        with self._lock:
            return [dict(item) for item in reversed(self._history)]

    def retry_last(self, insert=False) -> bool:
        """Rerun the most recent in-memory recording with the active model."""
        with self._lock:
            if self.state not in {State.IDLE, State.PAUSED} or self._last_audio is None:
                return False
            return_state = self.state
            audio = self._last_audio.copy()
            target_window = self.injector.capture_target() if insert else None
            self._generation += 1
            generation = self._generation
            self.state = State.TRANSCRIBING
        model_name = getattr(self.transcriber, "model_name", self.config.get("whisper.model", "Whisper"))
        self.on_state(State.TRANSCRIBING, f"Retrying with {model_name}…")
        self._spawn_worker(
            lambda: self._finish_retry(generation, audio, target_window, return_state, insert),
            "SolomonVoiceRetry",
        )
        return True

    def _finish_retry(self, generation, audio, target_window, return_state, insert):
        text = ""
        error = None
        status = "Rerun"
        try:
            text = self.transcriber.transcribe(audio, language=self.config.get("whisper.language"))
            if insert:
                with self._lock:
                    if not self._running or self._generation != generation:
                        return
                    self.injector.inject(text, target_window=target_window)
                self.feedback.transcription_done(text)
                status = "Rerun inserted"
        except Exception as exc:
            error = exc
            text = exc.transcript if isinstance(exc, UnsafeTranscriptionError) else text
            if isinstance(exc, UnsafeTranscriptionError):
                status = "Blocked"
            elif text:
                status = "Not inserted"
            else:
                status = "Failed"
            self.feedback.error(str(exc))
        finally:
            self._append_history(text, status, str(error) if error else None)
            with self._lock:
                if self._running and self._generation == generation:
                    self.state = return_state
                    self.on_state(return_state, str(error) if error else None)

    def _append_history(self, text, status, detail):
        with self._lock:
            self._history_sequence += 1
            self._history.append(
                {
                    "id": self._history_sequence,
                    "time": datetime.now().strftime("%I:%M:%S %p"),
                    "model": getattr(self.transcriber, "model_name", self.config.get("whisper.model", "Whisper")),
                    "status": status,
                    "text": text or "",
                    "detail": detail or "",
                }
            )
            if len(self._history) > 20:
                del self._history[:-20]
        self.on_history()

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

    def _start_cancel_hotkey(self, generation) -> None:
        if not self.config.get("behavior.escape_to_cancel", True):
            return
        candidate = NativeHotkey("escape", [], self._on_cancel_press, lambda: None)
        try:
            candidate.start()
        except Exception as exc:
            # Dictation remains usable if another app temporarily owns Escape.
            self.feedback.error(f"Escape-to-cancel is unavailable: {exc}")
            return
        with self._lock:
            valid = (
                self._running
                and self.state == State.RECORDING
                and self._generation == generation
                and self.cancel_hotkey is None
            )
            if valid:
                self.cancel_hotkey = candidate
        if not valid:
            try:
                candidate.stop()
            except Exception as exc:
                self.feedback.error(f"Escape cancel cleanup failed: {exc}")

    def _stop_cancel_hotkey(self) -> bool:
        with self._lock:
            cancel_hotkey = self.cancel_hotkey
        if cancel_hotkey is None:
            return True
        try:
            cancel_hotkey.stop()
        except Exception as exc:
            self.feedback.error(str(exc))
            return False
        with self._lock:
            if self.cancel_hotkey is cancel_hotkey:
                self.cancel_hotkey = None
        return True

    def _stop_pending_hotkeys(self) -> bool:
        """Retry teardown of any shortcut probe whose release was unconfirmed."""
        with self._lock:
            pending = list(self._pending_hotkeys)
        failed = []
        for hotkey in pending:
            try:
                hotkey.stop()
            except Exception as exc:
                failed.append(hotkey)
                self.feedback.error(str(exc))
        with self._lock:
            self._pending_hotkeys = failed
        return not failed

    def configure_shortcut(self, key, modifiers) -> None:
        """Validate and stage a new shortcut while the listener is paused.

        The candidate is registered and unregistered once before it replaces the
        old object. A conflict therefore leaves the previous shortcut intact.
        """
        with self._lock:
            if self.state != State.PAUSED:
                raise RuntimeError("Pause SolomonVoice before changing the shortcut")
        candidate = NativeHotkey(
            key,
            list(modifiers),
            self._on_hotkey_press,
            self._on_hotkey_release,
        )
        candidate.start()
        try:
            candidate.stop()
        except Exception as exc:
            with self._lock:
                self._pending_hotkeys.append(candidate)
            self._set_state(State.ERROR, f"Could not release shortcut probe: {exc}")
            raise
        with self._lock:
            self.hotkey = candidate

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
