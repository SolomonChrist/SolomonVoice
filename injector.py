"""Text injection via clipboard for cross-platform compatibility."""

import pyperclip
import pyautogui
import time


class Injector:
    """Injects text into the focused window using clipboard."""

    def __init__(self, append_space=True):
        """Initialize injector.

        Args:
            append_space: Whether to append a space to the transcribed text.
        """
        self.append_space = append_space

    def inject(self, text):
        """Inject text into the focused window.

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
            # Copy text to clipboard
            pyperclip.copy(text)
            # Wait for clipboard write to complete
            time.sleep(0.05)

            # Paste into focused window
            pyautogui.hotkey("ctrl", "v")
            # Wait for paste to complete
            time.sleep(0.1)

        except Exception as e:
            raise RuntimeError(f"Text injection failed: {e}")
        finally:
            # Always restore original clipboard
            try:
                pyperclip.copy(original_clipboard)
            except Exception:
                # If restore fails, continue anyway
                pass
