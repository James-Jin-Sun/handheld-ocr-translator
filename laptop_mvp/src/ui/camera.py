"""Webcam capture wrapper built on OpenCV, yielding PIL images."""

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


class Camera:
    """Thin wrapper around `cv2.VideoCapture` that hands back PIL images."""

    def __init__(self, device_index=0):
        self.device_index = device_index
        self._capture = None

    def open(self):
        """Open the camera device. Returns True if it is usable."""
        if self._capture is None:
            self._capture = cv2.VideoCapture(self.device_index)
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
