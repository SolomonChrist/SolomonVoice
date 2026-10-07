@echo off
cd /d "%~dp0"

echo.
echo ========================================
echo Starting SolomonVoice v2.3.4
echo ========================================
echo.
echo This is an offline voice-to-text and text-to-voice tool.
echo - Hold Ctrl+Space to record
echo - Release to transcribe
echo - Text will be typed into the focused app
echo - Ctrl+Shift+Space reads highlighted text aloud and stops it
echo.
echo Hotkey: Ctrl+Space
echo Models: Whisper Tiny + Kokoro FP16 by default (change them in Settings)
echo Dictation and Read Aloud: Local and offline after first-time setup
echo A tray icon will appear. Right-click it for Settings, Pause, or Exit.
echo.
echo Exit from the tray menu to release the hotkey.
echo ========================================
echo.

set "PYTHONW=pyw"
if exist ".venv\Scripts\pythonw.exe" set "PYTHONW=.venv\Scripts\pythonw.exe"
start "" "%PYTHONW%" main.py
