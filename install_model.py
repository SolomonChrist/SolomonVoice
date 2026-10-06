"""Explicit one-time Whisper model acquisition for offline runtime use."""

import argparse
from pathlib import Path

import whisper

from config import Config


def main():
    parser = argparse.ArgumentParser(description="Download and verify a SolomonVoice Whisper model")
    parser.add_argument("model", nargs="?", help="Model name; defaults to solomonvoice_config.json")
    args = parser.parse_args()
    config = Config(Path(__file__).parent / "solomonvoice_config.json")
    model_name = args.model or config.get("whisper.model")
    print(f"Installing Whisper model '{model_name}' into the local cache...")
    whisper.load_model(model_name)
    print(f"Model '{model_name}' is installed. SolomonVoice can now transcribe offline.")


if __name__ == "__main__":
    main()
