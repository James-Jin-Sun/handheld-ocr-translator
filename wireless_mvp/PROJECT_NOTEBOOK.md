# Wireless MVP -- Project Notebook

Working log for `wireless_mvp/` specifically. Prior history (Steps 1-4: Google
Vision/Translate migration, FastAPI backend, Flutter frontend, ESP32-S3
wireless capture) is in the top-level
[`../PROJECT_NOTEBOOK.md`](../PROJECT_NOTEBOOK.md). New entries for this
subproject go here going forward.

## 2026-09-08 -- Restructured `wireless_mvp/src` into `wireless_mvp/backend`

- Moved `src/main.py`, `src/api/`, `src/ocr/`, `src/overlay/`, `src/translation/`
  into `backend/app/` (same relative layout, so the existing flat
  `sys.path`-based imports between modules still work unchanged).
- Moved `src/api/uploads/`, `src/pipeline_results/`, and the top-level
  `translated_images/` into `backend/data/` (uploads/, pipeline_results/,
  translated_images/) and stopped tracking their generated contents in git
  (new `wireless_mvp/.gitignore`).
- Pulled the two standalone smoke-test scripts
  (`overlay/test_draw_translation.py`, `translation/test_translation.py`)
  out into `backend/tests/`, with `sys.path` adjusted to still find their
  target modules under `backend/app/`.
- Deleted `src/ui/` (the wireless copy of the Tkinter desktop app --
  webcam capture, GPIO buttons, `pipeline_worker.py`): the Flutter Web
  frontend + ESP32-S3 capture flow now fully cover that role for
  `wireless_mvp`. The original desktop app is untouched at
  `laptop_mvp/src/ui/`.
- Added `backend/requirements.txt` (fastapi, uvicorn, python-multipart,
  requests, google-cloud-vision, google-cloud-translate, pillow -- the
  packages actually imported by `app/main.py` and `app/api/server.py`; the
  heavier eval-harness-only deps for `app/ocr/evaluate.py` are listed
  commented-out) and `backend/.env.example` (documents the ADC gcloud
  login flow; no code currently reads a `.env` file).
- Updated stale `wireless_mvp/src/...` path references in
  `firmware/esp32_camera/` comments and `frontend/lib/*.dart` doc comments.
