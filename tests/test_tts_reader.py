import threading

import numpy as np

from tts_reader import TTSReader, chunk_text, time_compress_speech


def test_chunk_text_preserves_all_sentences_in_order():
    source = "First sentence. Second sentence!\nThird sentence?"
    chunks = chunk_text(source, target=25, maximum=100)

    assert chunks == ["First sentence.", "Second sentence!", "Third sentence?"]


def test_stop_sets_cancel_even_before_model_load(monkeypatch):
    stopped = []
    monkeypatch.setattr("tts_reader.sd.stop", lambda: stopped.append(True))
    reader = TTSReader("kokoro-v1.0-fp16", "models")

    reader.stop()

    assert reader._cancel.is_set()
    assert stopped == [True]


def test_external_cancel_prevents_synthesis(monkeypatch):
    reader = TTSReader("kokoro-v1.0-fp16", "models")
    model = type("FakeModel", (), {"create": lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError())})()
    monkeypatch.setattr(reader, "_load", lambda: model)
    cancel = threading.Event()
    cancel.set()

    assert reader.speak("This must not be synthesized.", cancel) is False


def test_advanced_speed_uses_native_continuous_synthesis(monkeypatch):
    calls = []

    class FakeModel:
        def create(self, text, **kwargs):
            calls.append((text, kwargs))
            return np.zeros(32, dtype=np.float32), 24000

    class FinishedStream:
        active = False

    reader = TTSReader("kokoro-v1.0-fp16", "models", speed=5.0)
    monkeypatch.setattr(reader, "_load", lambda: FakeModel())
    monkeypatch.setattr("tts_reader.sd.play", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("tts_reader.sd.get_stream", lambda: FinishedStream())

    assert reader.speak("Fast, clear, and articulated.") is True
    assert calls[0][1]["speed"] == 2.0
    assert calls[0][1]["continuous"] is True


def test_time_compression_preserves_pitch_and_shortens_audio():
    sample_rate = 24000
    source = np.sin(2 * np.pi * 220 * np.arange(sample_rate) / sample_rate).astype(np.float32)

    compressed = time_compress_speech(source, 2.5, sample_rate)

    assert len(compressed) == round(len(source) / 2.5)
    assert np.isfinite(compressed).all()
    zero_crossings = np.flatnonzero(np.diff(np.signbit(compressed)))
    estimated_frequency = len(zero_crossings) * sample_rate / (2 * len(compressed))
    assert 200 <= estimated_frequency <= 240
