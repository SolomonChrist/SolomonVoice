import threading

from tts_reader import TTSReader, chunk_text


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
