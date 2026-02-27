"""Configuration loader with deep-merge defaults and validation."""

import json
import os
from pathlib import Path


DEFAULT_CONFIG = {
    "shortcut": {
        "key": "space",
        "modifiers": ["ctrl"],
    },
    "whisper": {
        "model": "base",
        "language": None,
        "task": "transcribe",
    },
    "audio": {
        "sample_rate": 16000,
        "channels": 1,
        "device": None,
    },
    "behavior": {
        "min_recording_seconds": 0.5,
        "max_recording_seconds": 30,
        "append_space": True,
        "suppress_hotkey": True,
    },
    "feedback": {
        "sound_enabled": True,
        "console_enabled": True,
    },
}


class Config:
    """Configuration loader and validator."""

    def __init__(self, config_path=None):
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
        self.data = self._load_config(config_path)

    def _load_config(self, path):
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

        with open(path, "r") as f:
            user_config = json.load(f)

        # Deep-merge user config with defaults
        merged = self._deep_merge(DEFAULT_CONFIG.copy(), user_config)
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

        # Validate whisper model
        valid_models = ["tiny", "base", "small", "medium", "large"]
        if config["whisper"]["model"] not in valid_models:
            raise ValueError(
                f"Invalid model: {config['whisper']['model']}. "
                f"Must be one of: {', '.join(valid_models)}"
            )

        # Validate audio sample rate
        if config["audio"]["sample_rate"] <= 0:
            raise ValueError("audio.sample_rate must be positive")

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
