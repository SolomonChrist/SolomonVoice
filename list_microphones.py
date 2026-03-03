"""List available microphones for device selection."""

import sounddevice as sd


def list_microphones():
    """List all available input devices."""
    devices = sd.query_devices()

    print("\n=== Available Microphones ===\n")

    input_devices = []
    for i, device in enumerate(devices):
        if device['max_input_channels'] > 0:
            input_devices.append(i)
            is_default = " [DEFAULT]" if i == sd.default.device[0] else ""
            print(f"Device {i}: {device['name']}{is_default}")
            print(f"  Channels: {device['max_input_channels']}")
            print(f"  Sample Rate: {device['default_samplerate']} Hz")
            print()

    print("=== Configuration ===")
    print("\nTo use a specific microphone, edit solomonvoice_config.json:")
    print('  "audio": {')
    print('    "device": <DEVICE_NUMBER>')
    print('  }')
    print("\nExample: To use device 2, change to:")
    print('  "audio": {')
    print('    "device": 2')
    print('  }')
    print("\nTo use the default microphone, set device to null:")
    print('  "audio": {')
    print('    "device": null')
    print('  }')
    print()


if __name__ == "__main__":
    list_microphones()
