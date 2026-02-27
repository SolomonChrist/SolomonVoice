"""Console and audio feedback for SolomonVoice."""

import winsound
import sys


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
        preview = text[:50] + "..." if len(text) > 50 else text
        self._print(f'Done: "{preview}"')

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
        """Print a message to console.

        Args:
            message: The message to print.
        """
        if self.console_enabled:
            print(f"[SolomonVoice] {message}", flush=True)

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
            print("Press Ctrl+C to exit.", flush=True)
            print("=" * 50, flush=True)
