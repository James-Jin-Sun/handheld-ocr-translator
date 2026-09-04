/// Flutter Web frontend for the Handheld OCR Translator.
///
/// Mirrors the Tkinter desktop UI's (wireless_mvp/src/ui/app.py) three-screen
/// flow -- image source -> captured/selected -> translated -- including its
/// dark theme, single large image area, status bar, and bottom-left/right
/// action buttons. Calls the existing local FastAPI backend
/// (wireless_mvp/src/api/server.py) which in turn reuses the existing
/// OCR -> translate -> overlay pipeline. This app only ever talks to that
/// local backend -- it never calls Google Cloud APIs or holds credentials.
///
/// "Frame 1" has no browser-native live camera feed (unlike the desktop
/// app's webcam view). Instead, "Capture Image" asks the backend to pull one
/// JPEG from a wireless ESP32-S3 camera (wireless_mvp/firmware/esp32_camera)
/// and run it through the pipeline directly; "Select Image" keeps the
/// original laptop file-upload flow with its captured/confirm/retake step.
library;

import 'dart:typed_data';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';

import 'api_client.dart';
import 'mjpeg_view_stub.dart' if (dart.library.html) 'mjpeg_view_web.dart';
import 'models.dart';

const String kDefaultBackendUrl = 'http://localhost:8000';
const String kDefaultTargetLang = 'zh-CN';
const String kNoCameraStatusText =
    "No local camera. Set an ESP32-S3 camera URL in Settings to see a live view, or use 'Select Image' to upload a file.";
const String kLiveCameraStatusText =
    "Live view from the ESP32-S3 camera. Press 'Capture Image' when ready.";

/// Live preview URL for the ESP32 firmware's MJPEG endpoint (a separate
/// task/port from /capture and /status -- see wireless_mvp/firmware/esp32_camera),
/// or null if no ESP32 camera URL is configured / it doesn't parse as a URL.
String? _esp32StreamUrl(String esp32Url) {
  if (esp32Url.isEmpty) return null;
  final uri = Uri.tryParse(esp32Url);
  if (uri == null || uri.host.isEmpty) return null;
  return Uri(scheme: uri.scheme.isEmpty ? 'http' : uri.scheme, host: uri.host, port: 81, path: '/stream').toString();
}

void main() {
  runApp(const OcrTranslatorApp());
}

class OcrTranslatorApp extends StatelessWidget {
  const OcrTranslatorApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Handheld OCR Translator',
      theme: ThemeData(
        colorSchemeSeed: Colors.indigo,
        brightness: Brightness.dark,
        scaffoldBackgroundColor: const Color(0xFF1E1E1E),
        useMaterial3: true,
      ),
      home: const TranslatorHomePage(),
    );
  }
}

/// Mirrors the desktop app's STATE_CAMERA / STATE_CAPTURED / STATE_PROCESSING
/// / STATE_TRANSLATED state machine.
enum _Screen { camera, captured, processing, translated }

class TranslatorHomePage extends StatefulWidget {
  const TranslatorHomePage({super.key});

  @override
  State<TranslatorHomePage> createState() => _TranslatorHomePageState();
}

class _TranslatorHomePageState extends State<TranslatorHomePage> {
  static const _imageAreaSize = Size(820, 560);

  final _backendUrlController = TextEditingController(text: kDefaultBackendUrl);
  final _esp32UrlController = TextEditingController();
  final _targetLangController = TextEditingController(text: kDefaultTargetLang);
  final _sourceLangController = TextEditingController();
  final _ocrHintsController = TextEditingController();

  _Screen _screen = _Screen.camera;
  String _statusMessage = kNoCameraStatusText;
  bool _statusWarning = true;

  Uint8List? _pickedBytes;
  String? _pickedFilename;

  Uint8List? _resultImageBytes;
  Manifest? _manifest;

  OcrApiClient get _client => OcrApiClient(baseUrl: _backendUrlController.text.trim());

