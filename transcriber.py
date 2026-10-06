"""Private, local speech-to-text transcription using OpenAI Whisper."""

from __future__ import annotations

import re
import threading
import time
import numpy as np

from whisper_models import model_path


class UnsafeTranscriptionError(RuntimeError):
    """Raised when Whisper returns text that is unsafe to type automatically."""

    def __init__(self, message, transcript=""):
        super().__init__(message)
        self.transcript = transcript


def validate_transcript(text: str) -> str:
    """Block obvious decoder loops before they can be injected as keystrokes."""
    repeated_character = re.search(r"([^\s])\1{7,}", text, flags=re.IGNORECASE)
    repeated_word = re.search(r"\b([\w'-]+)(?:\s+\1){5,}\b", text, flags=re.IGNORECASE)
    if repeated_character or repeated_word:
        raise UnsafeTranscriptionError(
            "Whisper produced repeated text, so SolomonVoice blocked it instead of typing garbage. "
            "Open Session history to inspect or rerun the recording.",
            transcript=text,
        )
    return text


class Transcriber:
    """Lazily load Whisper once and transcribe in-memory audio."""

    def __init__(self, model_name="tiny", task="transcribe", model_directory=None):
        self.model_name = model_name
        self.task = task
        self.model_directory = model_directory
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

                checkpoint = model_path(self.model_name, self.model_directory)
                if not checkpoint.is_file():
                    raise RuntimeError(
                        f"The local Whisper model '{self.model_name}' is not installed. "
                        f"Install it in SolomonVoice Settings or place it in '{checkpoint.parent}'."
                    )
                # Loading by explicit path prevents Whisper from attempting a
                # network download during background dictation.
                self.model = whisper.load_model(str(checkpoint))
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
            # Whisper's temperature ladder retries segments whose compression
            # ratio or confidence indicates a decoder loop. A scalar zero
            # disabled that fallback and could produce long repeated letters.
            temperature=(0.0, 0.2, 0.4, 0.6, 0.8, 1.0),
            compression_ratio_threshold=2.4,
            logprob_threshold=-1.0,
            no_speech_threshold=0.6,
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
        return validate_transcript(text)
