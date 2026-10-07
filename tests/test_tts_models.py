from tts_models import (
    DEFAULT_TTS_MODEL,
    TTS_MODELS,
    VOICE_BY_ID,
    VOICE_CHOICES,
    model_file,
    model_is_installed,
    validate_tts_model,
    validate_voice,
    voices_file,
)


def test_default_model_is_recommended_fp16(tmp_path):
    assert DEFAULT_TTS_MODEL == "kokoro-v1.0-fp16"
    assert model_file(DEFAULT_TTS_MODEL, tmp_path).name == "kokoro-v1.0.fp16.onnx"
    assert TTS_MODELS[DEFAULT_TTS_MODEL]["filename"].endswith(".fp16.onnx")


def test_model_install_requires_graph_and_voice_pack(tmp_path):
    model_file(DEFAULT_TTS_MODEL, tmp_path).write_bytes(b"graph")
    assert not model_is_installed(DEFAULT_TTS_MODEL, tmp_path)
    voices_file(tmp_path).write_bytes(b"voices")
    assert model_is_installed(DEFAULT_TTS_MODEL, tmp_path)


def test_voice_ids_include_recommended_english_voice():
    assert VOICE_BY_ID[validate_voice("af_heart")][1] == "en-us"
    assert len(VOICE_CHOICES) == 54


def test_unknown_tts_model_and_voice_are_rejected():
    import pytest

    with pytest.raises(ValueError):
        validate_tts_model("some-model-from-a-folder")
    with pytest.raises(ValueError):
        validate_voice("unknown_voice")
