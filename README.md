# SolomonVoice

SolomonVoice is private, two-way speech for Windows. Hold a global shortcut and local OpenAI Whisper types your speech at the active caret; highlight text and a second shortcut reads it aloud with local Kokoro voices.

Version 2.3 adds offline Read Aloud, 54 selectable voices, adjustable speed, selection/full-document accessibility capture, and first-time installation of both local AI models. It builds on the safer Windows-owned hotkey registration, direct Unicode input, stateful tray icon, non-activating voice meter, Pause/Resume, and real Exit behavior introduced in v2.

> Experimental software. Review dictated text before sending or publishing it.

## Independent product identity

SolomonVoice is an independent product, not a clone or reskin of another dictation application. Its brand, microphone mark, waveform overlay, settings layout, colors, interaction model, and desktop behavior are designed specifically for SolomonVoice and rendered directly by this repository. The project does not incorporate proprietary code, screenshots, icons, copied layouts, or branded assets from competing products.

Product decisions should follow SolomonVoice's own priorities: offline privacy, explicit keyboard ownership, fast local dictation, visible system state, and clean Windows-native operation. New UI work should solve those requirements directly instead of recreating another product's screens or feature arrangement.

SolomonVoice does use clearly declared open-source runtime libraries, including OpenAI Whisper for local speech recognition and Kokoro-82M through the MIT-licensed `kokoro-onnx` runtime for local speech synthesis. Those dependencies provide underlying technical capabilities; they do not supply SolomonVoice's product identity or UI/UX. See `requirements.txt` and the upstream projects for their respective licenses.

## Read Aloud

- Highlight text in an application or browser and press **Ctrl+Shift+Space**.
- Press **Ctrl+Shift+Space** again to stop immediately.
- When nothing is highlighted, SolomonVoice can read the active document or webpage when Windows exposes it through the accessibility API.
- Selection capture prefers Windows UI Automation. For applications that do not expose highlighted ranges, SolomonVoice briefly uses Copy and restores every safely clonable original clipboard format. If a format cannot be preserved, the fallback stops before changing the clipboard. Captured text and generated audio remain in memory.
- Pausing or exiting SolomonVoice stops playback and unregisters both global shortcuts.
- Choose among 54 local voices and set reading speed from 0.5× to 5.0× in Settings.

## What changed in v2

- **Keyboard safety:** `RegisterHotKey` owns only the configured chord. Pause and Exit call `UnregisterHotKey`; no process-wide release hook remains.
- **Reliable shutdown:** active recordings are closed and in-flight transcription results are invalidated, so text cannot arrive after Pause or Exit.
- **Visual feedback:** a small waveform pill appears above the taskbar while recording and while Whisper is working. It is a no-activate tool window and does not take the caret.
- **Tray controls:** teal means ready, red means recording, amber means transcribing, gray means paused, and the warning badge means an error needs attention.
- **Safer insertion:** Unicode is sent directly with the Windows input API. SolomonVoice no longer overwrites or restores the clipboard and never synthesizes a Ctrl+V chord.
- **Focus protection:** if the active window changes while Whisper is transcribing, text is not inserted into the new window.
- **Privacy cleanup:** recorded audio stays in memory instead of being written to a temporary WAV file; transcript contents are not printed to the console.
- **Silence gate:** very low-level captures are rejected before Whisper to reduce silence hallucinations.
- **Decoder guard:** Whisper retries suspicious segments, and repeated-character or repeated-word loops are blocked before they can be typed.
- **Single instance:** a Windows mutex prevents duplicate hotkeys, microphones, and duplicate text insertion.

## Requirements

- Windows 10 or 11
- Python 3.11 or newer
- A working microphone
- Internet access during first-time setup to download the selected Whisper and Kokoro models

FFmpeg is not needed for live dictation in v2 because microphone audio is passed directly to Whisper as an in-memory NumPy array.

## Install

The first-time setup script creates an isolated environment, installs application dependencies, and downloads the smallest Whisper model plus the recommended Kokoro FP16 model and voice pack:

```powershell
.\setup-solomonvoice.ps1
```

`install_model.py` is the model-only equivalent for an environment whose dependencies are already installed. By default it installs both models. Use `--whisper-only` or `--tts-only` for repairs. Normal SolomonVoice startup uses only local files and never initiates a download.

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

