# Project Status & Architecture

Detailed reference for the Handheld OCR Translator. See `AGENTS.md` at the
repo root for the short version and ground rules. This file describes
`wireless_mvp/` (the active prototype) in depth, with a shorter section on
`laptop_mvp/` (reference-only) at the end.

Last updated: 2026-09-15, based on a full repo inspection. Update this file
when the architecture or file layout changes meaningfully; keep the
line-by-line "what changed and when" history in `wireless_mvp/PROJECT_NOTEBOOK.md`
instead of here.

## Repo layout

```
handheld-ocr-translator/        (git root)
├── AGENTS.md
├── PROJECT_NOTEBOOK.md          history for laptop_mvp + pre-wireless work
├── docs/PROJECT_STATUS.md       this file
├── laptop_mvp/                  old wired prototype (reference only)
├── wireless_mvp/                current prototype (active development)
│   ├── PROJECT_NOTEBOOK.md      history for wireless_mvp specifically
│   ├── README.md                setup/run instructions
│   ├── backend/                 FastAPI server + OCR/translation/overlay pipeline
│   ├── frontend/                Flutter Web UI
│   └── firmware/esp32_camera/   ESP32-S3 PlatformIO camera firmware
├── assignment/, CNN_tutorial/, image_tutorial/, object_detection_tut/,
│   OCR_tutorial/                coursework scratch, unrelated to the product
```

Note: `D:\Handheld OCR Translator\esp32_camera_test\` and
`...\esp32_s3_board_test\` (siblings of this git repo, one level up) are
**standalone PlatformIO bring-up projects, not part of this repo**. They
were used to validate the Freenove ESP32-S3 pin mapping and camera init
before that code was reused in `wireless_mvp/firmware/esp32_camera/`
(see `board_config.h`'s comment).

## Architecture: `wireless_mvp`

### Data flow

```
ESP32-S3 (Freenove freenove_esp32_s3_wroom + OV2640)
 ├─ GET :80/capture → one JPEG (SVGA/800x600, rotated 180° in firmware to
 │                     match enclosure orientation)
 ├─ GET :80/status  → {"status":"ok","button_capture_count":N}
 └─ GET :81/stream  → MJPEG live preview (multipart/x-mixed-replace),
                       own port/task so it can't block /capture or /status
        │
        ▼
Flutter Web frontend (wireless_mvp/frontend)
 - Live view: MjpegView widget points directly at ESP32 :81/stream
   (direct Flutter <-> ESP32, bypasses the backend)
 - Polls ESP32 :80/status every 1s for button_capture_count
   (direct Flutter <-> ESP32, no image/credential data crosses this call)
 - "Capture Image" click OR a rising button_capture_count both call the
   same code path: POST {backend}/api/capture {esp32_url}
 - "Select Image" -> local file picker -> POST {backend}/api/process (multipart)
        │
        ▼
FastAPI backend (wireless_mvp/backend/app/api/server.py)
 - /api/capture: backend does GET {esp32_url}/capture itself, saves JPEG
   to backend/data/uploads/esp32_<timestamp>.jpg
 - /api/process: saves uploaded JPEG to backend/data/uploads/upload_<timestamp>.<ext>
 - both then call app/main.py::run_pipeline(image_path, ...):
     1. OCR: Google Cloud Vision document_text_detection
        (app/ocr/google_vision_backend.py) -> one region per paragraph
        (Vision has no native "line" concept)
     2. Clean: app/ocr/text_cleaning.py strips OCR noise per region, then
        group_lines_into_blocks() merges vertically-stacked, horizontally-
        overlapping, similar-height lines into sentence "blocks" so the
        translator sees full sentences, not fragments
     3. Translate: Google Cloud Translation v3 (general/nmt model),
        one batched call per image translating all blocks at once
        (app/translation/google_translate.py)
     4. Overlay: app/overlay/draw_translation.py
        - resolve_overlapping_boxes() nudges apart any overlapping line
          boxes first
        - split_text_across_lines() splits each block's translation back
          across the block's original lines, proportional to each line's
          source character count (snaps to spaces for word-based
          languages, character boundaries for CJK)
        - blurs each line's bbox (Gaussian blur) and draws the translated
          segment centered on top, backdrop + auto-shrinking font
 - Saves translated JPEG + `<job_id>_regions.json` manifest under
   backend/data/pipeline_results/<job_id>/
 - Returns {job_id, text_detected, ocr_runtime_seconds,
   translated_image_url, manifest_url}
        │
        ▼
