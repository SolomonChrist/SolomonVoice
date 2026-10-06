# SolomonVoice

SolomonVoice is private push-to-talk dictation for Windows. Hold a global shortcut, speak, release it, and local OpenAI Whisper types the result at the active caret.

Version 2.1 replaces the old global keyboard hook and clipboard paste path with Windows-owned hotkey registration and direct Unicode input. It adds a stateful tray icon, a non-activating voice meter, Pause/Resume, a native settings window, and a real Exit command that releases the hotkey and microphone.

> Experimental software. Review dictated text before sending or publishing it.

## What changed in v2

- **Keyboard safety:** `RegisterHotKey` owns only the configured chord. Pause and Exit call `UnregisterHotKey`; no process-wide release hook remains.
- **Reliable shutdown:** active recordings are closed and in-flight transcription results are invalidated, so text cannot arrive after Pause or Exit.
- **Visual feedback:** a small waveform pill appears above the taskbar while recording and while Whisper is working. It is a no-activate tool window and does not take the caret.
- **Tray controls:** teal means ready, red means recording, amber means transcribing, gray means paused, and the warning badge means an error needs attention.
- **Safer insertion:** Unicode is sent directly with the Windows input API. SolomonVoice no longer overwrites or restores the clipboard and never synthesizes a Ctrl+V chord.
- **Focus protection:** if the active window changes while Whisper is transcribing, text is not inserted into the new window.
- **Privacy cleanup:** recorded audio stays in memory instead of being written to a temporary WAV file; transcript contents are not printed to the console.
- **Silence gate:** very low-level captures are rejected before Whisper to reduce silence hallucinations.
- **Single instance:** a Windows mutex prevents duplicate hotkeys, microphones, and duplicate text insertion.

## Requirements

- Windows 10 or 11
- Python 3.11 or newer
- A working microphone
- Internet access during setup only if the configured Whisper model is not already cached

FFmpeg is not needed for live dictation in v2 because microphone audio is passed directly to Whisper as an in-memory NumPy array.

## Install

