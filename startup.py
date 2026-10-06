"""Per-user Windows startup registration for SolomonVoice."""

from __future__ import annotations

import sys
from pathlib import Path


RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "SolomonVoice"


def launch_command(app_directory=None) -> str:
    app_directory = Path(app_directory or Path(__file__).parent).resolve()
    venv_pythonw = app_directory / ".venv" / "Scripts" / "pythonw.exe"
    if venv_pythonw.exists():
        executable = venv_pythonw
    else:
        running = Path(sys.executable)
        sibling_pythonw = running.with_name("pythonw.exe")
        executable = sibling_pythonw if sibling_pythonw.exists() else running
    return f'"{executable}" "{app_directory / "main.py"}"'


def set_start_with_windows(enabled: bool, app_directory=None) -> None:
    """Create or remove SolomonVoice from the current user's Run key."""
    if sys.platform != "win32":
        if enabled:
            raise RuntimeError("Start with Windows is available only on Windows")
        return
    import winreg

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        if enabled:
            winreg.SetValueEx(
                key,
                VALUE_NAME,
                0,
                winreg.REG_SZ,
                launch_command(app_directory),
            )
        else:
            try:
                winreg.DeleteValue(key, VALUE_NAME)
            except FileNotFoundError:
                pass


def starts_with_windows() -> bool:
    if sys.platform != "win32":
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, VALUE_NAME)
            return True
    except FileNotFoundError:
        return False
