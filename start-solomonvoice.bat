@echo off
echo Setting up environment...
set PATH=C:\ffmpeg\bin;%PATH%

cd /d "%~dp0"

echo.
echo ========================================
echo Starting SolomonVoice v1.0
echo ========================================
echo.
echo This is an offline voice-to-text tool.
echo - Hold Ctrl+Space to record
echo - Release to transcribe
echo - Text will be typed into the focused app
echo.
echo Hotkey: Ctrl+Space
echo Model: Base (145MB, recommended)
echo Voice: 100%% Offline, Zero Internet
echo.
echo Press Ctrl+C to exit
echo ========================================
echo.

py main.py

pause
