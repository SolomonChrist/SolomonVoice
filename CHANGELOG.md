# Changelog

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
