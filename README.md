# SolomonVoice - Offline Voice to Text

A lightweight, completely offline push-to-talk voice transcription tool for Windows. Hold a hotkey → record voice → release → text is automatically transcribed and typed into any focused app. No internet required, no data sent anywhere.

## Motivation

Inspired by the desire for a **completely offline alternative** to cloud-based voice tools—SolomonVoice runs entirely on your machine using OpenAI's Whisper model. Every transcription happens locally on your CPU. Your voice data stays on your device.

## Features

- **100% Offline**: Uses OpenAI Whisper running locally on your CPU (no API calls, no internet)
- **Privacy First**: All voice data stays on your device
- **Hotkey-triggered**: Configurable hotkey (default: Ctrl+Space)
- **Cross-app**: Text injection works in any focused window (Notepad, VS Code, Gmail, browsers, etc.)
- **Instant Feedback**: Audio beeps + console messages
- **Configurable**: Customize hotkey, model size, language, and behavior
- **Fast**: Whisper model cached locally after first run

## Prerequisites

Before installation, you need to set up the environment:

### 1. Install FFmpeg (Required by Whisper)

```bash
winget install ffmpeg
```

Restart your terminal and verify:
```bash
ffmpeg -version
```

### 2. Install PyTorch CPU-Only

**Important**: Do NOT install via `pip install -r requirements.txt` until you do this step.

```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
```

This uses the official CPU-only wheel and avoids downloading the large GPU CUDA toolkit.

### 3. Install SolomonVoice Dependencies

```bash
cd SolomonVoice
pip install -r requirements.txt
```

## First Run

On your first run, Whisper will download its base model (~145MB) and cache it locally:

```bash
python main.py
```

You should see:
```
==================================================
SolomonVoice - Offline Voice to Text
==================================================
Hotkey: Ctrl+Space
Config: C:\path\to\solomonvoice_config.json
Ready. Hold hotkey to record.
Press Ctrl+C to exit.
==================================================
```

The Whisper model is cached at `~/.cache/whisper/` so subsequent runs start instantly.

## Usage

### Basic Usage

1. Run SolomonVoice:
   ```bash
   python main.py
   ```

2. Open any text-accepting window (Notepad, browser, IDE, email, messaging app, etc.)

3. Hold **Ctrl+Space** (or your configured hotkey):
   - You'll hear a beep and see "Recording... (release key to stop)"
   - Speak clearly

4. Release the key:
   - You'll hear a stop beep and see "Transcribing..."
   - Wait 1-2 seconds for transcription (depends on audio length and CPU)
   - You'll hear a done beep and see the transcribed text

5. The text is pasted into the focused window, and your clipboard is restored

### Run in Background (No Console Window)

```bash
pythonw main.py
```

This uses the Python windowless interpreter. Audio beeps still work.

## Configuration

Edit `solomonvoice_config.json` to customize behavior:

```json
{
  "shortcut": {
    "key": "space",
    "modifiers": ["ctrl"]
  },
  "whisper": {
    "model": "base",
    "language": null,
    "task": "transcribe"
  },
  "audio": {
    "sample_rate": 16000,
    "channels": 1,
    "device": null
  },
  "behavior": {
    "min_recording_seconds": 0.5,
    "max_recording_seconds": 30,
    "append_space": true,
    "suppress_hotkey": true
  },
  "feedback": {
    "sound_enabled": true,
    "console_enabled": true
  }
}
```

### Configuration Options

#### Shortcut
- `key`: Any key name (`"space"`, `"f9"`, `"grave"`, etc.)
- `modifiers`: Array of `"ctrl"`, `"alt"`, `"shift"` (or empty `[]` for no modifier)

#### Whisper
- `model`: Model size (`"tiny"`, `"base"`, `"small"`, `"medium"`, `"large"`)
  - `tiny`: ~39MB, fast, lower accuracy
  - `base`: ~145MB, ~1.5-2s transcription, good accuracy (recommended)
  - `small`: ~466MB, ~3-4s transcription, higher accuracy
  - `medium`: ~1.5GB, slower, very high accuracy
  - `large`: ~2.9GB, slowest, highest accuracy
- `language`: ISO language code (e.g., `"en"`, `"es"`, `"fr"`) or `null` for auto-detect
- `task`: Always `"transcribe"` (future: `"translate"`)

#### Audio
- `sample_rate`: 16000 is standard for speech recognition
- `channels`: 1 (mono) is standard
- `device`: `null` for system default mic, or integer index for specific device

#### Behavior
- `min_recording_seconds`: Ignore recordings shorter than this (avoids accidental triggers)
- `max_recording_seconds`: Force stop recording after this (safety limit)
- `append_space`: Add a trailing space to transcribed text (useful for typing)
- `suppress_hotkey`: Don't send the hotkey to other apps

