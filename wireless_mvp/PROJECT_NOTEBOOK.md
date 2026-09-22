# Wireless MVP -- Project Notebook

Working log for `wireless_mvp/` specifically. Prior history (Steps 1-4: Google
Vision/Translate migration, FastAPI backend, Flutter frontend, ESP32-S3
wireless capture) is in the top-level
[`../PROJECT_NOTEBOOK.md`](../PROJECT_NOTEBOOK.md). New entries for this
subproject go here going forward.

## 2026-09-15 -- Generalized the physical capture button into left/right UI buttons

- Hardware test confirmed GPIO21 works with the ESP32's **internal**
  pull-up (`INPUT_PULLUP`) instead of the external pull-up originally
  assumed; switched to `INPUT_PULLUP` for good.
- Added a second physical button on **GPIO41**. The two buttons are no
  longer capture-specific: GPIO21 = "left", GPIO41 = "right", and each
  just increments its own debounced press counter -- the firmware has no
  notion of what a press *does* anymore.
  - `firmware/esp32_camera/src/main.cpp`: replaced the single-button
    globals with a `DebouncedButton` struct (`pin`, `pressCount`,
    debounce state) instantiated once per button; `pollButton()` /
    `pollButtons()` replace the old `pollCaptureButton()`. `GET /status`
    now returns `{"status":"ok","left_button_count":N,"right_button_count":N}`
    instead of `button_capture_count`.
- Flutter now maps each physical button to whatever on-screen action
  currently occupies that side of the UI for the active screen, matching
  `_buildControls()`'s existing left/right layout, instead of only ever
  triggering "Capture Image":
  - camera: left -> Capture Image, right -> Select Image
  - captured: left -> Confirm, right -> Close/Retake
  - translated: left -> Save, right -> Close/Restart
  - processing: both are no-ops (no buttons shown on that screen)
  - `frontend/lib/api_client.dart`: `fetchEsp32ButtonPressCount()` ->
    `fetchEsp32ButtonPressCounts()`, returning a new `ButtonPressCounts`
    model (`models.dart`) instead of a bare `int`.
  - `frontend/lib/main.dart`: `_pollPhysicalButton()` ->
    `_pollPhysicalButtons()`, tracking both counters and dispatching to
    new `_onLeftButtonPressed()` / `_onRightButtonPressed()` methods
    (one `switch` on `_screen` each, mirroring `_buildControls()`). If
    both counters advance in the same 1s poll, left is handled first and
    right is picked up on the next poll rather than firing both at once.

### Next Steps

- Physical bring-up test of the new GPIO41 right button (only GPIO21 has
  been hardware-tested so far).
- Confirm both buttons behave correctly through all four screens on real
  hardware, not just by inspection.

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
