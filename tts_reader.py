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


def time_compress_speech(samples, factor: float, sample_rate: int) -> np.ndarray:
    """Compress speech with waveform-similarity overlap-add while preserving pitch.

    Kokoro natively articulates speech up to 2x. This local WSOLA pass provides
    the remaining acceleration for advanced speeds without resampling away
    phonemes or raising the speaker's pitch.
    """
    audio = np.asarray(samples, dtype=np.float32).reshape(-1)
    factor = float(factor)
    if factor <= 1.001 or audio.size < 64:
        return audio.copy()

    window = max(64, int(sample_rate * 0.06))
    if window % 2:
        window += 1
    if audio.size <= window:
        indices = np.linspace(0, audio.size - 1, max(1, round(audio.size / factor)))
        return np.interp(indices, np.arange(audio.size), audio).astype(np.float32)

    overlap = window // 2
    synthesis_hop = window - overlap
    search = max(8, int(sample_rate * 0.01))
    estimated = max(window, round(audio.size / factor) + window * 2)
    output = np.zeros(estimated, dtype=np.float32)
    output[:window] = audio[:window]
    previous = audio[:window]
    analysis_position = 0
    synthesis_position = synthesis_hop
    fade = np.linspace(0.0, 1.0, overlap, endpoint=False, dtype=np.float32)

    while True:
        # Anchor each search to the ideal timeline so local alignment choices
        # cannot accumulate drift and clip the end of a long document.
        expected = round(synthesis_position * factor)
        earliest = max(0, expected - search)
        latest = min(audio.size - window, expected + search)
        if latest < earliest:
            break

        template = previous[-overlap:].astype(np.float64, copy=False)
        region = audio[earliest:latest + overlap].astype(np.float64, copy=False)
        correlations = np.correlate(region, template, mode="valid")
        squared = np.concatenate(([0.0], np.cumsum(region * region)))
        energies = squared[overlap:] - squared[:-overlap]
        template_energy = float(np.dot(template, template))
        scores = correlations / np.sqrt(np.maximum(template_energy * energies, 1e-12))
        analysis_position = earliest + int(np.argmax(scores))
        segment = audio[analysis_position:analysis_position + window]
        if segment.size < window:
            break

        required = synthesis_position + window
        if required > output.size:
            output = np.pad(output, (0, max(window * 2, required - output.size)))
        output[synthesis_position:synthesis_position + overlap] = (
            output[synthesis_position:synthesis_position + overlap] * (1.0 - fade)
            + segment[:overlap] * fade
        )
        output[synthesis_position + overlap:required] = segment[overlap:]
        previous = segment
        synthesis_position += synthesis_hop

        if analysis_position + window >= audio.size:
            break

    used = min(output.size, synthesis_position + window)
    target = max(1, round(audio.size / factor))
    return output[:min(used, target)].astype(np.float32, copy=False)


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
            # Kokoro's wrapper supports native articulation through 2x. Faster
            # settings synthesize at 2x, then use local pitch-preserving WSOLA.
            native_speed = min(self.speed, 2.0)
            post_speed = self.speed / native_speed
            high_speed_clarity = self.speed > 2.0
            for index, chunk in enumerate(chunks):
                if self._cancel.is_set() or (external_cancel and external_cancel.is_set()):
                    return False
                if on_progress:
                    on_progress(index + 1, len(chunks))
                samples, sample_rate = kokoro.create(
                    chunk,
                    voice=self.voice,
                    speed=native_speed,
                    lang=language,
                    continuous=high_speed_clarity,
                )
                audio = np.asarray(samples, dtype=np.float32)
                if post_speed > 1.001:
                    audio = time_compress_speech(audio, post_speed, int(sample_rate))
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
