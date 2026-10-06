import pytest

from single_instance import SingleInstance


def test_second_instance_is_rejected():
    first = SingleInstance("Local\\SolomonVoice-Test-Mutex")
    try:
        with pytest.raises(RuntimeError, match="already running"):
            SingleInstance("Local\\SolomonVoice-Test-Mutex")
    finally:
        first.close()
