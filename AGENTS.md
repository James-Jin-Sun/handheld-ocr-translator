# AGENTS.md

Guidance for AI coding agents (and humans) working in this repo.

## What this project is

A handheld OCR translator: capture an image of text → OCR → translate → blur
the original text → overlay the translation → show the result. Long-term
goal is a clip-on wireless device (eventually smart-glasses-compatible).

## Two generations in this repo

- **`laptop_mvp/`** — the original wired prototype (Tkinter UI, OpenCV
  webcam, PaddleOCR, direct-to-Google-Translate). It's a **working
  reference implementation only**. Do not modify it unless a task
  explicitly targets it.
- **`wireless_mvp/`** — the **active development target**. ESP32-S3 +
  OV2640 camera over Wi-Fi → FastAPI backend → Google Cloud Vision (OCR) +
  Google Cloud Translation → Flutter Web frontend. Nearly all new work
  belongs here.

Everything else at the repo root (`assignment/`, `CNN_tutorial/`,
`image_tutorial/`, `object_detection_tut/`, `OCR_tutorial/`) is coursework
scratch work, unrelated to the product.

**For full architecture, data flow, file map, and current state, read
[`docs/PROJECT_STATUS.md`](docs/PROJECT_STATUS.md) before making changes.**
Also check `wireless_mvp/PROJECT_NOTEBOOK.md` (and the root
`PROJECT_NOTEBOOK.md` for `laptop_mvp` history) for the dated work log —
update it after nontrivial changes, following its existing entry format.

## Ground rules

- **`wireless_mvp` is wireless end-to-end**: the ESP32 never talks to
  Google APIs and never receives Google credentials. The FastAPI backend
  is the *only* component allowed to import `google.cloud.*` or hold
  credentials. Do not add Google Cloud calls to the Flutter app or the
  ESP32 firmware.
- Backend auth is Application Default Credentials (`gcloud auth
  application-default login`, project `handheld-ocr-translator`) — no
  `.env` file is read by any code; don't wire one up without asking.
- Python modules under `wireless_mvp/backend/app/*` use flat
  `sys.path.insert(...)`-based imports between sibling packages (no
  relative package imports, no shared `__init__.py` re-exports). Match
  this style rather than introducing a different import convention.
- `wireless_mvp/backend/app/ocr/` contains a full multi-engine OCR
  benchmark harness (Tesseract/EasyOCR/PaddleOCR + ICDAR2013 eval) carried
  over from `laptop_mvp`. Only `google_vision_backend.py` +
  `text_cleaning.py` are used by the live pipeline (`app/main.py`) — the
  rest is inert unless a task is specifically about OCR-engine evaluation.
- Check `git status`/`git diff` before starting: this repo often has
  in-progress, uncommitted work (e.g. the ESP32 GPIO21/GPIO41 left/right
  physical button feature) that isn't reflected in the last commit.
- Don't assume filenames/ports/IPs/endpoints from prose descriptions —
  verify against the actual code, which sometimes lags or diverges from
  written docs.
