"""Offline speech-to-text transcription using OpenAI Whisper."""

import whisper
import re


class Transcriber:
    """Handles Whisper model loading and transcription."""

    def __init__(self, model_name="base"):
        """Load Whisper model.

        Args:
            model_name: Model size (tiny, base, small, medium, large).
        """
        self.model = whisper.load_model(model_name)
        self.model_name = model_name

    def transcribe(self, audio_path, language=None):
        """Transcribe audio file offline.

        Args:
            audio_path: Path to the audio file (WAV, MP3, etc.).
            language: Language code (e.g., 'en'). None for auto-detect.

        Returns:
            Transcribed text (stripped), or empty string if silent/noise.

        Raises:
            Exception: On Whisper errors (re-raised to caller).
        """
        try:
            result = self.model.transcribe(
                audio_path,
                language=language,
                fp16=False,  # Critical: use fp32 for CPU
            )
            text = result["text"].strip()

            # Remove common silence/noise markers
            text = re.sub(r"\[.*?\]", "", text).strip()

            return text
        except Exception as e:
            raise RuntimeError(f"Transcription error: {e}")
