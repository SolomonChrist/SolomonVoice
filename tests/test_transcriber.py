import numpy as np
import sys
from types import SimpleNamespace

import pytest

from transcriber import Transcriber


class FakeModel:
    def __init__(self, text):
        self.text = text
        self.kwargs = None

    def transcribe(self, audio, **kwargs):
        self.kwargs = kwargs
        assert audio.dtype == np.float32
        assert audio.ndim == 1
        return {"text": self.text}


def test_transcriber_uses_in_memory_audio_and_preserves_dictated_brackets():
    transcriber = Transcriber("tiny", "transcribe")
    transcriber.model = FakeModel(" Keep [this] [MUSIC] ")

    result = transcriber.transcribe(np.ones((4, 1), dtype=np.float64), language="en")

    assert result == "Keep [this]"
    assert transcriber.model.kwargs["condition_on_previous_text"] is False
    assert transcriber.model.kwargs["task"] == "transcribe"


def test_missing_cache_fails_closed_without_calling_whisper(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    monkeypatch.setitem(sys.modules, "whisper", SimpleNamespace(load_model=lambda path: calls.append(path)))

    with pytest.raises(RuntimeError, match="not installed"):
        Transcriber("tiny").warm_up()

    assert calls == []


def test_cached_model_is_loaded_by_local_path(monkeypatch, tmp_path):
    model_dir = tmp_path / "whisper"
    model_dir.mkdir()
    model_path = model_dir / "tiny.pt"
    model_path.write_bytes(b"trusted installer output")
    loaded = object()
    calls = []
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))

    def load_model(path):
        calls.append(path)
        return loaded

    monkeypatch.setitem(sys.modules, "whisper", SimpleNamespace(load_model=load_model))
    transcriber = Transcriber("tiny")

    transcriber.warm_up()

    assert transcriber.model is loaded
    assert calls == [str(model_path)]


def test_configured_model_directory_is_used(monkeypatch, tmp_path):
    model_dir = tmp_path / "models"
    model_dir.mkdir()
    checkpoint = model_dir / "custom-english.pt"
    checkpoint.write_bytes(b"trusted local checkpoint")
    calls = []
    loaded = object()
    monkeypatch.setitem(
        sys.modules,
        "whisper",
        SimpleNamespace(load_model=lambda path: calls.append(path) or loaded),
    )

    transcriber = Transcriber("custom-english", model_directory=str(model_dir))
    transcriber.warm_up()

    assert transcriber.model is loaded
    assert calls == [str(checkpoint)]
