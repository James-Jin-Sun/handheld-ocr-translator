/**
 * Handheld OCR Translator - ESP32-S3 wireless camera source.
 *
 * Exposes a minimal HTTP server with:
 *   GET :80/capture -> one JPEG frame from the camera
 *   GET :80/status  -> {"status":"ok"} liveness check
 *   GET :81/stream  -> MJPEG live preview (multipart/x-mixed-replace)
 *
 * so wireless_mvp/src/api/server.py can pull an image on demand, as an
 * alternative to the existing laptop file-upload path, and the Flutter Web
 * frontend can show a live preview. The stream runs on its own port/task so
 * a long-lived streaming client can't block /capture or /status. Never
 * talks to Google APIs and never receives Google credentials -- it only
 * returns raw JPEG data to callers.
 *
 * Wi-Fi credentials are NOT stored in this file -- copy
 * include/wifi_credentials.h.example to include/wifi_credentials.h (which is
 * gitignored) and fill in your network's SSID/password before building.
 */
#include <Arduino.h>
#include <ESPmDNS.h>
#include <WebServer.h>
#include <WiFi.h>
#include <WiFiServer.h>
#include "board_config.h"
#include "esp_camera.h"
#include "esp_heap_caps.h"
#include "img_converters.h"
#include "wifi_credentials.h"

#ifndef WIFI_SSID
#error "Copy include/wifi_credentials.h.example to include/wifi_credentials.h and fill in your Wi-Fi credentials."
#endif

namespace {

// Reachable at http://esp32cam.local/capture once mDNS resolves, in addition
// to the IP address printed over Serial at boot.
constexpr char kMdnsHostname[] = "esp32cam";

constexpr uint16_t kStreamPort = 81;

WebServer server(80);
WiFiServer streamServer(kStreamPort);

// The sensor is mounted rotated 180 degrees relative to the enclosure, so
// rotate raw RGB565 frames before JPEG encoding to compensate. Two
// independent hardware tests (each cross-checked against a known-correct
// reference image) confirmed a full 180-degree rotation is needed, not 90:
// reversing the linear pixel order is a foolproof way to do that (no x/y
// transpose bookkeeping, no risk of swapping rows/columns incorrectly).
void rotateRgb565_180(const uint8_t *src, uint8_t *dst, size_t width, size_t height) {
  const uint16_t *src16 = reinterpret_cast<const uint16_t *>(src);
  uint16_t *dst16 = reinterpret_cast<uint16_t *>(dst);
  const size_t total = width * height;
  for (size_t i = 0; i < total; ++i) {
    dst16[i] = src16[total - 1 - i];
  }
}

// Grabs one frame, rotates it to match the enclosure's orientation, and
// converts to JPEG if the sensor didn't already deliver one (see the comment
// in handleCapture()). Caller must free() the buffer when needsFree is true
// and always call esp_camera_fb_return(fb).
bool grabJpegFrame(camera_fb_t **fb_out, uint8_t **jpg_buf, size_t *jpg_len, bool *needs_free) {
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) {
    return false;
  }
  *fb_out = fb;

  camera_fb_t rotated = *fb;
  uint8_t *rotated_buf = nullptr;
  if (fb->format != PIXFORMAT_JPEG) {
    rotated_buf = static_cast<uint8_t *>(heap_caps_malloc(fb->len, MALLOC_CAP_SPIRAM));
    if (rotated_buf != nullptr) {
      rotateRgb565_180(fb->buf, rotated_buf, fb->width, fb->height);
      rotated.buf = rotated_buf;
      // 180-degree rotation preserves width/height (no transpose).
    }
  }

  *jpg_buf = rotated.buf;
  *jpg_len = rotated.len;
  *needs_free = false;
  if (rotated.format != PIXFORMAT_JPEG) {
    bool ok = frame2jpg(&rotated, 80, jpg_buf, jpg_len);
    if (rotated_buf != nullptr) {
      free(rotated_buf);
    }
    if (!ok) {
      return false;
    }
    *needs_free = true;
  }
  return true;
}

