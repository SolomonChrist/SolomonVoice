"""Configuration loading, validation, and per-user persistence."""

import copy
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from whisper_models import DEFAULT_MODEL, validate_model_name
from tts_models import DEFAULT_TTS_MODEL, validate_speed, validate_tts_model, validate_voice


DEFAULT_CONFIG = {
    "shortcut": {
        "key": "space",
        "modifiers": ["ctrl"],
    },
    "whisper": {
        "model": DEFAULT_MODEL,
        "model_directory": None,
        "language": None,
        "task": "transcribe",
    },
    "read_aloud": {
        "enabled": True,
        "shortcut": {
            "key": "space",
            "modifiers": ["ctrl", "shift"],
        },
        "model": DEFAULT_TTS_MODEL,
        "model_directory": None,
        "voice": "af_heart",
        "speed": 1.0,
        "read_full_document": True,
        "max_characters": 100000,
        "output_device": None,
    },
    "audio": {
        "sample_rate": 16000,
        "channels": 1,
        "device": None,
        "silence_rms": 0.003,
    },
    "behavior": {
        "min_recording_seconds": 0.5,
        "max_recording_seconds": 30,
        "append_space": True,
        "require_same_window": True,
        "recording_mode": "hold",
        "escape_to_cancel": True,
        "start_with_windows": False,
    },
    "visual": {
        "enabled": True,
        "position": "bottom",
        "reduced_motion": False,
    },
    "feedback": {
        "sound_enabled": True,
        "console_enabled": True,
    },
}


