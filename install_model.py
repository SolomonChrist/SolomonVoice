"""Explicit first-time acquisition of both offline SolomonVoice models."""

import argparse
from pathlib import Path

import whisper

from config import Config
from whisper_models import DEFAULT_MODEL, OFFICIAL_MODELS, resolve_model_directory
from tts_models import DEFAULT_TTS_MODEL, TTS_MODELS, install_tts_model, resolve_tts_directory


def main():
    parser = argparse.ArgumentParser(description="Install SolomonVoice's offline transcription and Read Aloud models")
    parser.add_argument(
        "model",
        nargs="?",
        help=f"Model name; defaults to {DEFAULT_MODEL}, the smallest and fastest starter model",
    )
    parser.add_argument("--model-dir", help="Folder where the downloaded .pt model should be stored")
    parser.add_argument("--tts-model", choices=tuple(TTS_MODELS), help="Kokoro model; defaults to the recommended FP16 model")
    parser.add_argument("--tts-model-dir", help="Folder where Kokoro and its voice pack should be stored")
    parser.add_argument("--whisper-only", action="store_true", help="Install only the Whisper model")
    parser.add_argument("--tts-only", action="store_true", help="Install only the Kokoro model and voice pack")
    args = parser.parse_args()
    config = Config(
        Path(__file__).parent / "solomonvoice_config.json",
        user_path=Config.default_user_path(),
    )
    if args.whisper_only and args.tts_only:
        parser.error("Choose either --whisper-only or --tts-only, not both")

    if not args.tts_only:
        model_name = args.model or config.get("whisper.model", DEFAULT_MODEL)
        if model_name not in OFFICIAL_MODELS:
            parser.error("Only official Whisper model names can be downloaded by the installer")
        model_directory = resolve_model_directory(args.model_dir or config.get("whisper.model_directory"))
        model_directory.mkdir(parents=True, exist_ok=True)
        print(f"Installing Whisper model '{model_name}' into '{model_directory}'...")
        loaded = whisper.load_model(model_name, download_root=str(model_directory))
        del loaded
        print(f"Whisper '{model_name}' is installed.")

    if not args.whisper_only:
        tts_name = args.tts_model or config.get("read_aloud.model", DEFAULT_TTS_MODEL)
        tts_directory = resolve_tts_directory(args.tts_model_dir or config.get("read_aloud.model_directory"))

        last_percent = {}

        def progress(filename, copied, total):
            percent = copied * 100 // total if total else copied // (1024 * 1024)
            if last_percent.get(filename) != percent and (not total or percent % 5 == 0):
                suffix = f"{percent}%" if total else f"{percent} MB"
                print(f"  {filename}: {suffix}")
                last_percent[filename] = percent

        print(f"Installing Read Aloud model '{tts_name}' into '{tts_directory}'...")
        graph, voices = install_tts_model(tts_name, tts_directory, progress)
        print(f"Kokoro is installed: {graph.name} + {voices.name}")

    print("Setup complete. SolomonVoice can now dictate and read aloud without an internet connection.")


if __name__ == "__main__":
    main()