void configureCamera() {
  camera_config_t config = {};
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 10000000;
  config.pixel_format = PIXFORMAT_JPEG;
  // LATEST (vs. WHEN_EMPTY) drops stale frames instead of blocking on VSYNC,
  // which otherwise floods the log with "EV-VSYNC-OVF" while idle.
  config.grab_mode = CAMERA_GRAB_LATEST;
  config.fb_location = CAMERA_FB_IN_PSRAM;
  // SVGA (800x600) balances OCR-usable detail against capture/transfer time
  // over Wi-Fi -- adjust here if text is too small/blurry to OCR reliably.
  config.frame_size = FRAMESIZE_SVGA;
  config.jpeg_quality = 10;  // lower number = higher quality/larger file
  config.fb_count = 1;

  esp_err_t err = esp_camera_init(&config);
  if (err == ESP_ERR_NOT_SUPPORTED) {
    config.pixel_format = PIXFORMAT_RGB565;
    err = esp_camera_init(&config);
  }
  if (err != ESP_OK) {
    Serial.printf("Camera init failed with error 0x%x\n", err);
    return;
  }

  sensor_t *s = esp_camera_sensor_get();
  if (s != nullptr) {
    s->set_brightness(s, 1);  // slightly increase brightness
    s->set_saturation(s, 0);  // reduce saturation
    s->set_ae_level(s, -3);   // exposure compensation, matches esp32_camera_test
    // Corrects this sensor's mirrored raw output; the remaining 90-degree
    // rotation (from how the sensor is mounted in the enclosure) is handled
    // per-frame in grabJpegFrame().
    s->set_hmirror(s, 1);
    s->set_vflip(s, 1);
  }
}

void handleCapture() {
  camera_fb_t *fb = nullptr;
  uint8_t *jpg_buf = nullptr;
  size_t jpg_len = 0;
  bool needs_free = false;
  // This sensor doesn't support hardware JPEG encoding (esp_camera_init logs
  // "JPEG format is not supported on this sensor" and silently falls back to
  // RGB565), so convert in software before sending -- same approach as the
  // reference Freenove CameraWebServer's capture_handler.
  if (!grabJpegFrame(&fb, &jpg_buf, &jpg_len, &needs_free)) {
    Serial.println(fb ? "JPEG conversion failed" : "Camera capture failed");
    if (fb) {
      esp_camera_fb_return(fb);
      server.send(500, "text/plain", "JPEG conversion failed");
    } else {
      server.send(503, "text/plain", "Camera capture failed");
    }
    return;
  }

  WiFiClient client = server.client();
  server.setContentLength(jpg_len);
  server.sendHeader("Access-Control-Allow-Origin", "*");
  server.send(200, "image/jpeg", "");
  client.write(jpg_buf, jpg_len);

  if (needs_free) {
    free(jpg_buf);
  }
  esp_camera_fb_return(fb);
}

void handleStatus() {
  server.sendHeader("Access-Control-Allow-Origin", "*");
  server.send(200, "application/json", "{\"status\":\"ok\"}");
}

// Serves MJPEG (multipart/x-mixed-replace) on its own port/task using a raw
// WiFiServer instead of the WebServer library, so a browser's <img> tag can
// hold this connection open indefinitely without blocking /capture or
// /status on port 80.
void streamTask(void *) {
  streamServer.begin();
  for (;;) {
    WiFiClient client = streamServer.available();
    if (!client) {
      vTaskDelay(pdMS_TO_TICKS(10));
      continue;
    }

    unsigned long waitStart = millis();
    while (client.connected() && !client.available() && millis() - waitStart < 1000) {
      delay(1);
    }
    while (client.available()) {
      client.readStringUntil('\n');  // discard the request line/headers, only one route exists
    }

    client.print(
        "HTTP/1.1 200 OK\r\n"
        "Access-Control-Allow-Origin: *\r\n"
        "Content-Type: multipart/x-mixed-replace;boundary=frame\r\n\r\n");

    while (client.connected()) {
      camera_fb_t *fb = nullptr;
      uint8_t *jpg_buf = nullptr;
      size_t jpg_len = 0;
      bool needs_free = false;
      if (!grabJpegFrame(&fb, &jpg_buf, &jpg_len, &needs_free)) {
        if (fb) {
          esp_camera_fb_return(fb);
        }
        break;
      }

      client.printf("--frame\r\nContent-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n", jpg_len);
      client.write(jpg_buf, jpg_len);
      client.print("\r\n");

      if (needs_free) {
        free(jpg_buf);
      }
      esp_camera_fb_return(fb);

      if (!client.connected()) {
        break;
      }
      vTaskDelay(pdMS_TO_TICKS(30));  // throttle to ~30fps max
    }
    client.stop();
  }
}

}  // namespace

void setup() {
  Serial.begin(115200);
  Serial.setDebugOutput(true);
  Serial.println();

  configureCamera();

  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("Connecting to Wi-Fi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println();
  Serial.print("Wi-Fi connected, IP address: ");
  Serial.println(WiFi.localIP());

  if (MDNS.begin(kMdnsHostname)) {
    Serial.printf("mDNS responder started: http://%s.local/capture\n", kMdnsHostname);
  }

  server.on("/capture", HTTP_GET, handleCapture);
  server.on("/status", HTTP_GET, handleStatus);
  server.begin();
  Serial.println("HTTP server started. Endpoints: /capture, /status");

  xTaskCreatePinnedToCore(streamTask, "mjpeg_stream", 8192, nullptr, 1, nullptr, 1);
  Serial.printf("MJPEG stream started on port %u. Endpoint: /stream\n", kStreamPort);
}

void loop() {
  server.handleClient();
}