  @override
  void dispose() {
    _backendUrlController.dispose();
    _esp32UrlController.dispose();
    _targetLangController.dispose();
    _sourceLangController.dispose();
    _ocrHintsController.dispose();
    super.dispose();
  }

  // ---- Frame 1: image source (ESP32-S3 wireless capture, or laptop file) ----

  Future<void> _onCaptureImageClicked() async {
    final esp32Url = _esp32UrlController.text.trim();
    if (esp32Url.isEmpty) {
      setState(() {
        _statusMessage = "No ESP32 camera URL set -- add one in Settings, or use 'Select Image' instead.";
        _statusWarning = true;
      });
      return;
    }

    setState(() {
      _pickedBytes = null;
      _pickedFilename = null;
    });

    await _runPipelineRequest(
      () => _client.captureFromEsp32(
        esp32Url: esp32Url,
        targetLang: _targetLangController.text,
        sourceLang: _sourceLangController.text,
        ocrLanguageHints: _parseHints(),
      ),
      fallbackScreen: _Screen.camera,
      fallbackStatusMessage: kNoCameraStatusText,
    );
  }

  Future<void> _onSelectImageClicked() async {
    final result = await FilePicker.platform.pickFiles(
      type: FileType.custom,
      allowedExtensions: const ['jpg', 'jpeg', 'png'],
      withData: true,
    );
    if (result == null || result.files.isEmpty) return;

    final file = result.files.single;
    if (file.bytes == null) {
      setState(() {
        _statusMessage = 'Could not read the selected file.';
        _statusWarning = true;
      });
      return;
    }

    setState(() {
      _pickedBytes = file.bytes;
      _pickedFilename = file.name;
      _resultImageBytes = null;
      _manifest = null;
      _screen = _Screen.captured;
      _statusMessage = 'Image selected. Confirm to translate, or retake.';
      _statusWarning = false;
    });
  }

  // ---- Frame 2: image captured/selected ----

  void _onRetakeClicked() {
    setState(() {
      _screen = _Screen.camera;
      _pickedBytes = null;
      _pickedFilename = null;
      _applyCameraScreenStatus();
    });
  }

  void _applyCameraScreenStatus() {
    final hasLiveView = _esp32StreamUrl(_esp32UrlController.text.trim()) != null;
    _statusMessage = hasLiveView ? kLiveCameraStatusText : kNoCameraStatusText;
    _statusWarning = !hasLiveView;
  }

  List<String>? _parseHints() {
    final raw = _ocrHintsController.text.trim();
    if (raw.isEmpty) return null;
    return raw.split(',').map((hint) => hint.trim()).where((hint) => hint.isNotEmpty).toList();
  }

