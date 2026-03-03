"""Text injection via clipboard for cross-platform compatibility."""

import pyperclip
import pyautogui
import time
import subprocess


class Injector:
    """Injects text into the focused window using clipboard."""

    def __init__(self, append_space=True):
        """Initialize injector.

        Args:
            append_space: Whether to append a space to the transcribed text.
        """
        self.append_space = append_space

    def inject(self, text):
        """Inject text into the focused window via clipboard and Ctrl+V.

        Args:
            text: The text to inject.

        Raises:
            RuntimeError: If injection fails.
        """
        if not text:
            raise ValueError("Cannot inject empty text")

        # Add space if configured
        if self.append_space:
            text = text + " "

        # Save original clipboard
        try:
            original_clipboard = pyperclip.paste()
        except Exception as e:
            raise RuntimeError(f"Failed to read clipboard: {e}")

        try:
            print(f"[SolomonVoice] Injecting via clipboard: {repr(text)}", flush=True)

            # Copy to clipboard
            pyperclip.copy(text)
            time.sleep(0.2)

            # Use pyautogui for more reliable Ctrl+V
            print(f"[SolomonVoice] Sending Ctrl+V...", flush=True)
            pyautogui.hotkey('ctrl', 'v')
            time.sleep(0.3)

            print(f"[SolomonVoice] Text injection complete", flush=True)

        except Exception as e:
            print(f"[SolomonVoice] Injection error: {e}", flush=True)
            raise RuntimeError(f"Text injection failed: {e}")
        finally:
            # Always restore original clipboard
            try:
                time.sleep(0.1)
                pyperclip.copy(original_clipboard)
                print(f"[SolomonVoice] Clipboard restored", flush=True)
            except Exception as e:
                print(f"[SolomonVoice] Warning: Could not restore clipboard: {e}", flush=True)