To read text aloud:

1. Highlight text in a normal Windows application or webpage.
2. Press **Ctrl+Shift+Space** once.
3. Press **Ctrl+Shift+Space** again whenever you want reading to stop.
4. With no selection, SolomonVoice reads the active document when that application exposes a Windows accessibility text document.

Right-click the tray microphone for:

- **Settings…** — manage Whisper and Kokoro model folders, select a voice and speed, choose a microphone, and configure both shortcuts without editing JSON.
- **Session history…** — inspect the latest 20 attempts, rerun the most recent in-memory audio without typing it, or explicitly copy a transcript. History disappears when SolomonVoice exits.
- **Retry last into active app** — rerun the latest recording with the active model and type it into the currently focused text target.
- **Pause listening** — immediately stops speech, unregisters Ctrl+Space and Ctrl+Shift+Space, and closes the microphone. Both shortcuts behave normally in every app.
- **Resume listening** — registers the shortcut again.
- **Exit SolomonVoice** — invalidates pending work, closes the mic, unregisters the hotkey, removes the tray icon, and terminates the process.

Double-clicking the tray icon toggles Pause/Resume.

## Settings

Open **Settings…** from the tray menu. SolomonVoice temporarily pauses both global shortcuts while the window is open. Use **Apply & resume** or **Cancel & resume** before testing a shortcut in another application.

- Choose **Windows default** or a named microphone. Named devices are saved by device name and Windows audio host rather than a fragile numeric index.
- Choose the active Whisper model and its local storage folder. **Install selected model** is an explicit one-time download; routine dictation remains offline. Compatible local `.pt` checkpoints placed in that folder also appear in the dropdown.
- Choose a Kokoro precision, voice, reading speed, and model folder. **Install voice model** downloads the selected ONNX graph and the shared 54-voice pack.
- Select a voice and click **Preview voice** to hear an offline sample at the current speed; click **Stop preview** to end it immediately. Advanced speeds combine Kokoro's native phoneme timing with local pitch-preserving speech compression to retain articulation without skipping words.
- The tray tooltip shows both active shortcuts. Privacy-safe operational diagnostics are written to `%LOCALAPPDATA%\SolomonVoice\runtime.log`; selected text and dictated text are never written there.
- Configure **Ctrl+Shift+Space** independently from the dictation shortcut and choose whether no-selection requests may fall back to the full active document.
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
    "model_directory": null,
    "language": "en",
    "task": "transcribe"
  },
  "read_aloud": {
    "enabled": true,
    "shortcut": {"key": "space", "modifiers": ["ctrl", "shift"]},
    "model": "kokoro-v1.0-fp16",
    "model_directory": null,
    "voice": "af_heart",
    "speed": 1.0,
    "read_full_document": true,
    "max_characters": 100000,
    "output_device": null
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

New installations select `tiny`, the smallest and fastest standard Whisper model, so first-time setup finishes quickly. Existing users keep their saved choice. Use the Speech model card in Settings to compare another installed model or change the model folder.

For English dictation, try these deliberately and compare them on your own speech:

| Model | Relative speed | Expected accuracy | Approximate download |
|---|---:|---:|---:|
| `tiny` / `tiny.en` | Fastest | Basic | 75 MB |
| `base` / `base.en` | Fast | Better | 145 MB |
| `small` / `small.en` | Moderate | Higher | 460 MB |

English-only `.en` models can improve English recognition without increasing model size. Change one variable at a time and compare several representative recordings before adopting a new default. Quantized engines such as faster-whisper may improve latency and memory at similar accuracy, but v2 does not silently change the inference engine without a user-specific word-error-rate benchmark.

## Safety behavior

- Pause and Exit return Ctrl+Space to Windows immediately.
- Pause and Exit also return Ctrl+Shift+Space and stop Read Aloud audio immediately.
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
- `tts_reader.py` — lazy local Kokoro synthesis, text chunking, and cancelable playback
- `text_capture.py` — clipboard-free selected/document text retrieval through Windows UI Automation
- `tts_models.py` — voice catalog, model locations, and explicit model downloads
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

Third-party libraries and model weights retain their upstream licenses; see `THIRD_PARTY_NOTICES.md`.
