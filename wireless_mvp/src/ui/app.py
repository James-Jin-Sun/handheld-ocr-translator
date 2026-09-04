"""Tkinter UI for the Handheld OCR Translator MVP.

Frame 1 - Default camera view: live webcam feed + "Capture Image" (bottom
    left) / "Select Image" (bottom right, pick an existing file instead).
Frame 2 - Image captured: static captured frame + "Confirm" / "Close / Retake".
Frame 3 - Translation completed: translated image + "Save" (bottom left) /
    "Close / Restart" (bottom right).

Flow:
    Frame 1 --Capture Image / Select Image--> Frame 2
    Frame 2 --Close / Retake--> Frame 1
    Frame 2 --Confirm--> [OCR -> Translation -> Overlay, on a background
        thread] --> Frame 3
    Frame 3 --Save--> (file saved, stays on Frame 3)
    Frame 3 --Close / Restart--> Frame 1

Usage:
    python app.py
"""

import sys
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox

UI_DIR = Path(__file__).resolve().parent
SRC_DIR = UI_DIR.parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from PIL import Image, ImageTk  # noqa: E402

from camera import Camera  # noqa: E402
from gpio_buttons import GpioButtons  # noqa: E402
from pipeline_worker import run_pipeline_async  # noqa: E402

APP_TITLE = "Handheld OCR Translator"
IMAGE_AREA_SIZE = (820, 560)
CAMERA_REFRESH_MS = 33  # ~30 fps
CAPTURES_DIR = UI_DIR / "captures"
LAPTOP_MVP_DIR = SRC_DIR.parent
TRANSLATED_IMAGES_DIR = LAPTOP_MVP_DIR / "translated_images"

STATE_CAMERA = "camera"
STATE_CAPTURED = "captured"
STATE_PROCESSING = "processing"
STATE_TRANSLATED = "translated"

BUTTON_STYLE = {
    "font": ("Segoe UI", 12),
    "padx": 24,
    "pady": 10,
    "relief": "raised",
    "cursor": "hand2",
}

STATUS_COLOR_NORMAL = "#cccccc"
STATUS_COLOR_WARNING = "#f08080"
NO_CAMERA_STATUS_TEXT = "No camera detected. Connect a camera to resume live view, or use 'Select Image'."
NO_CAMERA_PLACEHOLDER_TEXT = "LIVE CAMERA VIEW\n(no camera detected)"


def _resample_filter():
    if hasattr(Image, "Resampling"):
        return Image.Resampling.LANCZOS
    return Image.LANCZOS


