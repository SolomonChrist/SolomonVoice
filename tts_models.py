"""Local Kokoro model metadata, storage, and explicit installation."""

from __future__ import annotations

import os
import shutil
import urllib.request
from pathlib import Path


DEFAULT_TTS_MODEL = "kokoro-v1.0-fp16"
MIN_READ_SPEED = 0.5
MAX_READ_SPEED = 5.0
VOICE_PACK_FILE = "voices-v1.0.bin"
RELEASE_ROOT = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1"

TTS_MODELS = {
    "kokoro-v1.0-fp16": {
        "filename": "kokoro-v1.0.fp16.onnx",
        "description": "Recommended · natural voices · about 164 MB",
    },
    "kokoro-v1.0-int8": {
        "filename": "kokoro-v1.0.int8.onnx",
        "description": "Smallest · lower fidelity · about 114 MB",
    },
    "kokoro-v1.0": {
        "filename": "kokoro-v1.0.onnx",
        "description": "Full precision · highest fidelity · about 326 MB",
    },
}

# Labels stay friendly while stable voice IDs are persisted in settings.
VOICE_CHOICES = (
    ("American · Heart (female)", "af_heart", "en-us"),
    ("American · Bella (female)", "af_bella", "en-us"),
    ("American · Nicole (female)", "af_nicole", "en-us"),
    ("American · Aoede (female)", "af_aoede", "en-us"),
    ("American · Kore (female)", "af_kore", "en-us"),
    ("American · Sarah (female)", "af_sarah", "en-us"),
    ("American · Nova (female)", "af_nova", "en-us"),
    ("American · Alloy (female)", "af_alloy", "en-us"),
    ("American · Jessica (female)", "af_jessica", "en-us"),
    ("American · River (female)", "af_river", "en-us"),
    ("American · Sky (female)", "af_sky", "en-us"),
    ("American · Fenrir (male)", "am_fenrir", "en-us"),
    ("American · Michael (male)", "am_michael", "en-us"),
    ("American · Puck (male)", "am_puck", "en-us"),
    ("American · Eric (male)", "am_eric", "en-us"),
    ("American · Liam (male)", "am_liam", "en-us"),
    ("American · Onyx (male)", "am_onyx", "en-us"),
    ("American · Echo (male)", "am_echo", "en-us"),
    ("American · Adam (male)", "am_adam", "en-us"),
    ("American · Santa (male)", "am_santa", "en-us"),
    ("British · Emma (female)", "bf_emma", "en-gb"),
    ("British · Isabella (female)", "bf_isabella", "en-gb"),
    ("British · Alice (female)", "bf_alice", "en-gb"),
    ("British · Lily (female)", "bf_lily", "en-gb"),
    ("British · Fable (male)", "bm_fable", "en-gb"),
    ("British · George (male)", "bm_george", "en-gb"),
    ("British · Daniel (male)", "bm_daniel", "en-gb"),
    ("British · Lewis (male)", "bm_lewis", "en-gb"),
    ("Japanese · Alpha (female)", "jf_alpha", "ja"),
    ("Japanese · Gongitsune (female)", "jf_gongitsune", "ja"),
    ("Japanese · Nezumi (female)", "jf_nezumi", "ja"),
    ("Japanese · Tebukuro (female)", "jf_tebukuro", "ja"),
    ("Japanese · Kumo (male)", "jm_kumo", "ja"),
    ("Mandarin · Xiaobei (female)", "zf_xiaobei", "zh"),
    ("Mandarin · Xiaoni (female)", "zf_xiaoni", "zh"),
    ("Mandarin · Xiaoxiao (female)", "zf_xiaoxiao", "zh"),
    ("Mandarin · Xiaoyi (female)", "zf_xiaoyi", "zh"),
    ("Mandarin · Yunjian (male)", "zm_yunjian", "zh"),
    ("Mandarin · Yunxi (male)", "zm_yunxi", "zh"),
    ("Mandarin · Yunxia (male)", "zm_yunxia", "zh"),
    ("Mandarin · Yunyang (male)", "zm_yunyang", "zh"),
    ("Spanish · Dora (female)", "ef_dora", "es"),
    ("Spanish · Alex (male)", "em_alex", "es"),
    ("Spanish · Santa (male)", "em_santa", "es"),
    ("French · Siwis (female)", "ff_siwis", "fr-fr"),
    ("Hindi · Alpha (female)", "hf_alpha", "hi"),
    ("Hindi · Beta (female)", "hf_beta", "hi"),
    ("Hindi · Omega (male)", "hm_omega", "hi"),
    ("Hindi · Psi (male)", "hm_psi", "hi"),
    ("Italian · Sara (female)", "if_sara", "it"),
    ("Italian · Nicola (male)", "im_nicola", "it"),
    ("Portuguese · Dora (female)", "pf_dora", "pt-br"),
    ("Portuguese · Alex (male)", "pm_alex", "pt-br"),
    ("Portuguese · Santa (male)", "pm_santa", "pt-br"),
)

