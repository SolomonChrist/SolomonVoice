"""Entry point for SolomonVoice - Offline Voice to Text."""

import sys
import signal
import time
from pathlib import Path

from config import Config
from feedback import Feedback
from listener_v2 import ListenerV2


def main():
    """Main entry point."""
    # Load configuration
    try:
        config_path = Path(__file__).parent / "solomonvoice_config.json"
        config = Config(config_path)
    except FileNotFoundError as e:
        print(f"Fatal: {e}", file=sys.stderr)
        print("Ensure solomonvoice_config.json exists in the SolomonVoice directory.", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Fatal: Failed to load config: {e}", file=sys.stderr)
        sys.exit(1)

    # Initialize feedback handler
    feedback = Feedback(
        sound_enabled=config.get("feedback.sound_enabled"),
        console_enabled=config.get("feedback.console_enabled"),
    )

    # Initialize listener (using improved V2 version)
    try:
        listener = ListenerV2(config, feedback)
    except Exception as e:
        feedback.error(f"Failed to initialize: {e}")
        sys.exit(1)

    # Print startup banner
    feedback.startup(config_path, listener.hotkey_display())

    # Start listener
    try:
        listener.start()
    except Exception as e:
        feedback.error(f"Failed to start listener: {e}")
        sys.exit(1)

    # Handle Ctrl+C gracefully
    def signal_handler(sig, frame):
        """Handle Ctrl+C to stop listener."""
        listener.stop()
        if config.get("feedback.console_enabled"):
            print("\n[SolomonVoice] Shutting down...", flush=True)
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)

    # Keep running (signal.pause() doesn't work on Windows, so we use a loop)
    try:
        while True:
            time.sleep(0.1)  # Sleep to avoid busy-waiting
    except KeyboardInterrupt:
        listener.stop()
        if config.get("feedback.console_enabled"):
            print("\n[SolomonVoice] Shutting down...", flush=True)
        sys.exit(0)


if __name__ == "__main__":
    main()