def resize_to_fit(image, max_size):
    """Return a copy of `image` scaled down (preserving aspect ratio) to fit
    within `max_size` (width, height). Never upscales."""
    max_width, max_height = max_size
    width, height = image.size
    scale = min(max_width / width, max_height / height, 1.0)
    if scale >= 1.0:
        return image.copy()
    new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
    return image.resize(new_size, _resample_filter())


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.configure(bg="#1e1e1e")
        self.resizable(False, False)

        self.state_name = STATE_CAMERA
        self.camera = Camera()
        self.captured_image = None  # PIL Image captured from the live feed
        self.captured_image_path = None
        self.selected_image_path = None  # set only when the image came from "Select Image"
        self.translated_image_path = None
        self._last_camera_frame = None
        self._camera_job = None
        self._display_photo = None  # keep a reference so Tk doesn't GC it
        # None = not checked yet (used to show the one-time startup prompt);
        # True/False = last connection state the UI has reacted to, so
        # ongoing polling only updates the UI on an actual state change.
        self._camera_connected = None

        # Optional physical buttons (Jetson GPIO pins 29/31) standing in for
        # mouse clicks -- None on platforms without GPIO support (e.g. the
        # Windows laptop MVP), in which case the UI is mouse/keyboard-only.
        self.gpio_buttons = GpioButtons.create(
            on_primary=self._on_gpio_primary_button,
            on_secondary=self._on_gpio_secondary_button,
        )

        self._build_widgets()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        CAPTURES_DIR.mkdir(parents=True, exist_ok=True)
        TRANSLATED_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
        self._enter_camera_state()

    # ---- widget setup -----------------------------------------------

    def _build_widgets(self):
        width, height = IMAGE_AREA_SIZE

        image_frame = tk.Frame(self, width=width, height=height, bg="black")
        image_frame.pack_propagate(False)
        image_frame.pack(side="top", padx=10, pady=(10, 0))

        self.image_label = tk.Label(
            image_frame,
            bg="black",
            fg="white",
            font=("Segoe UI", 20),
            text="LIVE CAMERA VIEW",
        )
        self.image_label.pack(fill="both", expand=True)

        self.status_var = tk.StringVar(value="")
        self.status_label = tk.Label(
            self,
            textvariable=self.status_var,
            bg="#1e1e1e",
            fg=STATUS_COLOR_NORMAL,
            font=("Segoe UI", 11),
            anchor="w",
        )
        self.status_label.pack(side="top", fill="x", padx=14, pady=(8, 0))

        self.controls_frame = tk.Frame(self, bg="#1e1e1e", height=70)
        self.controls_frame.pack_propagate(False)
        self.controls_frame.pack(side="top", fill="x", padx=10, pady=10)

    def _clear_controls(self):
        for child in self.controls_frame.winfo_children():
            child.destroy()

    def _show_camera_controls(self):
        self._clear_controls()
        self.capture_button = tk.Button(
            self.controls_frame,
            text="Capture Image",
            command=self._on_capture_clicked,
            **BUTTON_STYLE,
        )
        self.capture_button.pack(side="left", padx=10, pady=5)
        tk.Button(
            self.controls_frame,
            text="Select Image",
            command=self._on_select_image_clicked,
            **BUTTON_STYLE,
        ).pack(side="right", padx=10, pady=5)
        self._sync_capture_button_state()

    def _show_captured_controls(self):
        self._clear_controls()
        tk.Button(
            self.controls_frame,
            text="Confirm",
            command=self._on_confirm_clicked,
            **BUTTON_STYLE,
        ).pack(side="left", padx=10, pady=5)
        tk.Button(
            self.controls_frame,
            text="Close / Retake",
            command=self._on_retake_clicked,
            **BUTTON_STYLE,
        ).pack(side="right", padx=10, pady=5)

    def _show_processing_controls(self):
        self._clear_controls()
        tk.Label(
            self.controls_frame,
            text="Processing...",
            font=("Segoe UI", 12),
            bg="#1e1e1e",
            fg="#f5c518",
        ).pack(side="left", padx=10, pady=5)

    def _show_translated_controls(self):
        self._clear_controls()
        tk.Button(
            self.controls_frame,
            text="Save",
            command=self._on_save_clicked,
            **BUTTON_STYLE,
        ).pack(side="left", padx=10, pady=5)
        tk.Button(
            self.controls_frame,
            text="Close / Restart",
            command=self._on_restart_clicked,
            **BUTTON_STYLE,
        ).pack(side="right", padx=10, pady=5)

    # ---- image display -------------------------------------------------

    def _display_image(self, pil_image):
        resized = resize_to_fit(pil_image, IMAGE_AREA_SIZE)
        photo = ImageTk.PhotoImage(resized)
        self._display_photo = photo  # keep a reference, Tk drops GC'd images
        self.image_label.configure(image=photo, text="")

    def _clear_image(self, placeholder_text):
        self._display_photo = None
        self.image_label.configure(image="", text=placeholder_text)

    # ---- camera connection status ----------------------------------------

    def _set_status(self, text, warning=False):
        self.status_var.set(text)
        self.status_label.configure(fg=STATUS_COLOR_WARNING if warning else STATUS_COLOR_NORMAL)

    def _sync_capture_button_state(self):
        capture_button = getattr(self, "capture_button", None)
        if capture_button is None or not capture_button.winfo_exists():
            return
        capture_button.configure(state="normal" if self._camera_connected else "disabled")

    def _apply_camera_connection_state(self, connected):
        """Update status text/placeholder/button state on a connection-state
        change, and (only the very first time, at startup) pop up a modal
        warning if no camera is present. Called both right after an
        open()/reconnect attempt and from the per-frame poll loop, so it
        covers startup, ongoing disconnects, and automatic reconnects."""
        previously_connected = self._camera_connected
        first_check = previously_connected is None
        self._camera_connected = connected

        if connected:
            if previously_connected is not True:
                self._set_status(
                    "Camera reconnected - live view resumed."
                    if previously_connected is False
                    else "Live camera view - point at text, then capture."
                )
        else:
            self._clear_image(NO_CAMERA_PLACEHOLDER_TEXT)
            self._set_status(NO_CAMERA_STATUS_TEXT, warning=True)
            if first_check:
                messagebox.showwarning(
                    APP_TITLE,
                    "No camera detected.\n\n"
                    "Connect a camera to use the live view, or use 'Select Image' "
                    "to load an existing photo instead. The live feed will start "
                    "automatically once a camera is connected.",
                )

        self._sync_capture_button_state()

    # ---- Frame 1: live camera view --------------------------------------

    def _enter_camera_state(self):
        self.state_name = STATE_CAMERA
        self.captured_image = None
        self.selected_image_path = None
        self._show_camera_controls()

        connected = self.camera.is_open() or self.camera.open()
        self._apply_camera_connection_state(connected)
        self._schedule_camera_update()

    def _schedule_camera_update(self):
        self._cancel_camera_job()
        self._update_camera_frame()

    def _cancel_camera_job(self):
        if self._camera_job is not None:
            self.after_cancel(self._camera_job)
            self._camera_job = None

    def _update_camera_frame(self):
        if self.state_name != STATE_CAMERA:
            return

        frame = self.camera.read_frame()
        if frame is not None:
            self._last_camera_frame = frame
            self._display_image(frame)
            if not self._camera_connected:
                self._apply_camera_connection_state(True)
        elif not self.camera.connected:
            # No frame and the camera is (still, or newly) considered
            # disconnected -- keep periodically retrying so a reconnected
            # camera is picked back up automatically without a restart.
            reconnected = self.camera.try_reconnect()
            if reconnected != self._camera_connected:
                self._apply_camera_connection_state(reconnected)

        self._camera_job = self.after(CAMERA_REFRESH_MS, self._update_camera_frame)

    def _on_capture_clicked(self):
        if self._last_camera_frame is None:
            messagebox.showwarning(APP_TITLE, "No camera frame available yet -- please wait a moment and retry.")
            return

        self._cancel_camera_job()
        self.captured_image = self._last_camera_frame.copy()
        self._enter_captured_state()

    def _on_select_image_clicked(self):
        file_path = filedialog.askopenfilename(
            title="Select an image",
            initialdir=str(CAPTURES_DIR),
            filetypes=[
                ("Image files", "*.jpg *.jpeg *.png *.bmp *.gif *.tiff"),
                ("All files", "*.*"),
            ],
        )
        if not file_path:
            return

        try:
            with Image.open(file_path) as image:
                selected_image = image.convert("RGB").copy()
        except Exception as exc:  # noqa: BLE001 - surface any load failure to the user
            messagebox.showerror(APP_TITLE, f"Could not open image:\n{exc}")
            return

        self._cancel_camera_job()
        self.captured_image = selected_image
        # Already exists on disk -- confirm should use it directly instead of
        # re-saving a duplicate copy into the captures folder.
        self.selected_image_path = Path(file_path)
        self._enter_captured_state()

    # ---- Frame 2: image captured ----------------------------------------

    def _enter_captured_state(self):
        self.state_name = STATE_CAPTURED
        self.status_var.set("Image captured. Confirm to translate, or retake.")
        self._display_image(self.captured_image)
        self._show_captured_controls()

    def _on_retake_clicked(self):
        self._enter_camera_state()

    def _on_confirm_clicked(self):
        if self.captured_image is None:
            return

        if self.selected_image_path is not None:
            # Image was picked via "Select Image" and already exists on disk --
            # feed it to the pipeline as-is instead of saving a duplicate copy.
            capture_path = self.selected_image_path
        else:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            capture_path = CAPTURES_DIR / f"capture_{timestamp}.jpg"
            self.captured_image.convert("RGB").save(capture_path)
        self.captured_image_path = capture_path

        self._enter_processing_state()
        run_pipeline_async(
            capture_path,
            on_done=self._on_pipeline_done,
            on_error=self._on_pipeline_error,
        )

    # ---- processing (between Frame 2 and Frame 3) -----------------------

    def _enter_processing_state(self):
        self.state_name = STATE_PROCESSING
        self.status_var.set("Processing: OCR -> Translation -> Overlay... this can take up to a minute.")
        self._show_processing_controls()

    def _on_pipeline_done(self, saved_path, ocr_runtime):
        # Called from the worker thread -- hop back onto the Tk main thread.
        self.after(0, self._handle_pipeline_done, saved_path, ocr_runtime)

    def _handle_pipeline_done(self, saved_path, ocr_runtime):
        if saved_path is None:
            messagebox.showinfo(
                APP_TITLE, f"No text was detected in the captured image.\nOCR took {ocr_runtime:.2f}s."
            )
            self._enter_captured_state()
            return

        self.translated_image_path = Path(saved_path)
        self._enter_translated_state(ocr_runtime)

    def _on_pipeline_error(self, exc):
        # Called from the worker thread -- hop back onto the Tk main thread.
        self.after(0, self._handle_pipeline_error, exc)

    def _handle_pipeline_error(self, exc):
        messagebox.showerror(APP_TITLE, f"Translation pipeline failed:\n{exc}")
        self._enter_captured_state()

    # ---- Frame 3: translation completed ---------------------------------

    def _enter_translated_state(self, ocr_runtime):
        self.state_name = STATE_TRANSLATED
        self.status_var.set(f"Translation complete. (OCR: {ocr_runtime:.2f}s)")
        with Image.open(self.translated_image_path) as translated_image:
            self._display_image(translated_image.convert("RGB"))
        self._show_translated_controls()

    def _on_save_clicked(self):
        if self.translated_image_path is None or not Path(self.translated_image_path).exists():
            messagebox.showwarning(APP_TITLE, "No translated image available to save.")
            return

        source_path = Path(self.translated_image_path)
        destination = filedialog.asksaveasfilename(
            title="Save translated image",
            initialdir=str(TRANSLATED_IMAGES_DIR),
            initialfile=source_path.name,
            defaultextension=source_path.suffix or ".jpg",
            filetypes=[("JPEG image", "*.jpg *.jpeg"), ("PNG image", "*.png"), ("All files", "*.*")],
        )
        if not destination:
            return

        try:
            with Image.open(source_path) as image:
                image.convert("RGB").save(destination)
        except Exception as exc:  # noqa: BLE001 - surface any save failure to the user
            messagebox.showerror(APP_TITLE, f"Could not save image:\n{exc}")
            return

        messagebox.showinfo(APP_TITLE, f"Saved translated image to:\n{destination}")

    def _on_restart_clicked(self):
        self._enter_camera_state()

    # ---- physical GPIO buttons (optional, Jetson only) --------------------
    #
    # Each screen shows two on-screen buttons (left = "primary"/move forward,
    # right = "secondary"/go back or pick alternate). The two physical
    # buttons mirror that same left/right convention so they act as a
    # drop-in replacement for mouse clicks, whichever screen is showing.

    def _on_gpio_primary_button(self):
        # Called from a Jetson.GPIO background thread -- hop onto the Tk main thread.
        self.after(0, self._handle_primary_action)

    def _on_gpio_secondary_button(self):
        # Called from a Jetson.GPIO background thread -- hop onto the Tk main thread.
        self.after(0, self._handle_secondary_action)

    def _handle_primary_action(self):
        if self.state_name == STATE_CAMERA:
            self._on_capture_clicked()
        elif self.state_name == STATE_CAPTURED:
            self._on_confirm_clicked()
        elif self.state_name == STATE_TRANSLATED:
            self._on_save_clicked()
        # STATE_PROCESSING: no on-screen buttons, so no-op.

    def _handle_secondary_action(self):
        if self.state_name == STATE_CAMERA:
            self._on_select_image_clicked()
        elif self.state_name == STATE_CAPTURED:
            self._on_retake_clicked()
        elif self.state_name == STATE_TRANSLATED:
            self._on_restart_clicked()
        # STATE_PROCESSING: no on-screen buttons, so no-op.

    # ---- lifecycle --------------------------------------------------------

    def _on_close(self):
        self._cancel_camera_job()
        self.camera.release()
        if self.gpio_buttons is not None:
            self.gpio_buttons.close()
        self.destroy()


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