Create a project virtual environment, then install CPU-only PyTorch first to avoid downloading CUDA packages on computers that do not use an NVIDIA GPU:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
python -m pip install -r requirements.txt
python install_model.py
```

`install_model.py` is the explicit, one-time network step. Normal SolomonVoice startup loads only that local cache path and fails closed if the model is absent, so background dictation never initiates a download.

For the first launch, use the activated environment and a console so device or setup errors remain visible:

```powershell
python main.py
```

Transcription is local; no recording or transcript is sent to an API. After setup, SolomonVoice can run without a network connection.

For later launches, double-click `start-solomonvoice.bat` or run:

```powershell
.\run-solomonvoice.ps1
```

Both background launchers use `pyw`, so SolomonVoice lives in the notification area without a console window.

## Use

1. Put the caret in any normal text field.
2. Hold **Ctrl+Space**.
3. Speak while the red waveform is visible.
4. Release **Space**. The overlay turns amber while transcription runs locally.
5. Keep the same target window active until the text appears.

Right-click the tray microphone for:

- **Settings…** — choose a microphone, test its level, change the dictation shortcut, and adjust behavior without editing JSON.
- **Pause listening** — immediately unregisters Ctrl+Space and closes the microphone. The shortcut behaves normally in every app.
- **Resume listening** — registers the shortcut again.
- **Exit SolomonVoice** — invalidates pending work, closes the mic, unregisters the hotkey, removes the tray icon, and terminates the process.

Double-clicking the tray icon toggles Pause/Resume.

## Settings

Open **Settings…** from the tray menu. SolomonVoice temporarily pauses listening while the window is open so shortcut capture and microphone testing cannot interfere with other applications.

- Choose **Windows default** or a named microphone. Named devices are saved by device name and Windows audio host rather than a fragile numeric index.
- Use the Ctrl/Alt/Shift controls and key picker, or click **Record shortcut** and press a combination. Apply checks the shortcut against Windows and keeps the old shortcut if another app already owns it.
- Choose hold-to-talk or press-once toggle mode. In either mode, **Escape** can discard the current recording without transcribing it.
- Enable launch at Windows sign-in, move or hide the waveform, reduce animation, and toggle sounds.

Settings are atomically stored for the current Windows user at `%LOCALAPPDATA%\SolomonVoice\settings.json`. The repository configuration remains the product default and is no longer edited for normal preference changes.

## Advanced configuration

The tray Settings window covers normal choices. `solomonvoice_config.json` remains available for model, language, sample-rate, and other advanced defaults:

```json
{
  "shortcut": {
    "key": "space",
    "modifiers": ["ctrl"]
  },
  "whisper": {
    "model": "tiny",
    "language": "en",
    "task": "transcribe"
  },
  "audio": {
    "sample_rate": 16000,
    "channels": 1,
    "device": null,
    "silence_rms": 0.003
  },
  "behavior": {
    "min_recording_seconds": 0.5,
    "max_recording_seconds": 30,
    "append_space": true,
    "require_same_window": true,
    "recording_mode": "hold",
    "escape_to_cancel": true,
    "start_with_windows": false
  },
  "visual": {
    "enabled": true,
    "position": "bottom",
    "reduced_motion": false
  },
  "feedback": {
    "sound_enabled": true,
    "console_enabled": true
  }
}
```

Useful shortcut keys include `space`, letters or digits, `f1`–`f24`, `tab`, `escape`, `insert`, `delete`, `home`, `end`, and arrow keys. Modifiers may include `ctrl`, `alt`, `shift`, and `win`. Windows reserves some combinations, and SolomonVoice shows an error if another application already owns the selected chord.

Set `audio.device` to `null` for the current Windows default microphone. The Settings window stores a stable device name and audio-host identity. Numeric indexes remain supported for older configurations but can change when USB or Bluetooth devices reconnect.

### Choosing a model

The shipped configuration remains on `tiny`, the smallest standard Whisper model, because the previous installation used it. There is no smaller official Whisper model with a guarantee of the same transcription quality.

For English dictation, try these deliberately and compare them on your own speech:

| Model | Relative speed | Expected accuracy | Approximate download |
|---|---:|---:|---:|
| `tiny` / `tiny.en` | Fastest | Basic | 75 MB |
| `base` / `base.en` | Fast | Better | 145 MB |
| `small` / `small.en` | Moderate | Higher | 460 MB |

English-only `.en` models can improve English recognition without increasing model size. Change one variable at a time and compare several representative recordings before adopting a new default. Quantized engines such as faster-whisper may improve latency and memory at similar accuracy, but v2 does not silently change the inference engine without a user-specific word-error-rate benchmark.

## Safety behavior

- Pause and Exit return Ctrl+Space to Windows immediately.
- Repeated keydown events do not start duplicate recordings.
- Text insertion waits for every shortcut key, including Ctrl, to be physically released.
- Changing focus during transcription causes a safe error instead of a paste into the wrong app.
- Closing during transcription discards that result.
- Audible start feedback finishes before the microphone opens; stop feedback plays after it closes.
- Elevated applications may reject input from a non-elevated SolomonVoice process due to Windows integrity protections.

## Tests

Run the unit and lifecycle tests with:

```powershell
py -m pytest -q --basetemp=.pytest-tmp
```

The test suite covers configuration isolation, hotkey parsing, UTF-16 input, in-memory transcription options, Pause teardown, and late-insertion cancellation. A Windows smoke test also registers and unregisters the native hotkey repeatedly without installing a global keyboard hook.

## Architecture

- `main.py` — application lifecycle, signals, and single-instance ownership
- `hotkey.py` — Win32 `RegisterHotKey`, release detection, and exact teardown
- `listener_v2.py` — locked recording/transcription state machine and cancellation generations
- `ui.py` — tray icon and no-activate waveform overlay
- `transcriber.py` — lazy local Whisper model and in-memory transcription
- `injector.py` — focus-checked Unicode `SendInput`
- `feedback.py` — optional sound and minimal console status
- `config.py` — defaults, deep merge, and validation

## Troubleshooting

**The tray says the hotkey could not be registered**

Another application owns the shortcut. Exit that application or choose a different combination in the configuration file.

**The microphone fails to open**

Set `audio.device` to `null`, confirm Windows microphone privacy permission, and test the device with `py list_microphones.py`.

**Text is not inserted**

Keep the original target window active until transcription finishes. Normal applications accept Unicode input; an elevated target requires SolomonVoice to run at the same integrity level.

**Accuracy is too low**

For English, try `tiny.en`, then `base.en`. Keep `language` set to `en`, speak close to the microphone, and compare results on the same sample phrases.

**The model is missing while offline**

Connect once and run `python install_model.py` from the activated environment, or copy a trusted model into the normal Whisper cache before starting offline.

## License

MIT — see `LICENSE`.