#### Feedback
- `sound_enabled`: Play beeps (800Hz start, 600Hz stop, 1000Hz done, 400Hz error)
- `console_enabled`: Print status messages

## Hotkey Examples

### F9 with no modifier
```json
{
  "shortcut": {
    "key": "f9",
    "modifiers": []
  }
}
```

### Ctrl+Alt+V
```json
{
  "shortcut": {
    "key": "v",
    "modifiers": ["ctrl", "alt"]
  }
}
```

### Grave (backtick) with Shift
```json
{
  "shortcut": {
    "key": "grave",
    "modifiers": ["shift"]
  }
}
```

## Verification

Test that everything works:

1. Open Notepad
2. Click in the text area
3. Hold Ctrl+Space, say "Hello world this is a test", release
4. You should see and hear feedback
5. "Hello world this is a test " should appear in Notepad
6. Paste elsewhere — your clipboard should be restored (not the transcribed text)
7. Try a very short press (<0.5s) — should be ignored silently
8. Try recording only silence — should show "Could not understand audio"

## Troubleshooting

### "ffmpeg: command not found"
Make sure you installed ffmpeg and restarted your terminal:
```bash
winget install ffmpeg
```

### "torch not found" or import errors
Install PyTorch with the CPU index URL (see Prerequisites above).

### Model download is stuck
Whisper downloads are sometimes slow. The model is cached at `~/.cache/whisper/`. If stuck, delete that directory and try again.

### Audio quality is poor
- Try moving your microphone closer
- Check system mic settings (Settings → Privacy & Security → Microphone)
- Try a different model size or language setting

### Text not appearing in target app
Some apps block text injection via clipboard + Ctrl+V. Try:
- Disabling any security software temporarily
- Testing with Notepad first
- Using `"suppress_hotkey": false` in case the hotkey is being intercepted

### High CPU usage during transcription
This is normal — Whisper is CPU-intensive. A smaller model (e.g., `"tiny"`) is faster but less accurate. Larger models are slower but more accurate. Transcription time depends on audio length and CPU cores.

## Architecture

- **main.py**: Entry point, startup banner, Ctrl+C handler
- **config.py**: Configuration loader with deep-merge defaults and validation
- **listener.py**: State machine for keyboard hook and recording orchestration
- **transcriber.py**: Offline Whisper model wrapper
- **injector.py**: Text injection via clipboard trick
- **feedback.py**: Console and audio feedback
- **solomonvoice_config.json**: User-editable configuration

## Data Flow

```
KEY DOWN (e.g., Ctrl+Space):
  state: IDLE → RECORDING
  Audio stream starts (callback appends chunks)
  Beep + "Recording..."

[USER HOLDS KEY, SPEAKS]

KEY UP:
  state: RECORDING → TRANSCRIBING
  Audio stream stops
  Beep + "Transcribing..."
  Background thread spawned

[BACKGROUND THREAD - COMPLETELY LOCAL]:
  Concatenate audio chunks
  Write to temp .wav
  Whisper transcribes locally (1-2 seconds)
  Copy text to clipboard
  Ctrl+V into focused window
  Restore original clipboard
  Beep + "Done: ..."
  state: TRANSCRIBING → IDLE
```

## Edge Cases Handled

- **Too short** (<0.5s): Silently ignored
- **Too long** (>30s): Auto-stopped, timer fires
- **Empty transcription** (silence/noise): Shows "Could not understand audio"
- **Whisper exception**: Caught, tool keeps running
- **Clipboard race**: 50ms sleep between copy and paste
- **Clipboard restore**: Always restored in finally block
- **Key suppression**: Only hotkey suppressed, not global

## Performance Notes

- First run: ~30-60s (downloads and caches model)
- Subsequent runs: ~1-2s startup
- Recording: Real-time (limited by your microphone)
- Transcription: Depends on model and audio length
  - Tiny: ~0.5s for 5s audio
  - Base: ~1.5-2s for 5s audio
  - Large: ~5-10s for 5s audio
- Text injection: ~100ms
- **Important**: Whisper needs `fp16=False` on CPU (we already set this)

## Privacy & Data

SolomonVoice processes all audio completely offline:
- ✅ No internet connection required
- ✅ No data sent to any server
- ✅ No cloud storage or APIs
- ✅ Voice stays on your machine
- ✅ Temp files deleted after transcription

## Future Enhancements

- Microphone device selector UI
- Audio visualization while recording
- Multiple hotkey profiles
- Whisper fine-tuning for custom vocabulary
- Real-time transcription (streaming)
- Translation support
- Custom TTS feedback
- Wake word detection
- Context-aware suggestions

## License

This is a sub-project of ai-SecondBrain. See main repo for details.
