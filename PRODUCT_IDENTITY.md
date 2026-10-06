# SolomonVoice Product Identity

SolomonVoice must remain a distinct, independently designed offline dictation system.

## Design boundary

- Do not copy proprietary source code, visual assets, screenshots, icons, wording, layouts, or interaction sequences from another dictation product.
- Do not present SolomonVoice as a clone, replacement skin, or imitation of a named competitor.
- Build UI components from SolomonVoice's own visual language: deep navy surfaces, teal state accents, concise privacy-first language, and the SolomonVoice microphone/waveform mark.
- Add features because they improve the offline dictation workflow, not merely because another product includes them.
- Keep recording, transcription, cancellation, pause, and keyboard-ownership states explicit and visually distinguishable.

## Permitted foundations

SolomonVoice may use properly licensed, declared open-source libraries for underlying capabilities. Current examples include OpenAI Whisper, sounddevice, NumPy, Pillow, and pystray. Dependencies must remain visible in `requirements.txt`, and their names or assets must not be repurposed as SolomonVoice branding.

## Review checklist

Before merging a UI or branding change:

1. Confirm every new visual asset was created for SolomonVoice or has documented compatible licensing.
2. Confirm no competitor name, screenshot, proprietary copy, or product-specific layout was used as implementation material.
3. Verify normal, hover, pressed, focused, disabled, error, recording, and transcribing states in both code and tests.
4. Confirm the result reinforces SolomonVoice's offline, private, Windows-native identity.
