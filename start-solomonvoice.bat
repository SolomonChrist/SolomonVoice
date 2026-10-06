@echo off
cd /d "%~dp0"

echo.
echo ========================================
echo Starting SolomonVoice v2.0
echo ========================================
echo.
echo This is an offline voice-to-text tool.
echo - Hold Ctrl+Space to record
echo - Release to transcribe
echo - Text will be typed into the focused app
echo.
echo Hotkey: Ctrl+Space
echo Model: Tiny (configured in solomonvoice_config.json)
echo Transcription: Local and offline after one-time model setup
echo A tray icon will appear. Right-click it to pause or exit.
echo.
echo Exit from the tray menu to release the hotkey.
echo ========================================
echo.

set "PYTHONW=pyw"
if exist ".venv\Scripts\pythonw.exe" set "PYTHONW=.venv\Scripts\pythonw.exe"
start "" "%PYTHONW%" main.py
