import ui
from listener_v2 import State
from settings_ui import SettingsWindow


class DummyValue:
    def __init__(self):
        self.value = None

    def set(self, value):
        self.value = value


class DummyButton:
    def configure(self, **_kwargs):
        pass


def test_failed_test_stream_close_retains_cleanup_handle():
    class BrokenStream:
        def stop(self):
            raise RuntimeError("stop failed")

        def abort(self):
            pass

        def close(self):
            raise RuntimeError("close failed")

    settings = SettingsWindow.__new__(SettingsWindow)
    stream = BrokenStream()
    settings._test_stream = stream
    settings._test_level = 1.0
    settings.mic_status = DummyValue()
    settings.test_button = DummyButton()

    assert settings._stop_microphone_test() is False
    assert settings._test_stream is stream
    assert "Could not release" in settings.mic_status.value


def test_settings_does_not_open_when_pause_is_unconfirmed(monkeypatch):
    class Listener:
        state = State.IDLE

        def pause(self):
            self.state = State.ERROR

    desktop = ui.DesktopUI.__new__(ui.DesktopUI)
    desktop.listener = Listener()
    desktop.config = object()
    desktop.root = object()
    desktop._settings_window = None
    errors = []
    monkeypatch.setattr(ui.messagebox, "showerror", lambda *args, **kwargs: errors.append(args))
    monkeypatch.setattr(ui, "SettingsWindow", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError()))

    desktop._open_settings()

    assert desktop._settings_window is None
    assert errors


def test_settings_constructor_failure_resumes_previous_active_state(monkeypatch):
    class Listener:
        state = State.IDLE
        resumed = False

        def pause(self):
            self.state = State.PAUSED

        def resume(self):
            self.resumed = True
            self.state = State.IDLE

    desktop = ui.DesktopUI.__new__(ui.DesktopUI)
    desktop.listener = Listener()
    desktop.config = object()
    desktop.root = object()
    desktop._settings_window = None
    monkeypatch.setattr(ui.messagebox, "showerror", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(ui, "SettingsWindow", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("UI failed")))

    desktop._open_settings()

    assert desktop.listener.resumed is True
    assert desktop.listener.state == State.IDLE
