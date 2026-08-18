"""Standalone hardware test for the physical GPIO buttons (see gpio_buttons.py).

Run this on the Jetson after wiring the buttons, to confirm the wiring and
permissions are correct *before* testing through the full Tkinter app:

    python3 test_gpio_buttons.py

Prints a line every time a press is detected on pin 29 (primary) or pin 31
(secondary). Press Ctrl+C to stop.
"""

import sys
import time

from gpio_buttons import GpioButtons


def on_primary():
    print("PRIMARY button pressed (pin 29)")


def on_secondary():
    print("SECONDARY button pressed (pin 31)")


def main():
    buttons = GpioButtons.create(on_primary=on_primary, on_secondary=on_secondary)
    if buttons is None:
        print(
            "GPIO buttons unavailable. Check that:\n"
            "  - Jetson.GPIO is installed (`pip install Jetson.GPIO`)\n"
            "  - you're running this on the Jetson (not the Windows laptop MVP)\n"
            "  - your user is in the `gpio` group, and you logged out/rebooted "
            "since running `sudo usermod -aG gpio $USER`"
        )
        sys.exit(1)

    print("Listening for button presses on pin 29 (primary) and pin 31 (secondary).")
    print("Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        buttons.close()
        print("\nDone.")


if __name__ == "__main__":
    main()
