# Get to the SolomonVoice directory
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

# Run SolomonVoice
Write-Host "Starting SolomonVoice in the system tray..."
$venvPython = Join-Path $scriptDir ".venv\Scripts\pythonw.exe"
$pythonw = if (Test-Path $venvPython) { $venvPython } else { "pyw.exe" }
Start-Process -FilePath $pythonw -ArgumentList "main.py" -WorkingDirectory $scriptDir -WindowStyle Hidden
