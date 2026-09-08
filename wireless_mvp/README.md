# Handheld OCR Translator -- Wireless MVP

Wireless version of the Handheld OCR Translator: an ESP32-S3 camera captures
a photo over Wi-Fi, a FastAPI backend runs it through the existing OCR ->
translate -> overlay pipeline, and a Flutter Web frontend displays the
result. The Flutter app never talks to Google Cloud directly and never
holds credentials -- the backend is the only component that calls the
Google Cloud Vision / Translation APIs.

```
wireless_mvp/
├── backend/     FastAPI server + OCR/translation/overlay pipeline (Python)
├── frontend/    Flutter Web UI
└── firmware/    ESP32-S3 PlatformIO camera firmware (Arduino)
```

## backend/

```
backend/
├── app/
│   ├── main.py          Pipeline entry point (OCR -> clean -> translate -> overlay)
│   ├── api/server.py    FastAPI app: /api/process, /api/capture, /api/results/...
│   ├── ocr/             Google Cloud Vision OCR + text clean-up (+ eval harness)
│   ├── overlay/         Blur source text, draw translated text
│   └── translation/     Google Cloud Translation API wrapper
├── data/                Generated at runtime, gitignored
│   ├── uploads/         Saved source images (laptop upload or ESP32 capture)
│   ├── pipeline_results/  Translated images + region manifests, per job_id
│   └── translated_images/
├── tests/               Standalone smoke test scripts
├── requirements.txt
└── .env.example
```

Setup:

```powershell
cd wireless_mvp/backend
pip install -r requirements.txt
gcloud auth application-default login   # once per machine, for Google Cloud APIs
gcloud config set project handheld-ocr-translator
python -m app.api.server                 # serves http://localhost:8000
```

## frontend/

```powershell
cd wireless_mvp/frontend
flutter pub get
flutter run -d chrome
```

Configure the backend URL and (optionally) the ESP32-S3 camera URL from the
app's Settings dialog.

## firmware/esp32_camera/

PlatformIO project for the `freenove_esp32_s3_wroom` board. Copy
`include/wifi_credentials.h.example` to `include/wifi_credentials.h` (git-ignored)
and fill in your Wi-Fi SSID/password before flashing. Exposes:

- `GET /capture` (port 80) -- one JPEG frame, pulled by `POST /api/capture`.
- `GET /status` (port 80) -- liveness check.
- `GET /stream` (port 81) -- MJPEG live preview for the Flutter frontend.

The ESP32 never talks to Google APIs and never receives Google credentials.
