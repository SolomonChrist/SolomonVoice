"""Whisper model names and local storage paths used by SolomonVoice."""

from __future__ import annotations

import os
import re
from pathlib import Path


DEFAULT_MODEL = "tiny"
OFFICIAL_MODELS = (
    "tiny",
    "tiny.en",
    "base",
    "base.en",
    "small",
    "small.en",
    "medium",
    "medium.en",
    "large",
    "large-v2",
    "large-v3",
    "turbo",
)

MODEL_DESCRIPTIONS = {
    "tiny": "Fastest · multilingual · about 75 MB",
    "tiny.en": "Fastest · English only · about 75 MB",
    "base": "Fast · multilingual · about 145 MB",
    "base.en": "Fast · English only · about 145 MB",
    "small": "Balanced · multilingual · about 460 MB",
    "small.en": "Balanced · English only · about 460 MB",
    "medium": "More accurate · multilingual · about 1.5 GB",
    "medium.en": "More accurate · English only · about 1.5 GB",
    "large": "Highest accuracy · multilingual · about 2.9 GB",
    "large-v2": "Highest accuracy · multilingual · about 2.9 GB",
    "large-v3": "Highest accuracy · multilingual · about 2.9 GB",
    "turbo": "Fast large model · multilingual · about 1.6 GB",
}

_SAFE_MODEL_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def default_model_directory() -> Path:
    """Return the directory used by OpenAI Whisper when no override is set."""
    cache_root = Path(os.getenv("XDG_CACHE_HOME", Path.home() / ".cache"))
    return cache_root / "whisper"


def resolve_model_directory(configured_directory=None) -> Path:
    """Expand a configured model directory or return Whisper's default cache."""
    if configured_directory is None or not str(configured_directory).strip():
        return default_model_directory()
    expanded = os.path.expandvars(os.path.expanduser(str(configured_directory).strip()))
    return Path(expanded).absolute()


def validate_model_name(model_name: str) -> str:
    """Accept official names and safe local Whisper-compatible checkpoint stems."""
    name = str(model_name).strip()
    if name.lower().endswith(".pt"):
        name = name[:-3]
    if not name or not _SAFE_MODEL_NAME.fullmatch(name) or name in {".", ".."}:
        raise ValueError("Whisper model must be a safe model name without a folder path")
    return name


def model_path(model_name: str, configured_directory=None) -> Path:
    """Return the expected local checkpoint path for a model name."""
    return resolve_model_directory(configured_directory) / f"{validate_model_name(model_name)}.pt"


def available_model_names(configured_directory=None, selected=None) -> tuple[str, ...]:
    """List official choices followed by compatible local .pt checkpoint names."""
    names = list(OFFICIAL_MODELS)
    directory = resolve_model_directory(configured_directory)
    local_names = []
    try:
        for item in directory.glob("*.pt"):
            if not item.is_file():
                continue
            try:
                local_names.append(validate_model_name(item.stem))
            except ValueError:
                continue
        local_names.sort()
    except OSError:
        local_names = []
    for name in local_names:
        if name not in names:
            names.append(name)
    if selected:
        name = validate_model_name(selected)
        if name not in names:
            names.append(name)
    return tuple(names)
