# Changelog

## 2.0.0 — 2026-10-06

- Replaced the leaking low-level keyboard hook with owned Win32 hotkey registration.
- Added stateful system-tray Pause, Resume, and Exit controls.
- Added a passive animated voice-level and transcription overlay.
- Added locked lifecycle transitions and cancellation of stale transcription results.
- Replaced clipboard plus Ctrl+V injection with focus-checked Unicode input.
- Kept microphone audio in memory and removed transcript content from logs.
- Added silence detection, single-instance protection, and automated lifecycle tests.
- Removed the hardware-specific default microphone index and obsolete dependencies.