Flutter fetches both result URLs, shows the translated image plus an
expandable "detected text -> translated text" table built from the
manifest's blocks.
```

Only `wireless_mvp/backend` ever imports `google.cloud.vision` /
`google.cloud.translate` or touches credentials (via
`gcloud auth application-default login`, project
`handheld-ocr-translator`). The ESP32 and Flutter never see Google
credentials and never call Google directly — this is a hard architectural
invariant, not just current practice.

### File map

| Subsystem | Files | Notes |
|---|---|---|
| ESP32 firmware | `firmware/esp32_camera/src/main.cpp` | Camera init, `/capture`, `/status`, `/stream`, GPIO21 button polling |
| | `src/board_config.h`, `src/camera_pins.h` | Freenove pin map, reused verbatim from `esp32_camera_test` |
| | `include/wifi_credentials.h` (gitignored; `.h.example` tracked) | Wi-Fi SSID/password, must be created locally before flashing |
| | `platformio.ini` | `env:freenove_esp32_s3_wroom`, Arduino framework |
| Backend entry/pipeline | `backend/app/main.py` | `run_pipeline()` — the single source of truth for OCR→translate→overlay; also runnable as a CLI (`python -m app.main --image ...`) |
| Backend HTTP API | `backend/app/api/server.py` | `/api/health`, `/api/process`, `/api/capture`, `/api/results/{job_id}/image`, `/api/results/{job_id}/manifest`; lazy-imports `app/main.py` on first request (Google client libs are slow to import) |
| OCR (live) | `backend/app/ocr/google_vision_backend.py`, `text_cleaning.py` | Only these two are used by the running pipeline |
| OCR (inert eval harness) | `backend/app/ocr/{paddleocr_backend,easyocr_backend,evaluate,ground_truth,dataset,metrics,results,config,ocr}.py` | Carried over from `laptop_mvp`'s OCR-engine benchmarking (Tesseract/EasyOCR/PaddleOCR vs ICDAR2013 ground truth). Not imported by `app/main.py`; only relevant if a task is specifically about OCR-engine comparison |
| Translation | `backend/app/translation/google_translate.py` | `translate_text` (single) / `translate_batch`; default `DEFAULT_PROJECT_ID = "handheld-ocr-translator"`, `DEFAULT_TARGET_LANGUAGE = "zh-CN"` |
| Overlay | `backend/app/overlay/draw_translation.py` | Blur, draw, proportional line-splitting, box-overlap resolution |
| Backend data (generated, gitignored) | `backend/data/{uploads,pipeline_results}/` | Actively used. `backend/data/translated_images/` is created/gitignored but **nothing currently writes to it** — likely a leftover from the `laptop_mvp` -> `wireless_mvp` restructuring |
| Backend tests | `backend/tests/{test_draw_translation,test_translation}.py` | Standalone smoke scripts, not a pytest suite; no tests exist for the FastAPI routes themselves |
| Flutter UI | `frontend/lib/main.dart` | 3-screen state machine (`camera` / `captured` / `processing` / `translated`) mirroring the old Tkinter app's flow; owns the physical-button poll timer |
| Flutter API client | `frontend/lib/api_client.dart` | HTTP client to the backend (`processImage`, `captureFromEsp32`, `fetchResultImage`, `fetchManifest`) plus one direct-to-ESP32 call (`fetchEsp32ButtonPressCount`) |
| Flutter models | `frontend/lib/models.dart` | `ProcessResult`, `Manifest`, `TranslatedBlock` — mirror the backend's JSON shapes |
| Flutter MJPEG view | `frontend/lib/mjpeg_view_web.dart` / `mjpeg_view_stub.dart` | Web-only `<img>`-based MJPEG viewer, conditional import so non-web builds don't break |

### Setup / run (from `wireless_mvp/README.md`)

```powershell
# Backend
cd wireless_mvp/backend
pip install -r requirements.txt
gcloud auth application-default login
gcloud config set project handheld-ocr-translator
python -m app.api.server        # serves http://localhost:8000

# Frontend
cd wireless_mvp/frontend
flutter pub get
flutter run -d chrome           # Flutter Web only today, no android/ios platform folders

# Firmware
# copy firmware/esp32_camera/include/wifi_credentials.h.example
#   -> .../include/wifi_credentials.h, fill in SSID/password (gitignored)
# flash with PlatformIO, env:freenove_esp32_s3_wroom
```

Backend URL, ESP32 camera URL, target/source language, and OCR language
hints are all configured from the Flutter app's in-app Settings dialog —
nothing is hardcoded except the defaults (`localhost:8000`,
`http://esp32cam.local`, `zh-CN`).

## Current development state

- Steps 1–4 of the wireless migration (Google Vision OCR → FastAPI backend
  → Flutter Web frontend → ESP32-S3 wireless capture) are complete and
  committed. Recent commit history (newest first):
  `22636ae refractor backend`, `66ac815 move frontend to proper place`,
  `751d1ed integrated esp32_camera`, `e0a79db updated UI`,
  `14b45a5 created python backend`, `31a2056 replace PaddleOCR with Google Vision`.