  Future<void> _showMessageDialog(String message) {
    return showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Handheld OCR Translator'),
        content: Text(message),
        actions: [TextButton(onPressed: () => Navigator.of(context).pop(), child: const Text('OK'))],
      ),
    );
  }

  Future<void> _onConfirmClicked() async {
    final bytes = _pickedBytes;
    final filename = _pickedFilename;
    if (bytes == null || filename == null) return;

    await _runPipelineRequest(
      () => _client.processImage(
        imageBytes: bytes,
        filename: filename,
        targetLang: _targetLangController.text,
        sourceLang: _sourceLangController.text,
        ocrLanguageHints: _parseHints(),
      ),
      fallbackScreen: _Screen.captured,
      fallbackStatusMessage: 'Image selected. Confirm to translate, or retake.',
    );
  }

  /// Shared by [_onConfirmClicked] (laptop upload) and [_onCaptureImageClicked]
  /// (ESP32 wireless capture) -- both just supply a different backend call and
  /// a different screen/message to fall back to on "no text"/error.
  Future<void> _runPipelineRequest(
    Future<ProcessResult> Function() request, {
    required _Screen fallbackScreen,
    required String fallbackStatusMessage,
  }) async {
    setState(() {
      _screen = _Screen.processing;
      _statusMessage = 'Processing: OCR -> Translation -> Overlay... this can take up to a minute.';
      _statusWarning = false;
    });

    try {
      final result = await request();

      if (!result.textDetected) {
        if (mounted) {
          await _showMessageDialog(
            'No text was detected in the image.\nOCR took ${result.ocrRuntimeSeconds.toStringAsFixed(2)}s.',
          );
        }
        if (!mounted) return;
        setState(() {
          _screen = fallbackScreen;
          _statusMessage = fallbackStatusMessage;
          _statusWarning = false;
        });
        return;
      }

      final imageBytes = await _client.fetchResultImage(result.translatedImageUrl!);
      final manifest = await _client.fetchManifest(result.manifestUrl!);

      if (!mounted) return;
      setState(() {
        _resultImageBytes = imageBytes;
        _manifest = manifest;
        _screen = _Screen.translated;
        _statusMessage = 'Translation complete. (OCR: ${result.ocrRuntimeSeconds.toStringAsFixed(2)}s)';
        _statusWarning = false;
      });
    } catch (exc) {
      final message = exc is OcrApiException ? exc.message : 'Could not reach the backend: $exc';
      if (mounted) await _showMessageDialog('Translation pipeline failed:\n$message');
      if (!mounted) return;
      setState(() {
        _screen = fallbackScreen;
        _statusMessage = fallbackStatusMessage;
        _statusWarning = false;
      });
    }
  }

  // ---- Frame 3: translation completed ----

  Future<void> _onSaveClicked() async {
    final bytes = _resultImageBytes;
    if (bytes == null) return;

    final suggestedName = _pickedFilename == null ? 'translated.jpg' : 'translated_${_pickedFilename!}';

    try {
      await FilePicker.platform.saveFile(
        dialogTitle: 'Save translated image',
        fileName: suggestedName,
        bytes: bytes,
        type: FileType.custom,
        allowedExtensions: const ['jpg', 'jpeg', 'png'],
      );
    } catch (exc) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Could not save image: $exc')));
    }
  }

  void _onRestartClicked() {
    setState(() {
      _screen = _Screen.camera;
      _pickedBytes = null;
      _pickedFilename = null;
      _resultImageBytes = null;
      _manifest = null;
      _applyCameraScreenStatus();
    });
  }

  Future<void> _openSettings() async {
    await showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Settings'),
        content: SizedBox(
          width: 360,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              TextField(
                controller: _backendUrlController,
                decoration: const InputDecoration(labelText: 'Backend URL', border: OutlineInputBorder()),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _esp32UrlController,
                decoration: const InputDecoration(
                  labelText: 'ESP32 camera URL (e.g. http://192.168.1.42)',
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _targetLangController,
                decoration:
                    const InputDecoration(labelText: 'Target language (e.g. zh-CN)', border: OutlineInputBorder()),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _sourceLangController,
                decoration: const InputDecoration(
                  labelText: 'Source language (optional, auto-detect)',
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _ocrHintsController,
                decoration: const InputDecoration(
                  labelText: 'OCR language hints (optional, e.g. en,fr)',
                  border: OutlineInputBorder(),
                ),
              ),
            ],
          ),
        ),
        actions: [TextButton(onPressed: () => Navigator.of(context).pop(), child: const Text('Done'))],
      ),
    );
    if (_screen == _Screen.camera) {
      setState(_applyCameraScreenStatus);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Handheld OCR Translator'),
        actions: [
          IconButton(onPressed: _openSettings, icon: const Icon(Icons.settings_outlined), tooltip: 'Settings'),
        ],
      ),
      body: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(16),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 900),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                _buildImageArea(),
                const SizedBox(height: 8),
                _buildStatusBar(),
                const SizedBox(height: 12),
                _buildControls(),
                if (_screen == _Screen.translated && _manifest != null && _manifest!.blocks.isNotEmpty)
                  _buildDetectedTextPanel(_manifest!.blocks),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildImageArea() {
    Widget content;
    switch (_screen) {
      case _Screen.camera:
        final streamUrl = _esp32StreamUrl(_esp32UrlController.text.trim());
        content = streamUrl == null
            ? const Text(
                'LIVE CAMERA VIEW\n(no camera detected)',
                textAlign: TextAlign.center,
                style: TextStyle(color: Colors.white, fontSize: 20),
              )
            : MjpegView(streamUrl: streamUrl);
        break;
      case _Screen.captured:
      case _Screen.processing:
        content = _pickedBytes == null ? const SizedBox.shrink() : Image.memory(_pickedBytes!, fit: BoxFit.contain);
        break;
      case _Screen.translated:
        content =
            _resultImageBytes == null ? const SizedBox.shrink() : Image.memory(_resultImageBytes!, fit: BoxFit.contain);
        break;
    }

    return Container(
      width: _imageAreaSize.width,
      height: _imageAreaSize.height,
      decoration: BoxDecoration(color: Colors.black, borderRadius: BorderRadius.circular(4)),
      alignment: Alignment.center,
      child: content,
    );
  }

  Widget _buildStatusBar() {
    return Align(
      alignment: Alignment.centerLeft,
      child: Text(
        _statusMessage,
        style: TextStyle(color: _statusWarning ? const Color(0xFFF08080) : const Color(0xFFCCCCCC), fontSize: 14),
      ),
    );
  }

  Widget _buildControls() {
    switch (_screen) {
      case _Screen.camera:
        return Row(
          children: [
            Tooltip(
              message: 'Pull a photo from the ESP32-S3 camera over Wi-Fi (configure its URL in Settings).',
              child: FilledButton(onPressed: _onCaptureImageClicked, child: const Text('Capture Image')),
            ),
            const Spacer(),
            FilledButton(onPressed: _onSelectImageClicked, child: const Text('Select Image')),
          ],
        );
      case _Screen.captured:
        return Row(
          children: [
            FilledButton(onPressed: _onConfirmClicked, child: const Text('Confirm')),
            const Spacer(),
            FilledButton(onPressed: _onRetakeClicked, child: const Text('Close / Retake')),
          ],
        );
      case _Screen.processing:
        return const Row(
          children: [
            SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2)),
            SizedBox(width: 12),
            Text('Processing...', style: TextStyle(color: Color(0xFFF5C518))),
          ],
        );
      case _Screen.translated:
        return Row(
          children: [
            FilledButton(onPressed: _onSaveClicked, child: const Text('Save')),
            const Spacer(),
            FilledButton(onPressed: _onRestartClicked, child: const Text('Close / Restart')),
          ],
        );
    }
  }

  Widget _buildDetectedTextPanel(List<TranslatedBlock> blocks) {
    return Padding(
      padding: const EdgeInsets.only(top: 16),
      child: ExpansionTile(
        title: Text('Detected text (${_manifest!.ocrEngine})'),
        children: [
          Table(
            border: TableBorder.all(color: Theme.of(context).dividerColor),
            columnWidths: const {0: FlexColumnWidth(), 1: FlexColumnWidth()},
            children: [
              TableRow(
                decoration: BoxDecoration(color: Theme.of(context).colorScheme.surfaceContainerHighest),
                children: const [
                  Padding(
                    padding: EdgeInsets.all(8),
                    child: Text('Detected text', style: TextStyle(fontWeight: FontWeight.bold)),
                  ),
                  Padding(
                    padding: EdgeInsets.all(8),
                    child: Text('Translated text', style: TextStyle(fontWeight: FontWeight.bold)),
                  ),
                ],
              ),
              for (final block in blocks)
                TableRow(
                  children: [
                    Padding(padding: const EdgeInsets.all(8), child: Text(block.text)),
                    Padding(padding: const EdgeInsets.all(8), child: Text(block.translatedText)),
                  ],
                ),
            ],
          ),
        ],
      ),
    );
  }
}
