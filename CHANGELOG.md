# Changelog

## 2.3.0

- Added completely offline Read Aloud using Apache-2.0 Kokoro-82M weights through the MIT `kokoro-onnx` runtime.
- Added the independently configurable **Ctrl+Shift+Space** start/stop shortcut, with the same Windows-owned registration and teardown guarantees as dictation.
- Added clipboard-free highlighted-text and full-document capture through Windows UI Automation.
- Added 54-voice selection, 0.5×–2.0× reading speed, model precision selection, model-folder display, installation status, and in-app model installation.
- First-time setup now installs both Whisper Tiny and Kokoro FP16 plus the shared voice pack; normal runtime remains offline and never downloads models.
- Pausing or exiting now cancels synthesis, stops output, clears the in-memory queue, and unregisters both shortcuts.

## 2.2.1

- Fixed lost opening words on slow-waking USB and Bluetooth microphones by opening the input first and waiting for the first real audio block.
- Capture now prefers each Windows endpoint's native sample rate before local resampling.
- Restored Whisper's decoding fallback ladder and block pathological repeated-letter or repeated-word output before insertion.
- Added private session history and retry controls; transcripts and the latest retry audio remain memory-only and disappear on exit.
- Fixed Settings microphone-meter timer cleanup so closed windows leave no background UI callbacks.

## 2.2.0

- Added a visible Whisper model selector with installed-state and size/speed guidance.
- Added a configurable local model folder and discovery of compatible `.pt` checkpoints.
- Added an explicit in-app model installer; background dictation remains offline.
- Made `tiny` the consistent smallest, fastest first-install default.

## 2.1.1

- Redesigned Settings with a cohesive SolomonVoice dark visual system.
- Removed Windows light-theme hover, focus, and selected-state bleed-through.
- Added dark title-bar treatment, branded app icon/header, bordered cards, and clearer hierarchy.
- Replaced small native checkboxes and radio buttons with accessible high-contrast selection chips.
- Added layout and interaction-state regression coverage.

## 2.1.0

- Added a native Settings window available from the tray.
- Added stable microphone selection with a live speaking-level test.
- Added shortcut recording, conflict detection, and rollback to the previous shortcut on failure.
- Added hold-to-talk and press-once toggle recording modes.
- Added Escape-to-cancel during an active recording.
- Added optional launch at Windows sign-in.
- Added per-user, atomic settings under `%LOCALAPPDATA%\SolomonVoice`.
- Added controls for waveform visibility/position, reduced motion, and sound feedback.

## 2.0.1 — 2026-10-06

- Added a visible SolomonVoice brand label and microphone mark to the recording overlay.
- Rebuilt the pill background to eliminate overlapping corner outlines.
- Separated status text and waveform into fixed columns with automated layout checks.

## 2.0.0 — 2026-10-06

- Replaced the leaking low-level keyboard hook with owned Win32 hotkey registration.
- Added stateful system-tray Pause, Resume, and Exit controls.
- Added a passive animated voice-level and transcription overlay.
- Added locked lifecycle transitions and cancellation of stale transcription results.
- Replaced clipboard plus Ctrl+V injection with focus-checked Unicode input.
- Kept microphone audio in memory and removed transcript content from logs.
- Added silence detection, single-instance protection, and automated lifecycle tests.
- Removed the hardware-specific default microphone index and obsolete dependencies.
