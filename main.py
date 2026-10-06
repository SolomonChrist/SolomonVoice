"""SolomonVoice Windows tray application entry point."""

from __future__ import annotations

import signal
import sys
from pathlib import Path

from config import Config
from feedback import Feedback
from listener_v2 import ListenerV2, State
from single_instance import SingleInstance
from ui import DesktopUI


def main() -> int:
    config_path = Path(__file__).parent / "solomonvoice_config.json"
    instance = None
    ui = None
    listener = None
    try:
        instance = SingleInstance()
        config = Config(config_path, user_path=Config.default_user_path())
        feedback = Feedback(
            sound_enabled=config.get("feedback.sound_enabled"),
            console_enabled=config.get("feedback.console_enabled"),
        )
        ui = DesktopUI(config)
        listener = ListenerV2(
            config,
            feedback,
            on_state=ui.notify_state,
            on_level=ui.notify_level,
            on_history=ui.notify_history,
        )
        ui.bind_listener(listener)
        ui.start_tray()

        def request_shutdown(_signal=None, _frame=None):
            ui.root.after(0, ui.shutdown)

        signal.signal(signal.SIGINT, request_shutdown)
        signal.signal(signal.SIGTERM, request_shutdown)

        try:
            listener.start()
            feedback.startup(config_path, listener.hotkey_display())
            if config.load_warning:
                feedback.error(config.load_warning)
                ui.notify_state(State.ERROR, config.load_warning)
            if "--settings" in sys.argv[1:]:
                ui.root.after(350, ui.open_settings)
        except Exception as exc:
            feedback.error(str(exc))
            ui.notify_state(State.ERROR, str(exc))

        ui.run()
        return 0
    except Exception as exc:
        print(f"[SolomonVoice] Fatal: {exc}", file=sys.stderr, flush=True)
        return 1
    finally:
        if listener:
            listener.stop()
        if instance:
            instance.close()


if __name__ == "__main__":
    raise SystemExit(main())
