$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvDir = Join-Path $scriptDir ".venv"
$python = Join-Path $venvDir "Scripts\python.exe"

Write-Host "SolomonVoice first-time setup" -ForegroundColor Cyan
Write-Host "This installs application dependencies, Whisper Tiny, Kokoro FP16, and the local voice pack."

if (-not (Test-Path -LiteralPath $python)) {
    py -3.11 -m venv $venvDir
}

& $python -m pip install --upgrade pip setuptools wheel
& $python -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
& $python -m pip install -r (Join-Path $scriptDir "requirements.txt")
& $python (Join-Path $scriptDir "install_model.py")

Write-Host ""
Write-Host "SolomonVoice is ready. Runtime dictation and Read Aloud are fully offline." -ForegroundColor Green
Write-Host "Start it with: .\run-solomonvoice.ps1"
