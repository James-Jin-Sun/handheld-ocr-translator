"""Runs the OCR -> translate -> overlay pipeline (src/main.py) on a
background thread so the UI stays responsive while PaddleOCR/Translate run.
"""

import sys
import threading
from pathlib import Path

UI_DIR = Path(__file__).resolve().parent
SRC_DIR = UI_DIR.parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def run_pipeline_async(image_path, on_done, on_error, **pipeline_kwargs):
    """Run the full pipeline on a background thread.

    `main` (the pipeline module) is imported lazily inside the worker thread
    on first use, since it pulls in PaddleOCR/paddle, which is slow to import.

    `on_done(saved_path, ocr_runtime)` and `on_error(exception)` are invoked
    from the worker thread -- callers must marshal back to the UI thread
    themselves (e.g. via `root.after(0, ...)`) before touching any Tkinter
    widgets.
    """

    def worker():
        try:
            import main as pipeline  # noqa: PLC0415 - intentional lazy/heavy import

            saved_path, ocr_runtime = pipeline.run_pipeline(image_path, **pipeline_kwargs)
            on_done(saved_path, ocr_runtime)
        except Exception as exc:  # noqa: BLE001 - surface any pipeline failure to the UI
            on_error(exc)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    return thread
