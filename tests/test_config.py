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


def test_user_settings_override_defaults_and_save_atomically(tmp_path):
    base = write_config(tmp_path, {"audio": {"device": None}})
    user = tmp_path / "profile" / "settings.json"
    user.parent.mkdir()
    user.write_text(
        json.dumps({"audio": {"device": {"name": "Desk Mic", "hostapi": "WASAPI"}}}),
        encoding="utf-8",
    )

    config = Config(base, user_path=user)
    assert config.get("audio.device.name") == "Desk Mic"
    config.set("behavior.recording_mode", "toggle")
    config.save_user()

    saved = json.loads(user.read_text(encoding="utf-8"))
    assert saved["behavior"]["recording_mode"] == "toggle"
    assert not list(user.parent.glob("settings-*.tmp"))


def test_invalid_recording_mode_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="recording_mode"):
        Config(write_config(tmp_path, {"behavior": {"recording_mode": "always"}}))


def test_corrupt_user_settings_are_quarantined_and_defaults_load(tmp_path):
    base = write_config(tmp_path, {"shortcut": {"key": "f9", "modifiers": ["ctrl"]}})
    user = tmp_path / "profile" / "settings.json"
    user.parent.mkdir()
    user.write_text("{not json", encoding="utf-8")

    config = Config(base, user_path=user)

    assert config.get("shortcut.key") == "f9"
    assert config.load_warning
    assert not user.exists()
    assert list(user.parent.glob("settings.invalid-*.json"))
