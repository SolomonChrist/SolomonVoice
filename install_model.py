"""Explicit one-time Whisper model acquisition for offline runtime use."""

import argparse
from pathlib import Path

import whisper

from config import Config
from whisper_models import DEFAULT_MODEL, OFFICIAL_MODELS, resolve_model_directory


def main():
    parser = argparse.ArgumentParser(description="Download and verify a SolomonVoice Whisper model")
    parser.add_argument(
        "model",
        nargs="?",
        help=f"Model name; defaults to {DEFAULT_MODEL}, the smallest and fastest starter model",
    )
    parser.add_argument("--model-dir", help="Folder where the downloaded .pt model should be stored")
    args = parser.parse_args()
    config = Config(
        Path(__file__).parent / "solomonvoice_config.json",
        user_path=Config.default_user_path(),
    )
    model_name = args.model or config.get("whisper.model", DEFAULT_MODEL)
    if model_name not in OFFICIAL_MODELS:
        parser.error("Only official Whisper model names can be downloaded by the installer")
    model_directory = resolve_model_directory(args.model_dir or config.get("whisper.model_directory"))
    model_directory.mkdir(parents=True, exist_ok=True)
    print(f"Installing Whisper model '{model_name}' into '{model_directory}'...")
    whisper.load_model(model_name, download_root=str(model_directory))
    print(f"Model '{model_name}' is installed. SolomonVoice can now transcribe offline.")


if __name__ == "__main__":
    main()