- **Active uncommitted work as of this writing**: two physical UI buttons
  on the ESP32, generalized to mirror whichever on-screen action is
  currently shown on that side of the Flutter UI (not fixed to "capture"
  anymore). Code-complete on both ends:
  - Firmware (`main.cpp`): GPIO21 = "left", GPIO41 = "right", both wired
    with the ESP32's **internal** pull-up (`INPUT_PULLUP`) — confirmed
    working on real hardware for GPIO21 after an earlier external-pull-up
    attempt; GPIO41 is not yet hardware-tested. A shared `DebouncedButton`
    struct + `pollButton()`/`pollButtons()` debounce each independently
    and bump its own `pressCount`, exposed via `/status` as
    `{"status":"ok","left_button_count":N,"right_button_count":N}`. A
    press received mid-capture (`g_captureInProgress`) is dropped for
    either button, not queued. The firmware has no notion of what a press
    *does* — it never calls the backend itself.
  - Flutter (`main.dart` / `api_client.dart`): a 1s `Timer.periodic` calls
    `fetchEsp32ButtonPressCounts()` (returns a `ButtonPressCounts { left,
    right }`); on an increase, `_onLeftButtonPressed()` /
    `_onRightButtonPressed()` dispatch via a `switch` on the current
    `_screen` to whatever `_buildControls()` shows on that side:
    camera (left=Capture Image, right=Select Image), captured
    (left=Confirm, right=Close/Retake), translated (left=Save,
    right=Close/Restart), processing (both no-ops — no buttons shown).
    If both counters advance in the same poll, left wins and right is
    picked up on the next poll.
  - Also uncommitted: `wireless_mvp/frontend/analysis_options.yaml`
    (excludes `build/**`, `web/**` from analysis) and a `pubspec.lock`
    bump.
  - `laptop_mvp/src/ui/test_gpio_buttons.py` shows as modified in
    `git status` but has an empty `git diff` — likely a line-ending/mode
    change only; verify before committing.
  - See `wireless_mvp/PROJECT_NOTEBOOK.md` (2026-09-15 entry) for the
    detailed change log. Next step: hardware bring-up test of the new
    GPIO41 right button, then a full click-through of all four screens
    with both physical buttons.

## Known gaps / TODO

- No automated tests for the FastAPI routes (`/api/process`,
  `/api/capture`, `/api/results/...`) — only two standalone pipeline
  smoke scripts exist.
- `split_text_across_lines`'s proportional character-count split breaks
  down for blocks with many merged lines where the translation
  reorders/compresses content differently than the source (e.g. multi-line
  address blocks) — a known, explicitly-deferred quality tradeoff, not a
  bug (see `PROJECT_NOTEBOOK.md`, 2026-07-20 entry).
- `backend/data/translated_images/` is unused dead weight from the
  restructuring; either wire it up or remove the gitignore entry/mkdir if
  it comes up.
- `backend/app/ocr/` eval harness (Tesseract/EasyOCR/PaddleOCR) has no
  connection to the live pipeline; consider whether it should move to a
  separate tools/ or eval/ location if it keeps causing confusion about
  "which OCR engine is actually used" (answer: only Google Vision, live).
- Flutter frontend is Web-only; mobile (Android/iOS) platform folders
  don't exist yet, referenced as a future step in the original project
  description ("preparing for later deployment to a phone").

## `laptop_mvp` (reference only, do not modify unnecessarily)

Original wired prototype, Tkinter desktop app:

- `src/ui/app.py` — 3-frame Tkinter state machine (camera / captured /
  translated), webcam capture via `src/ui/camera.py` (OpenCV, auto-detects
  known external UVC cameras by DirectShow name), optional Jetson GPIO
  buttons (`gpio_buttons.py`, pins 29/31) as an alternative to mouse
  clicks, background-threaded pipeline execution (`pipeline_worker.py`).
- `src/main.py` — pipeline: PaddleOCR (`ocr/paddleocr_backend.py`) → clean
  → translate (`translation/google_translate.py`) → blur & overlay
  (`overlay/draw_translation.py`). This is the pipeline `wireless_mvp`
  forked from before swapping PaddleOCR for Google Vision.
- `src/ocr/` also contains the original Tesseract/EasyOCR/PaddleOCR
  benchmarking harness against ICDAR2013 (`evaluate.py` + friends) — this
  is where that code originates before being copied into
  `wireless_mvp/backend/app/ocr/`.
- Full dated history of OCR-engine comparisons and UI development is in
  the root `PROJECT_NOTEBOOK.md`.
