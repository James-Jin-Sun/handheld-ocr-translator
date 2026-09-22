/// Thin HTTP client for the existing local FastAPI backend
/// (wireless_mvp/backend/app/api/server.py). This is the *only* network boundary --
/// the Flutter app never talks to Google Cloud or holds any credentials.
library;

import 'dart:convert';
import 'dart:typed_data';

import 'package:http/http.dart' as http;

import 'models.dart';

class OcrApiException implements Exception {
  OcrApiException(this.message);

  final String message;

  @override
  String toString() => message;
}

class OcrApiClient {
  OcrApiClient({required this.baseUrl});

  final String baseUrl;

  Future<bool> checkHealth() async {
    try {
      final response = await http.get(Uri.parse('$baseUrl/api/health'));
      return response.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

  Future<ProcessResult> processImage({
    required Uint8List imageBytes,
    required String filename,
    String? targetLang,
    String? sourceLang,
    String? projectId,
    List<String>? ocrLanguageHints,
  }) async {
    final request = http.MultipartRequest('POST', Uri.parse('$baseUrl/api/process'))
      ..files.add(http.MultipartFile.fromBytes('image', imageBytes, filename: filename));

    if (targetLang != null && targetLang.trim().isNotEmpty) {
      request.fields['target_lang'] = targetLang.trim();
    }
    if (sourceLang != null && sourceLang.trim().isNotEmpty) {
      request.fields['source_lang'] = sourceLang.trim();
    }
    if (projectId != null && projectId.trim().isNotEmpty) {
      request.fields['project_id'] = projectId.trim();
    }
    if (ocrLanguageHints != null && ocrLanguageHints.isNotEmpty) {
      request.fields['ocr_language_hints'] = ocrLanguageHints.join(',');
    }

    final response = await http.Response.fromStream(await request.send());
    if (response.statusCode != 200) {
      throw OcrApiException(_extractDetail(response.body) ?? 'Request failed (HTTP ${response.statusCode}).');
    }
    return ProcessResult.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
  }

  /// Asks the backend to pull one JPEG from the ESP32-S3 camera's own
  /// `GET /capture` endpoint and run it through the same pipeline as
  /// [processImage]. The Flutter app never talks to the ESP32 directly.
  Future<ProcessResult> captureFromEsp32({
    required String esp32Url,
    String? targetLang,
    String? sourceLang,
    String? projectId,
    List<String>? ocrLanguageHints,
  }) async {
    final request = http.MultipartRequest('POST', Uri.parse('$baseUrl/api/capture'))
      ..fields['esp32_url'] = esp32Url.trim();

    if (targetLang != null && targetLang.trim().isNotEmpty) {
      request.fields['target_lang'] = targetLang.trim();
    }
    if (sourceLang != null && sourceLang.trim().isNotEmpty) {
      request.fields['source_lang'] = sourceLang.trim();
    }
    if (projectId != null && projectId.trim().isNotEmpty) {
      request.fields['project_id'] = projectId.trim();
    }
    if (ocrLanguageHints != null && ocrLanguageHints.isNotEmpty) {
      request.fields['ocr_language_hints'] = ocrLanguageHints.join(',');
    }

    final response = await http.Response.fromStream(await request.send());
    if (response.statusCode != 200) {
      throw OcrApiException(_extractDetail(response.body) ?? 'Request failed (HTTP ${response.statusCode}).');
    }
    return ProcessResult.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
  }

  Future<Uint8List> fetchResultImage(String relativeUrl) async {
    final response = await http.get(Uri.parse('$baseUrl$relativeUrl'));
    if (response.statusCode != 200) {
      throw OcrApiException('Could not fetch translated image (HTTP ${response.statusCode}).');
    }
    return response.bodyBytes;
  }

  Future<Manifest> fetchManifest(String relativeUrl) async {
    final response = await http.get(Uri.parse('$baseUrl$relativeUrl'));
    if (response.statusCode != 200) {
      throw OcrApiException('Could not fetch manifest (HTTP ${response.statusCode}).');
    }
    return Manifest.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
  }

  /// Polls the ESP32's own `GET /status` directly (bypassing the backend --
  /// the only direct Flutter<->ESP32 traffic in this app) purely to read
  /// `left_button_count`/`right_button_count`, incremented by the physical
  /// GPIO21 (left) / GPIO41 (right) push buttons. No image bytes, OCR
  /// results, or credentials ever cross this call. Returns null on any
  /// network/parse failure (treated as "no change").
  Future<ButtonPressCounts?> fetchEsp32ButtonPressCounts(String esp32Url) async {
    final trimmed = esp32Url.trim();
    if (trimmed.isEmpty) return null;
    try {
      final response = await http
          .get(Uri.parse('${trimmed.replaceFirst(RegExp(r"/+$"), "")}/status'))
          .timeout(const Duration(seconds: 3));
      if (response.statusCode != 200) return null;
      final data = jsonDecode(response.body);
      if (data is! Map) return null;
      final left = data['left_button_count'];
      final right = data['right_button_count'];
      if (left is! int || right is! int) return null;
      return ButtonPressCounts(left: left, right: right);
    } catch (_) {
      return null;
    }
  }

  String? _extractDetail(String body) {
    try {
      final data = jsonDecode(body);
      if (data is Map && data['detail'] != null) return data['detail'].toString();
    } catch (_) {
      // Response body wasn't JSON -- fall through and use the generic message.
    }
    return null;
  }
}
