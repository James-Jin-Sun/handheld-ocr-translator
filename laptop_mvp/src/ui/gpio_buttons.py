"""Optional physical push-button input for Jetson devices, so a handheld
unit without a mouse can drive the UI with two buttons instead of clicks.

Button wiring (BOARD numbering, active-low with an external pull-up -- see
the NVIDIA Jetson.GPIO `button_led.py`/`button_event.py` samples for the
same pattern):

    3.3V (pin 1 or 17) --[10k resistor]--+-- PRIMARY_PIN (pin 29 / GPIO01)
                                          |
                                      [Button 1]
                                          |
                                         GND (pin 25, 30, or 34)

    3.3V (pin 1 or 17) --[10k resistor]--+-- SECONDARY_PIN (pin 31 / GPIO11)
                                          |
                                      [Button 2]
                                          |
                                         GND (pin 25, 30, or 34)

Both pins default to plain GPIO on the Orin Nano devkit's 40-pin header (no
I2C/UART/SPI function to fight with), so no `jetson-io.py` reconfiguration
is needed.

`GpioButtons.create()` maps to "primary" (the left-hand button on each
screen: Capture Image / Confirm / Save) and "secondary" (the right-hand
button: Select Image / Close-Retake / Close-Restart) -- app.py decides what
each one does based on the current screen. It returns None instead of
raising when `Jetson.GPIO` isn't installed or the platform isn't ARM (e.g.
the Windows laptop MVP), so physical buttons are a purely optional
accessory that never blocks running the app without them.
"""

import platform

try:
    import Jetson.GPIO as GPIO
except ImportError:
    GPIO = None

# BOARD (physical) pin numbers -- see the module docstring for wiring.
PRIMARY_PIN = 29
SECONDARY_PIN = 31
DEBOUNCE_MS = 250


class GpioButtons:
    """Two momentary push buttons read via interrupt-driven GPIO edge
    detection instead of polling.

    Callbacks fire on a `Jetson.GPIO`-managed background thread, so callers
    must hop back onto the Tk main thread themselves (e.g. via
    `root.after(0, ...)`) before touching any widgets -- same pattern as
    `pipeline_worker.run_pipeline_async`'s `on_done`/`on_error`.
    """

    def __init__(self, on_primary, on_secondary):
        GPIO.setmode(GPIO.BOARD)
        GPIO.setup(PRIMARY_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(SECONDARY_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

        GPIO.add_event_detect(
            PRIMARY_PIN,
            GPIO.FALLING,
            callback=lambda channel: on_primary(),
            bouncetime=DEBOUNCE_MS,
        )
        GPIO.add_event_detect(
            SECONDARY_PIN,
            GPIO.FALLING,
            callback=lambda channel: on_secondary(),
            bouncetime=DEBOUNCE_MS,
        )

    def close(self):
        GPIO.remove_event_detect(PRIMARY_PIN)
        GPIO.remove_event_detect(SECONDARY_PIN)
        GPIO.cleanup([PRIMARY_PIN, SECONDARY_PIN])

    @staticmethod
    def is_supported():
        return GPIO is not None and platform.machine().lower() in ("aarch64", "arm64")

    @classmethod
    def create(cls, on_primary, on_secondary):
        """Factory that never raises: returns None when GPIO isn't
        available (wrong platform, `Jetson.GPIO` not installed, or no
        permission to access it) so physical buttons stay optional."""
        if not cls.is_supported():
            return None
        try:
            return cls(on_primary, on_secondary)
        except Exception as exc:  # noqa: BLE001 - optional hardware must never crash the app
            print(f"GPIO buttons unavailable ({exc}); continuing with mouse/keyboard only.")
            return None
