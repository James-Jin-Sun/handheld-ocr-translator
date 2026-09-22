# Handheld OCR Translator

A prototype of an AI-powered smart-glass companion: point a camera at printed text, read it, translate it, and overlay the translation on the original image. The long-term goal is a clip-on wireless viewer; this repo holds two working steps toward that device.

```
Capture image → OCR → translate → blur source text → overlay translation → display
```

There are two prototypes in this repository:

| | `laptop_mvp/` | `wireless_mvp/` |
|---|---|---|
| Role | First wired prototype | Current portable prototype |
| Camera | Webcam (OpenCV) on a Jetson Orin Nano | Freenove ESP32-S3 + OV2640 over Wi-Fi |
| UI | Tkinter desktop app | Flutter (web and Android) |
| OCR | PaddleOCR on-device | Google Cloud Vision (via the backend) |

---

## Technology

**Laptop MVP**

- Python, OpenCV, Tkinter
- PaddleOCR (live pipeline); Tesseract / EasyOCR / PaddleOCR eval harness on ICDAR2013
- Google Cloud Translation (Advanced v3)
- Pillow (blur + overlay)
- NVIDIA Jetson Orin Nano GPIO (`Jetson.GPIO`) for physical buttons

**Wireless MVP**

- Freenove ESP32-S3 Camera Board Kit (ESP32-S3 + OV2640), Arduino / PlatformIO
- FastAPI backend (Python)
- Google Cloud Vision (OCR) + Google Cloud Translation
- Flutter frontend (Chrome and Android / MuMu)
- Hardware: TPS61023 boost converter, 3.7 V LiPo, push button, slide switch, perf board

The ESP32 and Flutter app never talk to Google Cloud and never hold credentials. Only the FastAPI backend calls Vision and Translation.

---

## Features

- Capture from a live camera or pick an existing image
- OCR with bounding boxes, then sentence-level grouping so translation keeps context
- Batch translation (default target: Simplified Chinese, `zh-CN`)
- Blur the original text and draw the translation in place, split back across the source line boxes
- Physical buttons that mirror on-screen left/right actions (capture / confirm / save, and the matching right-side actions)
- Wireless live preview from the ESP32 (`GET :81/stream`) plus on-demand still capture (`GET :80/capture`)
- In-app settings for backend URL, camera URL, and languages

---

## The process

I built this in two generations.

**1. Laptop MVP — webcam + Jetson Orin Nano**

I started with a USB webcam and a Jetson Orin Nano. OpenCV captured the live feed; a Tkinter UI walked through camera → confirm → translated result. OCR and translation ran on the Jetson (PaddleOCR + Google Translate). Two GPIO buttons stood in for mouse clicks so the unit could be used as a handheld without a pointer.

**2. Wireless MVP — ESP32-S3 camera + portable power**

I then moved the camera off the Jetson onto a **Freenove ESP32-S3 Camera Board Kit (ESP32-S3 + OV2640)**. The board serves JPEG stills and an MJPEG preview over Wi-Fi. A FastAPI backend on a laptop pulls one frame, runs OCR → translate → overlay, and a Flutter app shows the live view and the result.

To make it portable, I soldered a prototype on a perf board with:

- **TPS61023** boost converter
- **3.7 V LiPo** battery
- **Push button** (capture / UI left action)
- **Slide switch** (power)

The Flutter UI runs in the browser or as an Android app (tested in MuMu Player).

---

## What I learned

### Image processing with OpenCV

Live capture with `VideoCapture`, camera selection (external UVC vs built-in webcam), resolution control, and feeding frames into the OCR pipeline. Overlay work used region crops, Gaussian blur of source text, and drawing translated glyphs back into each line box.

### OCR performance: PyTesseract vs PaddleOCR

I compared engines on the first 50 ICDAR2013 test images (CER / WER). Tesseract on ground-truth crops was the most accurate *given* boxes; among detectors that have to find text themselves, PaddleOCR’s full pipeline beat EasyOCR and was the one I shipped in the laptop app. Scene text still needed cropping, cleaning, and line grouping — raw whole-image Tesseract was not enough.

| Method | CER | WER |
|---|---|---|
| Tesseract `gt_bbox_crops` (best with GT boxes) | 0.1800 | 0.5103 |
| PaddleOCR simple (detect + recognize) | 0.2474 | **0.4487** |
| EasyOCR paragraph | 0.2845 | 0.6628 |
| Tesseract whole image / PSM 11 | much worse | much worse |

The wireless prototype later switched live OCR to **Google Cloud Vision** so the ESP32 stays a thin camera, not an on-device model host.

### A simple desktop UI

Tkinter three-screen flow (camera / captured / processing / translated), background-thread pipeline so the window stays responsive, file pick + save, and GPIO buttons mapped to the same left/right actions as the on-screen buttons.

### Flutter frontend for web and app

The same capture → confirm → result flow in Flutter, talking only to the local FastAPI backend. Web uses a native `<img>` MJPEG preview; Android parses the ESP32 multipart JPEG stream. Settings hold backend and camera URLs so the same build can run in Chrome or MuMu.

### ESP32 capture and talking to frontend / backend

Firmware exposes `GET /capture`, `GET /status` (button press counts), and `GET /stream`. The ESP32 never POSTs to the backend. Flutter polls `/status` and asks the backend to `POST /api/capture`; the backend then pulls the JPEG from the camera. Physical buttons only increment counters — the app decides what a press means.

### Soldering and prototyping a portable device

Perf-board wiring of a LiPo, TPS61023 boost, slide switch, and push button onto the Freenove camera kit so the capture side can run untethered from the Jetson.

---

## How to run

Google Cloud APIs (Translation for both MVPs; Vision for the wireless backend) use Application Default Credentials:

```powershell
gcloud auth application-default login
gcloud config set project handheld-ocr-translator
```

### Laptop MVP

Needs Python 3, OpenCV, Pillow, PaddleOCR / PaddlePaddle, and `google-cloud-translate`. On a Jetson, also `Jetson.GPIO` if you want the physical buttons.

```powershell
cd laptop_mvp
python src/ui/app.py
```

CLI on a single image (no UI):

```powershell
cd laptop_mvp/src
python main.py --image path/to/photo.jpg --target-lang zh-CN
```

### Wireless MVP

**Backend** (http://localhost:8000):

```powershell
cd wireless_mvp/backend
pip install -r requirements.txt
python -m app.api.server
```

**Frontend**

```powershell
cd wireless_mvp/frontend
flutter pub get
flutter run -d chrome
```

Android (for example MuMu at `127.0.0.1:7555`):

```powershell
flutter run -d 127.0.0.1:7555
```

In the app Settings:

- Backend URL: `http://localhost:8000` on web, or `http://10.0.2.2:8000` from an Android emulator
- ESP32 camera URL: the board’s Wi-Fi IP, e.g. `http://10.0.0.x` (not the emulator’s `10.0.2.15`)

**Firmware** (PlatformIO, env `freenove_esp32_s3_wroom`):

1. Create `wireless_mvp/firmware/esp32_camera/include/wifi_credentials.h` (gitignored) with your Wi-Fi SSID and password:

   ```c
   #define WIFI_SSID "your-ssid"
   #define WIFI_PASSWORD "your-password"
   ```

2. Flash and open the serial monitor; the board prints its IP after joining Wi-Fi.
3. Endpoints: `GET :80/capture`, `GET :80/status`, `GET :81/stream`.

---

## Video demo

_Add a link to the demo recording here (YouTube, Drive, or a file in this repo)._
