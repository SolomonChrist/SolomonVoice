from whisper_models import available_model_names, model_path, resolve_model_directory


def test_local_checkpoints_are_added_to_model_choices(tmp_path):
    (tmp_path / "custom-english.pt").write_bytes(b"checkpoint")
    (tmp_path / "ignore.txt").write_text("not a model", encoding="utf-8")

    names = available_model_names(tmp_path)

    assert names[0] == "tiny"
    assert "custom-english" in names
    assert "ignore" not in names


def test_pt_suffix_is_normalized_once(tmp_path):
    assert model_path("tiny.pt", tmp_path) == tmp_path / "tiny.pt"


def test_blank_directory_uses_whisper_default(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))

    assert resolve_model_directory("") == tmp_path / "whisper"