VOICE_BY_LABEL = {label: (voice, language) for label, voice, language in VOICE_CHOICES}
VOICE_BY_ID = {voice: (label, language) for label, voice, language in VOICE_CHOICES}


def default_tts_directory() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "SolomonVoice" / "models" / "kokoro"
    return Path.home() / ".solomonvoice" / "models" / "kokoro"


def resolve_tts_directory(configured_directory=None) -> Path:
    if configured_directory is None or not str(configured_directory).strip():
        return default_tts_directory()
    expanded = os.path.expandvars(os.path.expanduser(str(configured_directory).strip()))
    return Path(expanded).absolute()


def validate_tts_model(model_name: str) -> str:
    name = str(model_name).strip()
    if name not in TTS_MODELS:
        raise ValueError(f"Unsupported read-aloud model: {name}")
    return name


def validate_voice(voice: str) -> str:
    value = str(voice).strip()
    if value not in VOICE_BY_ID:
        raise ValueError(f"Unsupported Kokoro voice: {value}")
    return value


def validate_speed(speed) -> float:
    value = float(speed)
    if not MIN_READ_SPEED <= value <= MAX_READ_SPEED:
        raise ValueError(
            f"read_aloud.speed must be between {MIN_READ_SPEED} and {MAX_READ_SPEED}"
        )
    return value


def model_file(model_name=DEFAULT_TTS_MODEL, configured_directory=None) -> Path:
    model = TTS_MODELS[validate_tts_model(model_name)]
    return resolve_tts_directory(configured_directory) / model["filename"]


def voices_file(configured_directory=None) -> Path:
    return resolve_tts_directory(configured_directory) / VOICE_PACK_FILE


def model_is_installed(model_name=DEFAULT_TTS_MODEL, configured_directory=None) -> bool:
    return model_file(model_name, configured_directory).is_file() and voices_file(configured_directory).is_file()


def _download(url: str, destination: Path, progress=None) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "SolomonVoice/2.3"})
        with urllib.request.urlopen(request, timeout=45) as response, open(temporary, "wb") as stream:
            total = int(response.headers.get("Content-Length", "0"))
            copied = 0
            while True:
                block = response.read(1024 * 1024)
                if not block:
                    break
                stream.write(block)
                copied += len(block)
                if progress:
                    progress(destination.name, copied, total)
            stream.flush()
            os.fsync(stream.fileno())
        if temporary.stat().st_size == 0:
            raise RuntimeError(f"Downloaded file is empty: {destination.name}")
        os.replace(temporary, destination)
    except Exception:
        try:
            temporary.unlink()
        except OSError:
            pass
        raise


def install_tts_model(model_name=DEFAULT_TTS_MODEL, configured_directory=None, progress=None) -> tuple[Path, Path]:
    """Download the selected ONNX graph and shared voice pack if missing."""
    directory = resolve_tts_directory(configured_directory)
    graph = model_file(model_name, directory)
    voices = voices_file(directory)
    if not graph.is_file():
        _download(f"{RELEASE_ROOT}/{graph.name}", graph, progress)
    if not voices.is_file():
        _download(f"{RELEASE_ROOT}/{voices.name}", voices, progress)
    return graph, voices


def move_installed_model(model_name, old_directory, new_directory) -> tuple[Path, Path]:
    """Copy an installed model pair to a user-selected folder without deleting the original."""
    source_graph = model_file(model_name, old_directory)
    source_voices = voices_file(old_directory)
    destination = resolve_tts_directory(new_directory)
    destination.mkdir(parents=True, exist_ok=True)
    target_graph = destination / source_graph.name
    target_voices = destination / source_voices.name
    if source_graph.is_file() and not target_graph.exists():
        shutil.copy2(source_graph, target_graph)
    if source_voices.is_file() and not target_voices.exists():
        shutil.copy2(source_voices, target_voices)
    return target_graph, target_voices
