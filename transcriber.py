"""Private, local speech-to-text transcription using OpenAI Whisper."""

from __future__ import annotations

import re
import threading
import time
import os
from pathlib import Path

import numpy as np


class Transcriber:
    """Lazily load Whisper once and transcribe in-memory audio."""

    def __init__(self, model_name="base", task="transcribe"):
        self.model_name = model_name
        self.task = task
        self.model = None
        self._model_lock = threading.Lock()

    def warm_up(self) -> None:
        """Load the configured model; safe to call from a background thread."""
        self._get_model()

    def _get_model(self):
        if self.model is not None:
            return self.model
        with self._model_lock:
            if self.model is None:
                import whisper

                default_cache = Path(os.getenv("XDG_CACHE_HOME", Path.home() / ".cache"))
                model_path = default_cache / "whisper" / f"{self.model_name}.pt"
                if not model_path.is_file():
                    raise RuntimeError(
                        f"The local Whisper model '{self.model_name}' is not installed. "
                        "Run 'py install_model.py' once during setup."
                    )
                # Loading by explicit path prevents Whisper from attempting a
                # network download during background dictation.
                self.model = whisper.load_model(str(model_path))
        return self.model

    def transcribe(self, audio: np.ndarray, language=None) -> str:
        """Transcribe mono 16 kHz float audio without writing speech to disk."""
        start_time = time.monotonic()
        model = self._get_model()
        result = model.transcribe(
            np.asarray(audio, dtype=np.float32).reshape(-1),
            language=language,
            task=self.task,
            fp16=False,
            temperature=0,
            condition_on_previous_text=False,
        )
        text = result.get("text", "").strip()
        text = re.sub(
            r"\[(?:music|applause|laughter|silence|inaudible)\]",
            "",
            text,
            flags=re.IGNORECASE,
        ).strip()
        elapsed = time.monotonic() - start_time
        print(f"[SolomonVoice] Transcription complete in {elapsed:.1f}s", flush=True)
        return text
