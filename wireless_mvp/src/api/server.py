"""Local HTTP API exposing the existing OCR -> translate -> overlay pipeline
(src/main.py) so a future Flutter Web frontend (or any HTTP client) can call
it. This is a thin wrapper only -- it reuses `main.run_pipeline` as-is and
does not duplicate any OCR, translation, or overlay logic. The existing
Tkinter desktop app (src/ui/app.py) is untouched and keeps working alongside
this server.

Usage:
    python api/server.py
    # then POST an image to http://localhost:8000/api/process
"""

import sys
import threading
from datetime import datetime
from pathlib import Path

try:
    from fastapi import FastAPI, File, Form, HTTPException, UploadFile
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import FileResponse, JSONResponse
except ImportError as exc:
    raise SystemExit(
        "Missing dependency: install it with `pip install fastapi uvicorn[standard] python-multipart`."
    ) from exc

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
    pipeline = _get_pipeline()

    suffix = Path(image.filename or "").suffix or ".jpg"
    job_id = f"upload_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
    upload_path = UPLOADS_DIR / f"{job_id}{suffix}"
    upload_path.write_bytes(image.file.read())

    kwargs = {}
    if target_lang:
        kwargs["target_lang"] = target_lang
    if source_lang:
        kwargs["source_lang"] = source_lang
    if project_id:
        kwargs["project_id"] = project_id
    if ocr_language_hints:
        kwargs["ocr_language_hints"] = [hint.strip() for hint in ocr_language_hints.split(",") if hint.strip()]

    try:
        saved_path, ocr_runtime = pipeline.run_pipeline(upload_path, **kwargs)
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
