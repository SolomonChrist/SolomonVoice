import json

import pytest

from config import Config


def write_config(tmp_path, data):
    path = tmp_path / "config.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_defaults_do_not_leak_between_instances(tmp_path):
    first = Config(write_config(tmp_path, {"audio": {"device": 7}}))
    second_path = tmp_path / "second.json"
    second_path.write_text("{}", encoding="utf-8")
    second = Config(second_path)

    assert first.get("audio.device") == 7
    assert second.get("audio.device") is None


def test_english_only_models_are_supported(tmp_path):
    config = Config(write_config(tmp_path, {"whisper": {"model": "base.en"}}))
    assert config.get("whisper.model") == "base.en"


def test_unknown_modifier_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="Unsupported shortcut modifiers"):
        Config(write_config(tmp_path, {"shortcut": {"modifiers": ["hyper"]}}))