class Config:
    """Configuration loader and validator."""

    def __init__(self, config_path=None, user_path=None):
        """Load configuration from file, with defaults.

        Args:
            config_path: Path to solomonvoice_config.json. Defaults to
                        solomonvoice_config.json in the script directory.
        """
        if config_path is None:
            config_path = Path(__file__).parent / "solomonvoice_config.json"
        else:
            config_path = Path(config_path)

        self.config_path = config_path
        self.user_path = Path(user_path) if user_path else None
        self.load_warning = None
        self.base_data = self._load_config(config_path)
        try:
            self.data = self._load_config(config_path, self.user_path)
        except (json.JSONDecodeError, ValueError, OSError) as exc:
            if not self.user_path or not self.user_path.exists():
                raise
            quarantine = self.user_path.with_name(
                f"{self.user_path.stem}.invalid-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}{self.user_path.suffix}"
            )
            try:
                self.user_path.replace(quarantine)
                location = f" It was moved to {quarantine}."
            except OSError:
                location = " It could not be moved; fix or remove it before saving new preferences."
            self.load_warning = f"Your saved settings were invalid, so product defaults were restored.{location} ({exc})"
            self.data = copy.deepcopy(self.base_data)

    @staticmethod
    def default_user_path():
        """Return the writable per-user settings file used by the desktop app."""
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            return Path(local_app_data) / "SolomonVoice" / "settings.json"
        return Path.home() / ".solomonvoice" / "settings.json"

    def _load_config(self, path, user_path=None):
        """Load and validate config file.

        Args:
            path: Path to config file.

        Returns:
            Merged config dict (user config + defaults).

        Raises:
            FileNotFoundError: If config file doesn't exist.
            json.JSONDecodeError: If config file is invalid JSON.
        """
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")

        with open(path, "r", encoding="utf-8") as f:
            user_config = json.load(f)

        # The checked-in file provides product defaults. A per-user file keeps
        # machine-specific microphone and shortcut choices out of the repo.
        merged = self._deep_merge(copy.deepcopy(DEFAULT_CONFIG), user_config)
        if user_path and user_path.exists():
            with open(user_path, "r", encoding="utf-8") as f:
                merged = self._deep_merge(merged, json.load(f))
        self._validate(merged)
        return merged

    def _deep_merge(self, defaults, user_config):
        """Recursively merge user config into defaults.

        Args:
            defaults: Default configuration dict.
            user_config: User-provided configuration dict.

        Returns:
            Merged configuration dict.
        """
        for key, value in user_config.items():
            if key in defaults and isinstance(defaults[key], dict) and isinstance(value, dict):
                defaults[key] = self._deep_merge(defaults[key], value)
            else:
                defaults[key] = value
        return defaults

    def _validate(self, config):
        """Validate configuration values.

        Args:
            config: Configuration dict.

        Raises:
            ValueError: If config is invalid.
        """
        # Validate shortcut
        if not config["shortcut"]["key"]:
            raise ValueError("shortcut.key cannot be empty")
        if not config["read_aloud"]["shortcut"]["key"]:
            raise ValueError("read_aloud.shortcut.key cannot be empty")

        # Official model names and safe local Whisper-compatible .pt stems are
        # supported. Folder traversal is rejected independently of the folder.
        config["whisper"]["model"] = validate_model_name(config["whisper"]["model"])
        model_directory = config["whisper"].get("model_directory")
        if model_directory is not None and (
            not isinstance(model_directory, str) or not model_directory.strip()
        ):
            raise ValueError("whisper.model_directory must be null or a non-empty folder path")

        config["read_aloud"]["model"] = validate_tts_model(config["read_aloud"]["model"])
        config["read_aloud"]["voice"] = validate_voice(config["read_aloud"]["voice"])
        config["read_aloud"]["speed"] = validate_speed(config["read_aloud"]["speed"])
        tts_directory = config["read_aloud"].get("model_directory")
        if tts_directory is not None and (
            not isinstance(tts_directory, str) or not tts_directory.strip()
        ):
            raise ValueError("read_aloud.model_directory must be null or a non-empty folder path")
        if not isinstance(config["read_aloud"].get("read_full_document"), bool):
            raise ValueError("read_aloud.read_full_document must be true or false")
        max_characters = config["read_aloud"].get("max_characters", 100000)
        if not isinstance(max_characters, int) or not 1000 <= max_characters <= 1000000:
            raise ValueError("read_aloud.max_characters must be between 1000 and 1000000")

        # Validate audio sample rate
        if config["audio"]["sample_rate"] <= 0:
            raise ValueError("audio.sample_rate must be positive")
        if config["audio"]["channels"] != 1:
            raise ValueError("audio.channels must be 1 (mono)")
        if config["audio"]["silence_rms"] < 0:
            raise ValueError("audio.silence_rms cannot be negative")

        valid_modifiers = {"ctrl", "control", "alt", "shift", "win", "windows"}
        invalid_modifiers = set(config["shortcut"]["modifiers"]) - valid_modifiers
        if invalid_modifiers:
            raise ValueError(f"Unsupported shortcut modifiers: {sorted(invalid_modifiers)}")
        invalid_read_modifiers = set(config["read_aloud"]["shortcut"]["modifiers"]) - valid_modifiers
        if invalid_read_modifiers:
            raise ValueError(f"Unsupported read-aloud shortcut modifiers: {sorted(invalid_read_modifiers)}")
        dictation_chord = (
            config["shortcut"]["key"].lower(),
            frozenset(item.lower() for item in config["shortcut"]["modifiers"]),
        )
        reading_chord = (
            config["read_aloud"]["shortcut"]["key"].lower(),
            frozenset(item.lower() for item in config["read_aloud"]["shortcut"]["modifiers"]),
        )
        if config["read_aloud"].get("enabled", True) and dictation_chord == reading_chord:
            raise ValueError("Dictation and Read Aloud shortcuts must be different")

        if config["whisper"]["task"] not in {"transcribe", "translate"}:
            raise ValueError("whisper.task must be 'transcribe' or 'translate'")

        device = config["audio"]["device"]
        if device is not None and not isinstance(device, (int, str, dict)):
            raise ValueError("audio.device must be null, a device index, name, or identity object")
        if isinstance(device, dict) and not device.get("name"):
            raise ValueError("audio.device identity must include a name")

        if config["behavior"]["recording_mode"] not in {"hold", "toggle"}:
            raise ValueError("behavior.recording_mode must be 'hold' or 'toggle'")

        # Validate behavior limits
        min_sec = config["behavior"]["min_recording_seconds"]
        max_sec = config["behavior"]["max_recording_seconds"]
        if min_sec < 0 or max_sec < 0:
            raise ValueError("Recording time limits must be non-negative")
        if min_sec >= max_sec:
            raise ValueError("min_recording_seconds must be < max_recording_seconds")

    def get(self, key, default=None):
        """Get a config value using dot notation (e.g., 'whisper.model').

        Args:
            key: Config key with optional dot notation.
            default: Default value if key not found.

        Returns:
            Config value or default.
        """
        keys = key.split(".")
        value = self.data
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        return value

    def __getitem__(self, key):
        """Get config section by key (e.g., config['whisper']).

        Args:
            key: Top-level config key.

        Returns:
            Config section dict.
        """
        return self.data.get(key, {})

    def replace(self, new_data):
        """Validate and replace the in-memory settings as one transaction."""
        self.data = self.validated(new_data)

    def validated(self, new_data):
        """Return a normalized, validated snapshot without mutating settings."""
        candidate = self._deep_merge(copy.deepcopy(DEFAULT_CONFIG), copy.deepcopy(new_data))
        self._validate(candidate)
        return candidate

    def set(self, key, value):
        """Set one dot-separated value after validating the complete config."""
        candidate = copy.deepcopy(self.data)
        target = candidate
        parts = key.split(".")
        for part in parts[:-1]:
            target = target.setdefault(part, {})
        target[parts[-1]] = value
        self.replace(candidate)

    def save_user(self):
        """Atomically save current settings to the per-user file."""
        if self.user_path is None:
            raise RuntimeError("No per-user settings path is configured")
        self.user_path.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary_name = tempfile.mkstemp(
            prefix="settings-",
            suffix=".tmp",
            dir=self.user_path.parent,
            text=True,
        )
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                json.dump(self._deep_diff(self.base_data, self.data), stream, indent=2, ensure_ascii=False)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_name, self.user_path)
        except Exception:
            try:
                os.unlink(temporary_name)
            except OSError:
                pass
            raise

    def _deep_diff(self, baseline, current):
        """Return only values that differ from checked-in product defaults."""
        result = {}
        for key, value in current.items():
            if key not in baseline:
                result[key] = copy.deepcopy(value)
            elif isinstance(value, dict) and isinstance(baseline[key], dict):
                nested = self._deep_diff(baseline[key], value)
                if nested:
                    result[key] = nested
            elif value != baseline[key]:
                result[key] = copy.deepcopy(value)
        return result
