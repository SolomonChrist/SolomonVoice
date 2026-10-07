"""Cancelable, local Kokoro text-to-speech playback."""

from __future__ import annotations

import re
import threading

import numpy as np
import sounddevice as sd

from tts_models import VOICE_BY_ID, model_file, voices_file


def chunk_text(text: str, target=650, maximum=1000) -> list[str]:
    """Create natural chunks while avoiding Kokoro's weak very-long utterances."""
    paragraphs = [part.strip() for part in re.split(r"\n+", text) if part.strip()]
    chunks = []
    current = ""
    for paragraph in paragraphs:
        sentences = re.split(r"(?<=[.!?])\s+", paragraph)
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            if len(sentence) > maximum:
                pieces = [sentence[index:index + maximum] for index in range(0, len(sentence), maximum)]
            else:
                pieces = [sentence]
            for piece in pieces:
                candidate = f"{current} {piece}".strip()
                if current and len(candidate) > target:
                    chunks.append(current)
                    current = piece
                else:
                    current = candidate
    if current:
        chunks.append(current)
    return chunks


class TTSReader:
    """Lazy-load one local Kokoro session and serialize synthesis/playback."""

    def __init__(self, model_name, model_directory, voice="af_heart", speed=1.0, output_device=None):
        self.model_name = model_name
        self.model_directory = model_directory
        self.voice = voice
        self.speed = float(speed)
        self.output_device = output_device
        self._kokoro = None
        self._lock = threading.Lock()
        self._cancel = threading.Event()

    def validate_files(self) -> None:
        graph = model_file(self.model_name, self.model_directory)
        voices = voices_file(self.model_directory)
        missing = [str(path) for path in (graph, voices) if not path.is_file()]
        if missing:
            raise RuntimeError("Read Aloud model is not installed. Missing: " + ", ".join(missing))

    def _load(self):
        if self._kokoro is not None:
            return self._kokoro
        self.validate_files()
        try:
            import onnxruntime
            from kokoro_onnx import Kokoro
        except ImportError as exc:
            raise RuntimeError("Read Aloud dependencies are not installed; run the SolomonVoice setup again") from exc

        options = onnxruntime.SessionOptions()
        options.intra_op_num_threads = max(1, min(8, __import__("os").cpu_count() or 1))
        options.log_severity_level = 3
        session = onnxruntime.InferenceSession(
            str(model_file(self.model_name, self.model_directory)),
            providers=["CPUExecutionProvider"],
            sess_options=options,
        )
        self._kokoro = Kokoro.from_session(session, str(voices_file(self.model_directory)))
        return self._kokoro

    def stop(self) -> None:
        self._cancel.set()
        try:
            sd.stop()
        except Exception:
            pass

    def speak(self, text: str, external_cancel=None, on_progress=None) -> bool:
        """Speak text synchronously; return False when canceled."""
        with self._lock:
            self._cancel.clear()
            kokoro = self._load()
            chunks = chunk_text(text)
            language = VOICE_BY_ID[self.voice][1]
            for index, chunk in enumerate(chunks):
                if self._cancel.is_set() or (external_cancel and external_cancel.is_set()):
                    return False
                if on_progress:
                    on_progress(index + 1, len(chunks))
                samples, sample_rate = kokoro.create(
                    chunk,
                    voice=self.voice,
                    speed=self.speed,
                    lang=language,
                )
                audio = np.asarray(samples, dtype=np.float32)
                sd.play(audio, int(sample_rate), device=self.output_device, blocking=False)
                while True:
                    if self._cancel.wait(0.05) or (external_cancel and external_cancel.is_set()):
                        sd.stop()
                        return False
                    try:
                        if not sd.get_stream().active:
                            break
                    except Exception:
                        break
            return True
