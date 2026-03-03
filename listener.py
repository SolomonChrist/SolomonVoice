"""State machine for keyboard hook and recording orchestration."""

import threading
import time
from enum import Enum
from pathlib import Path
import tempfile

import numpy as np
import sounddevice as sd
from scipy.io import wavfile
from pynput import keyboard

from transcriber import Transcriber
from injector import Injector
from feedback import Feedback


class State(Enum):
    """Listener state machine states."""

    IDLE = "idle"
    RECORDING = "recording"
    TRANSCRIBING = "transcribing"


class Listener:
    """Keyboard hook listener with recording orchestration."""

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

        # Hotkey components
        self.hotkey_key = self._parse_key(config["shortcut"]["key"])
        self.hotkey_modifiers = set(config["shortcut"]["modifiers"])

        # Track current modifier key states
        self.ctrl_pressed = False
        self.alt_pressed = False
        self.shift_pressed = False

        self.listener_thread = None
        self.running = False

    def start(self):
        """Start the keyboard listener in a background thread."""
        self.running = True
        self.listener_thread = keyboard.Listener(
            on_press=self._on_key_press,
            on_release=self._on_key_release,
        )
        self.listener_thread.start()

    def stop(self):
        """Stop the keyboard listener."""
        self.running = False
        if self.listener_thread:
            self.listener_thread.stop()
            self.listener_thread.join(timeout=2)

    def _on_key_press(self, key):
        """Handle key press event.

        Args:
            key: The key pressed.

        Returns:
            False to suppress the hotkey, None otherwise.
        """
        try:
            # Track modifier states
            self._update_modifiers(key, pressed=True)

            if self.state == State.IDLE and self._is_hotkey(key):
                print(f"[SolomonVoice] Hotkey detected, starting recording...", flush=True)
                self._start_recording()
                # Suppress the hotkey only if configured
                if self.config.get("behavior.suppress_hotkey"):
                    return False
            elif self.state != State.IDLE and self._is_hotkey(key):
                print(f"[SolomonVoice] Hotkey pressed but not in IDLE state: {self.state.value}", flush=True)
        except Exception as e:
            print(f"[SolomonVoice] Error in key press handler: {e}", flush=True)

    def _on_key_release(self, key):
        """Handle key release event.

        Args:
            key: The key released.
        """
        try:
            # Track modifier states
            self._update_modifiers(key, pressed=False)

            # Debug: log all key releases when recording
            if self.state == State.RECORDING:
                try:
                    key_name = getattr(key, 'name', str(key))
                except:
                    key_name = str(key)
                print(f"[SolomonVoice] Key released during recording: {key_name}", flush=True)

            if self.state == State.RECORDING and self._is_hotkey(key):
                print(f"[SolomonVoice] Hotkey released, stopping recording...", flush=True)
                self._stop_recording()
            elif self.state == State.RECORDING:
                # Check if this is the main key being released (even if modifier state changed)
                try:
                    if key == self.hotkey_key:
                        print(f"[SolomonVoice] Main hotkey key released (via direct comparison), stopping recording...", flush=True)
                        self._stop_recording()
                except:
                    pass
        except Exception as e:
            print(f"[SolomonVoice] Error in key release handler: {e}", flush=True)

    def _update_modifiers(self, key, pressed):
        """Update modifier key states.

        Args:
            key: The key being updated.
            pressed: Whether the key was pressed or released.
        """
        try:
            if key == keyboard.Key.ctrl_l or key == keyboard.Key.ctrl_r:
                self.ctrl_pressed = pressed
            elif key == keyboard.Key.alt_l or key == keyboard.Key.alt_r:
                self.alt_pressed = pressed
            elif key == keyboard.Key.shift_l or key == keyboard.Key.shift_r:
                self.shift_pressed = pressed
        except AttributeError:
            pass

    def _is_hotkey(self, key):
        """Check if the pressed key is the configured hotkey.

        Args:
            key: The pressed key.

        Returns:
            True if this is the hotkey.
        """
        # Check the main key first
        try:
            if key == self.hotkey_key:
                # For release events, be more lenient with modifier checking
                # since modifier states might change during release
                if self.state == State.RECORDING:
                    # During recording, just check if it's the main key
                    return True
                else:
                    # For press events, check modifiers are active
                    return self._check_modifiers()
            return False
        except (AttributeError, TypeError):
            return False

    def _check_modifiers(self):
        """Check if all configured modifier keys are pressed.

        Returns:
            True if all modifiers are active.
        """
        for mod in self.hotkey_modifiers:
            if mod == "ctrl" and not self.ctrl_pressed:
                return False
            elif mod == "alt" and not self.alt_pressed:
                return False
            elif mod == "shift" and not self.shift_pressed:
                return False
        return True

    def _parse_key(self, key_name):
        """Parse key name from config to pynput key object.

        Args:
            key_name: Key name from config (e.g., 'space', 'f9', 'grave').

        Returns:
            pynput key object.
        """
        # Build key map dynamically to handle platform differences
        key_map = {
            "space": keyboard.Key.space,
            "f1": keyboard.Key.f1,
            "f2": keyboard.Key.f2,
            "f3": keyboard.Key.f3,
            "f4": keyboard.Key.f4,
            "f5": keyboard.Key.f5,
            "f6": keyboard.Key.f6,
            "f7": keyboard.Key.f7,
            "f8": keyboard.Key.f8,
            "f9": keyboard.Key.f9,
            "f10": keyboard.Key.f10,
            "f11": keyboard.Key.f11,
            "f12": keyboard.Key.f12,
            "escape": keyboard.Key.esc,
            "insert": keyboard.Key.insert,
            "delete": keyboard.Key.delete,
            "home": keyboard.Key.home,
            "end": keyboard.Key.end,
            "page_up": keyboard.Key.page_up,
            "page_down": keyboard.Key.page_down,
        }

        # Add grave key if it exists (not all systems support it)
        try:
            key_map["grave"] = keyboard.Key.grave
        except AttributeError:
            pass

        if key_name in key_map:
            return key_map[key_name]

        # Try to parse as a character
        if len(key_name) == 1:
            try:
                return keyboard.KeyCode(char=key_name)
            except Exception:
                pass

        raise ValueError(f"Unknown key: {key_name}")

    def _start_recording(self):
        """Start recording audio."""
        print(f"[SolomonVoice] _start_recording called, current state: {self.state.value}", flush=True)
        self.state = State.RECORDING
        self.audio_chunks = []
        self.start_time = time.time()
        self.record_start_time = time.time()

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

        # Set max recording timeout - also acts as fallback if key release isn't detected
        max_sec = self.config.get("behavior.max_recording_seconds")

        def timeout_handler():
            """Auto-stop recording when key is released or after timeout."""
            # For modifier hotkeys, detect when modifiers are released
            # For single-key hotkeys, use a short timeout (5 seconds)
            has_modifiers = len(self.hotkey_modifiers) > 0

            if has_modifiers:
                # Poll for modifier release - if modifiers released, stop
                initial_modifiers = {
                    "ctrl": self.ctrl_pressed,
                    "alt": self.alt_pressed,
                    "shift": self.shift_pressed,
                }

                for i in range(int(max_sec * 10)):  # Check 10x per second
                    time.sleep(0.1)

                    if self.state != State.RECORDING:
                        return

                    # Check if any required modifier was released
                    modifiers_released = False
                    for mod in self.hotkey_modifiers:
                        if mod == "ctrl" and initial_modifiers.get("ctrl") and not self.ctrl_pressed:
                            modifiers_released = True
                        elif mod == "alt" and initial_modifiers.get("alt") and not self.alt_pressed:
                            modifiers_released = True
                        elif mod == "shift" and initial_modifiers.get("shift") and not self.shift_pressed:
                            modifiers_released = True

                    if modifiers_released:
                        print(f"[SolomonVoice] Modifier released, stopping recording...", flush=True)
                        self._stop_recording()
                        return
            else:
                # Single-key hotkey (like F9): use short timeout (5 seconds)
                short_timeout = 5
                for i in range(short_timeout * 10):
                    time.sleep(0.1)
                    if self.state != State.RECORDING:
                        return

                # Timeout reached
                if self.state == State.RECORDING:
                    print(f"[SolomonVoice] Recording timeout ({short_timeout}s), auto-stopping...", flush=True)
                    self._stop_recording()
                    return

            # Final timeout as absolute limit
            if self.state == State.RECORDING:
                print(f"[SolomonVoice] Max recording time reached, auto-stopping...", flush=True)
                self._stop_recording()

        timeout_thread = threading.Thread(target=timeout_handler, daemon=True)
        timeout_thread.start()

        self.feedback.recording_start()

    def _stop_recording(self):
        """Stop recording audio and start transcription."""
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
        """Audio stream callback to accumulate chunks.

        Args:
            indata: Audio data.
            frames: Number of frames.
            time_info: Time info (unused).
            status: Status flags.
        """
        if status:
            # Log status but don't fail
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
        """Return a human-readable hotkey display string.

        Returns:
            Display string (e.g., 'Ctrl+Space').
        """
        mods = sorted(self.hotkey_modifiers)
        mod_str = "+".join(m.capitalize() for m in mods)

        key_name = self.config["shortcut"]["key"]
        if mod_str:
            return f"{mod_str}+{key_name.capitalize()}"
        return key_name.capitalize()
