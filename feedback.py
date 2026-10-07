"""Console, audio, and privacy-safe diagnostic feedback for SolomonVoice."""

from datetime import datetime
import os
from pathlib import Path
import sys
import threading
import winsound


class Feedback:
    """Handles console and audio feedback."""

    def __init__(self, sound_enabled=True, console_enabled=True):
        """Initialize feedback handler.

        Args:
            sound_enabled: Whether to play audio beeps.
            console_enabled: Whether to print to console.
        """
        self.sound_enabled = sound_enabled
        self.console_enabled = console_enabled
        self._log_lock = threading.Lock()
        local_app_data = os.environ.get("LOCALAPPDATA")
        log_root = Path(local_app_data) / "SolomonVoice" if local_app_data else Path.home() / ".solomonvoice"
        self.log_path = log_root / "runtime.log"

    def recording_start(self):
        """Signal that recording has started."""
        self._beep(800, 100)
        self._print("Recording... (release key to stop)")

    def recording_stop(self):
        """Signal that recording has stopped."""
        self._beep(600, 100)
        self._print("Transcribing...")

    def transcription_done(self, text):
        """Signal that transcription is complete.

        Args:
            text: The transcribed text.
        """
        self._beep(1000, 150)
        self._print("Done — text inserted")

    def recording_canceled(self):
        """Signal that a recording was intentionally discarded."""
        self._beep(500, 70)
        self._print("Recording canceled")

    def read_shortcut_received(self, state):
        self._print(f"Read Aloud shortcut received while state={state}")

    def reading_start(self):
        self._beep(720, 80)
        self._print("Read Aloud started; waiting for shortcut release")

    def reading_captured(self, source, characters):
        self._print(f"Read Aloud captured {characters} characters from {source}")

    def reading_done(self):
        self._print("Read Aloud finished")

    def reading_stopped(self):
        self._print("Read Aloud stopped")

    def error(self, message):
        """Signal an error.

        Args:
            message: The error message.
        """
        self._beep(400, 300)
        self._print(f"Error: {message}")

    def _beep(self, frequency, duration):
        """Play a beep sound.

        Args:
            frequency: Frequency in Hz.
            duration: Duration in milliseconds.
        """
        if self.sound_enabled:
            try:
                winsound.Beep(frequency, duration)
            except Exception as e:
                # winsound might fail in some environments; continue anyway
                pass

    def _print(self, message):
        """Print and persist an event without recording dictated or selected text.

        Args:
            message: The message to print.
        """
        if self.console_enabled:
            print(f"[SolomonVoice] {message}", flush=True)
        try:
            with self._log_lock:
                self.log_path.parent.mkdir(parents=True, exist_ok=True)
                if self.log_path.exists() and self.log_path.stat().st_size > 256 * 1024:
                    previous = self.log_path.with_name("runtime.previous.log")
                    os.replace(self.log_path, previous)
                with open(self.log_path, "a", encoding="utf-8") as stream:
                    timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
                    stream.write(f"{timestamp}  {message}\n")
        except OSError:
            pass

    def startup(self, config_path, hotkey_display):
        """Print startup banner.

        Args:
            config_path: Path to the config file.
            hotkey_display: Display string for the hotkey.
        """
        if self.console_enabled:
            print("=" * 50, flush=True)
            print("SolomonVoice - Offline Voice to Text", flush=True)
            print("=" * 50, flush=True)
            print(f"Hotkey: {hotkey_display}", flush=True)
            print(f"Config: {config_path}", flush=True)
            print("Ready. Hold hotkey to record.", flush=True)
            print("Use the tray menu to pause or exit.", flush=True)
            print("=" * 50, flush=True)
        self._print(f"Started; dictation shortcut={hotkey_display}")
