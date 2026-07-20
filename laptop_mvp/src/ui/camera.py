"""Webcam capture wrapper built on OpenCV, yielding PIL images.

Auto-detects an external USB handheld camera by device name so it is picked
correctly even when a laptop's built-in webcam is also connected (device
indices otherwise depend on OS enumeration order and can silently point at
the wrong camera). Known cameras that have been used with this project are
matched first (`KNOWN_EXTERNAL_CAMERA_NAMES`); if none of those match, the
first device that isn't the built-in webcam or a virtual camera is used, so
swapping in a new external camera generally doesn't require a code change.
Falls back to plain index 0 if name-based lookup is unavailable (non-Windows)
or nothing external is found.
"""

try:
    import cv2
except ImportError as exc:
    raise SystemExit(
        "Missing dependency: install opencv with `pip install opencv-python-headless`."
    ) from exc

try:
    from PIL import Image
except ImportError as exc:
    raise SystemExit("Missing dependency: install Pillow with `pip install pillow`.") from exc

# Ordered by recency of use; the first match wins. Add new handheld cameras
# here as they get used with this project.
KNOWN_EXTERNAL_CAMERA_NAMES = (
    "EPIC CAM USB HD WEBCAM",  # JLab Epic Cam
    "Innomaker-U20CAM-1080p-S1",  # Innomaker U20CAM-1080P
)
# Built-in/virtual devices to skip when falling back to "first external camera".
EXCLUDED_CAMERA_NAME_SUBSTRINGS = (
    "integrated camera",
    "integrated webcam",
    "built-in",
    "obs virtual camera",
    "virtual camera",
)
DEFAULT_FRAME_WIDTH = 1920
DEFAULT_FRAME_HEIGHT = 1080


def _list_device_names():
    """Return DirectShow device names in enumeration order, or None if the
    lookup is unavailable (e.g. non-Windows, or `pygrabber` not installed)."""
    try:
        from pygrabber.dshow_graph import FilterGraph
    except ImportError:
        return None

    try:
        return FilterGraph().get_input_devices()
    except Exception:
        return None


def _find_device_index_by_name(name_substring, device_names):
    needle = name_substring.lower()
    for index, device_name in enumerate(device_names):
        if needle in device_name.lower():
            return index
    return None


def _find_first_external_camera_index(device_names):
    for index, device_name in enumerate(device_names):
        name_lower = device_name.lower()
        if not any(excluded in name_lower for excluded in EXCLUDED_CAMERA_NAME_SUBSTRINGS):
            return index
    return None


def autodetect_camera_index():
    """Best-effort pick of the external handheld camera's device index.

    Tries known camera names first, then falls back to the first
    non-built-in/non-virtual device, then None if nothing usable is found.
    """
    device_names = _list_device_names()
    if not device_names:
        return None

    for known_name in KNOWN_EXTERNAL_CAMERA_NAMES:
        index = _find_device_index_by_name(known_name, device_names)
        if index is not None:
            return index

    return _find_first_external_camera_index(device_names)


class Camera:
    """Thin wrapper around `cv2.VideoCapture` that hands back PIL images."""

    def __init__(
        self,
        device_index=None,
        frame_width=DEFAULT_FRAME_WIDTH,
        frame_height=DEFAULT_FRAME_HEIGHT,
    ):
        if device_index is None:
            device_index = autodetect_camera_index()
        self.device_index = device_index if device_index is not None else 0
        self.frame_width = frame_width
        self.frame_height = frame_height
        self._capture = None

    def open(self):
        """Open the camera device. Returns True if it is usable."""
        if self._capture is None:
            # CAP_DSHOW gives more reliable resolution control on Windows than
            # the default backend; fall back if it can't open this device.
            capture = cv2.VideoCapture(self.device_index, cv2.CAP_DSHOW)
            if not capture.isOpened():
                capture.release()
                capture = cv2.VideoCapture(self.device_index)

            self._capture = capture
            if self._capture.isOpened():
                self._capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.frame_width)
                self._capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.frame_height)

        return self._capture.isOpened()

    def is_open(self):
        return self._capture is not None and self._capture.isOpened()

    def read_frame(self):
        """Grab one frame as a PIL Image (RGB), or None if unavailable."""
        if not self.is_open():
            return None

        ok, frame_bgr = self._capture.read()
        if not ok or frame_bgr is None:
            return None

        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        return Image.fromarray(frame_rgb)

    def release(self):
        if self._capture is not None:
            self._capture.release()
            self._capture = None

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.release()
