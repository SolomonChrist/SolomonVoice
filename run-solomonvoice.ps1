# Set FFmpeg in PATH
$env:PATH = "C:\ffmpeg\bin;$env:PATH"

# Get to the SolomonVoice directory
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

# Run SolomonVoice
Write-Host "Starting SolomonVoice..."
Write-Host "First run will download Whisper model (~145MB) - this may take a few minutes"
Write-Host ""

py main.py
