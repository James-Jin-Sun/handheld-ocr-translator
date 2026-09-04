"""Local HTTP API exposing the existing OCR -> translate -> overlay pipeline
(src/main.py) so a future Flutter Web frontend (or any HTTP client) can call
it. This is a thin wrapper only -- it reuses `main.run_pipeline` as-is and
does not duplicate any OCR, translation, or overlay logic. The existing
Tkinter desktop app (src/ui/app.py) is untouched and keeps working alongside
this server.

Two image sources are supported, both feeding the same pipeline:
  - POST /api/process: laptop file upload (unchanged).
  - POST /api/capture: pulls one JPEG from an ESP32-S3 camera's own
    `GET /capture` endpoint (wireless_mvp/firmware/esp32_camera) instead of
    an uploaded file. The ESP32 never talks to Google APIs and never
    receives Google credentials -- it only ever returns a raw JPEG to this
    backend, which is the sole caller of the Google Cloud APIs.

Usage:
    python api/server.py
    # then POST an image to http://localhost:8000/api/process
"""

import sys
import threading
from datetime import datetime
from pathlib import Path

try:
    import requests
    from fastapi import FastAPI, File, Form, HTTPException, UploadFile
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import FileResponse, JSONResponse
except ImportError as exc:
    raise SystemExit(
        "Missing dependency: install it with `pip install fastapi uvicorn[standard] python-multipart requests`."
    ) from exc

# Timeout for pulling a single frame from the ESP32 -- capture + Wi-Fi upload
# of one JPEG should be quick, but the sensor can occasionally stall.
ESP32_CAPTURE_TIMEOUT_SECONDS = 15

API_DIR = Path(__file__).resolve().parent
SRC_DIR = API_DIR.parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

UPLOADS_DIR = API_DIR / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Handheld OCR Translator API")

# A Flutter Web build is served from its own origin (different port than this
# API), so the browser needs CORS allowed -- this is a local dev/companion
# tool, not a public service, so any origin is allowed.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# `main` (the pipeline module) pulls in the Google Cloud client libraries,
# which are slow to import -- load it lazily on first request, same as
# src/ui/pipeline_worker.py does for the desktop app, instead of at startup.
_pipeline_lock = threading.Lock()
_pipeline = None


def _get_pipeline():
    global _pipeline
    with _pipeline_lock:
        if _pipeline is None:
            import main as pipeline  # noqa: PLC0415 - intentional lazy/heavy import

            _pipeline = pipeline
    return _pipeline


def _result_dir(job_id):
    result_dir = _get_pipeline().DEFAULT_OUTPUT_ROOT / job_id
    if not result_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"No results for job_id {job_id!r}.")
    return result_dir


@app.get("/api/health")
def health():
    return {"status": "ok"}


def _pipeline_kwargs(target_lang, source_lang, project_id, ocr_language_hints):
    kwargs = {}
    if target_lang:
        kwargs["target_lang"] = target_lang
    if source_lang:
        kwargs["source_lang"] = source_lang
    if project_id:
        kwargs["project_id"] = project_id
    if ocr_language_hints:
        kwargs["ocr_language_hints"] = [hint.strip() for hint in ocr_language_hints.split(",") if hint.strip()]
    return kwargs


def _run_pipeline_and_build_response(job_id, image_path, kwargs):
    """Shared by /api/process and /api/capture: run the existing pipeline
    on an already-saved image and build the same response shape for both."""
    pipeline = _get_pipeline()

    try:
        saved_path, ocr_runtime = pipeline.run_pipeline(image_path, **kwargs)
    except Exception as exc:  # noqa: BLE001 - surface any pipeline failure to the caller
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if saved_path is None:
        return JSONResponse({"job_id": job_id, "text_detected": False, "ocr_runtime_seconds": ocr_runtime})

    return {
        "job_id": job_id,
        "text_detected": True,
        "ocr_runtime_seconds": ocr_runtime,
        "translated_image_url": f"/api/results/{job_id}/image",
        "manifest_url": f"/api/results/{job_id}/manifest",
    }


@app.post("/api/process")
def process_image(
    image: UploadFile = File(...),
    target_lang: str = Form(None),
    source_lang: str = Form(None),
    project_id: str = Form(None),
    ocr_language_hints: str = Form(None),  # comma-separated, e.g. "en,fr"
):
    """Run the existing OCR -> translate -> overlay pipeline on an uploaded
    image and return job info; the translated image and manifest are then
    fetched via the `/api/results/{job_id}/...` endpoints below."""
    suffix = Path(image.filename or "").suffix or ".jpg"
    job_id = f"upload_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
    upload_path = UPLOADS_DIR / f"{job_id}{suffix}"
    upload_path.write_bytes(image.file.read())

    kwargs = _pipeline_kwargs(target_lang, source_lang, project_id, ocr_language_hints)
    return _run_pipeline_and_build_response(job_id, upload_path, kwargs)


@app.post("/api/capture")
def capture_and_process(
    esp32_url: str = Form(...),  # e.g. "http://192.168.1.42" or "http://esp32cam.local"
    target_lang: str = Form(None),
    source_lang: str = Form(None),
    project_id: str = Form(None),
    ocr_language_hints: str = Form(None),  # comma-separated, e.g. "en,fr"
):
    """Pull one JPEG frame from the ESP32-S3 camera's own `GET /capture`
    endpoint (wireless_mvp/firmware/esp32_camera), then run it through the
    same OCR -> translate -> overlay pipeline as /api/process. The ESP32's
    address is supplied by the caller per-request -- it is never hardcoded
    here, and this backend remains the only component that talks to Google
    Cloud (the ESP32 and Flutter never do, and never see credentials)."""
    capture_url = esp32_url.rstrip("/") + "/capture"
    try:
        response = requests.get(capture_url, timeout=ESP32_CAPTURE_TIMEOUT_SECONDS)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach ESP32 camera at {capture_url}: {exc}") from exc

    job_id = f"esp32_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
    capture_path = UPLOADS_DIR / f"{job_id}.jpg"
    capture_path.write_bytes(response.content)

    kwargs = _pipeline_kwargs(target_lang, source_lang, project_id, ocr_language_hints)
    return _run_pipeline_and_build_response(job_id, capture_path, kwargs)


@app.get("/api/results/{job_id}/image")
def get_translated_image(job_id: str):
    result_dir = _result_dir(job_id)
    matches = list(result_dir.glob(f"{job_id}_translated.*"))
    if not matches:
        raise HTTPException(status_code=404, detail="Translated image not found.")
    return FileResponse(matches[0])


@app.get("/api/results/{job_id}/manifest")
def get_manifest(job_id: str):
    manifest_path = _result_dir(job_id) / f"{job_id}_regions.json"
    if not manifest_path.exists():
        raise HTTPException(status_code=404, detail="Manifest not found.")
    return FileResponse(manifest_path, media_type="application/json")


def main():
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
