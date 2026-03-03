"""Windows-optimized keyboard listener using keyboard module (more reliable)."""

import threading
import time
from enum import Enum
from pathlib import Path
import tempfile

import numpy as np
import sounddevice as sd
from scipy.io import wavfile
import keyboard

from transcriber import Transcriber
from injector import Injector
from feedback import Feedback


class State(Enum):
    """Listener state machine states."""
    IDLE = "idle"
    RECORDING = "recording"
    TRANSCRIBING = "transcribing"


class ListenerV2:
    """Windows-optimized keyboard listener with better key release detection."""

    def __init__(self, config, feedback):
        """Initialize listener.

        Args:
            config: Config object.
            feedback: Feedback handler.
        """
        self.config = config
        self.feedback = feedback
        self.state = State.IDLE
        self.audio_chunks = []
        self.stream = None
        self.start_time = None

        # Initialize components
        self.transcriber = Transcriber(config.get("whisper.model"))
        self.injector = Injector(config.get("behavior.append_space"))

        # Parse hotkey
        self.hotkey_string = self._build_hotkey_string(config)
        print(f"[SolomonVoice] Hotkey: {self.hotkey_string}", flush=True)

        self.running = False

    def _build_hotkey_string(self, config):
        """Build keyboard module hotkey string from config.

        Examples: 'ctrl+space', 'f9', 'alt+shift+v'
        """
        key = config["shortcut"]["key"]
        modifiers = config["shortcut"]["modifiers"]

        parts = modifiers + [key]
        return "+".join(parts).lower()

    def start(self):
        """Start the keyboard listener."""
        self.running = True
        print(f"[SolomonVoice] Starting keyboard listener for '{self.hotkey_string}'...", flush=True)

        # Parse hotkey into individual keys for monitoring
        self.hotkey_parts = self.hotkey_string.split('+')
        self.main_key = self.hotkey_parts[-1]  # Last part is the main key
        self.modifier_keys = self.hotkey_parts[:-1]  # Everything before is modifiers

        # Register hotkey with keyboard module
        keyboard.add_hotkey(
            self.hotkey_string,
            self._on_hotkey_press,
            suppress=self.config.get("behavior.suppress_hotkey", True)
        )

        # Monitor main key release
        keyboard.on_release(self._on_key_release)

        print(f"[SolomonVoice] Keyboard listener active", flush=True)

    def stop(self):
        """Stop the keyboard listener."""
        self.running = False
        try:
            keyboard.remove_all_hotkeys()
        except:
            pass

    def _on_hotkey_press(self):
        """Handle hotkey press."""
        try:
            if self.state == State.IDLE:
                print(f"[SolomonVoice] Hotkey detected, starting recording...", flush=True)
                self._start_recording()
        except Exception as e:
            print(f"[SolomonVoice] Error in hotkey handler: {e}", flush=True)

    def _on_key_release(self, event):
        """Handle any key release - check if it's the main hotkey key."""
        try:
            if self.state == State.RECORDING and event.name == self.main_key:
                print(f"[SolomonVoice] Main key '{self.main_key}' released, stopping recording...", flush=True)
                self._stop_recording()
        except Exception as e:
            pass  # Ignore errors in global key release handler

    def _start_recording(self):
        """Start recording audio."""
        print(f"[SolomonVoice] _start_recording called, current state: {self.state.value}", flush=True)
        self.state = State.RECORDING
        self.audio_chunks = []
        self.start_time = time.time()

        # Create audio stream
        try:
            print(f"[SolomonVoice] Creating audio input stream...", flush=True)
            self.stream = sd.InputStream(
                channels=self.config.get("audio.channels"),
                samplerate=self.config.get("audio.sample_rate"),
                device=self.config.get("audio.device"),
                callback=self._audio_callback,
            )
            self.stream.start()
            print(f"[SolomonVoice] Audio stream started successfully", flush=True)
        except Exception as e:
            print(f"[SolomonVoice] Failed to start audio stream: {e}", flush=True)
            self.feedback.error(f"Failed to start audio stream: {e}")
            self.state = State.IDLE
            return

        self.feedback.recording_start()

        # Wait for key release in background
        release_thread = threading.Thread(target=self._wait_for_key_release, daemon=True)
        release_thread.start()

    def _wait_for_key_release(self):
        """Wait for the hotkey to be released (using polling)."""
        timeout = self.config.get("behavior.max_recording_seconds", 30)
        start = time.time()

        while self.state == State.RECORDING:
            # Check if timeout reached
            if time.time() - start > timeout:
                print(f"[SolomonVoice] Max recording time reached, stopping...", flush=True)
                self._stop_recording()
                return

            # Check if key is currently pressed
            # keyboard module doesn't have a direct "is key pressed" function,
            # so we use a timeout-based approach with polling
            time.sleep(0.05)

        print(f"[SolomonVoice] Key release detected, stopping recording...", flush=True)

    def _stop_recording(self):
        """Stop recording and start transcription."""
        if self.state != State.RECORDING:
            return

        self.state = State.TRANSCRIBING
        self.feedback.recording_stop()

        # Stop audio stream
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None

        # Spawn background thread for transcription
        thread = threading.Thread(target=self._finish_recording, daemon=True)
        thread.start()

    def _audio_callback(self, indata, frames, time_info, status):
        """Audio stream callback."""
        if status:
            pass
        self.audio_chunks.append(indata.copy())

    def _finish_recording(self):
        """Process recorded audio: transcribe and inject text."""
        print(f"[SolomonVoice] _finish_recording started, state: {self.state.value}", flush=True)
        try:
            # Check minimum recording duration
            duration = time.time() - self.start_time
            min_sec = self.config.get("behavior.min_recording_seconds")
            if duration < min_sec:
                self.state = State.IDLE
                return

            # Concatenate audio chunks
            if not self.audio_chunks:
                self.feedback.error("No audio recorded")
                self.state = State.IDLE
                return

            audio_data = np.concatenate(self.audio_chunks, axis=0)

            # Write to temporary WAV file
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp_path = tmp.name

            try:
                sample_rate = self.config.get("audio.sample_rate")
                wavfile.write(tmp_path, sample_rate, (audio_data * 32767).astype(np.int16))

                # Transcribe
                language = self.config.get("whisper.language")
                text = self.transcriber.transcribe(tmp_path, language=language)

                if not text:
                    self.feedback.error("Could not understand audio")
                    self.state = State.IDLE
                    return

                # Inject text
                self.injector.inject(text)
                self.feedback.transcription_done(text)

            finally:
                # Clean up temp file
                try:
                    Path(tmp_path).unlink()
                except Exception:
                    pass

        except Exception as e:
            print(f"[SolomonVoice] Exception in _finish_recording: {e}", flush=True)
            self.feedback.error(str(e))
        finally:
            print(f"[SolomonVoice] _finish_recording complete, resetting state to IDLE", flush=True)
            self.state = State.IDLE

    def hotkey_display(self):
        """Return a human-readable hotkey display string."""
        return self.hotkey_string.replace("+", "+").title()
