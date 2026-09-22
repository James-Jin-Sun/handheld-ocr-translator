/// Data models matching the JSON shapes returned by the FastAPI backend
/// (see wireless_mvp/backend/app/api/server.py and app/main.py's manifest output).
library;

class ProcessResult {
  ProcessResult({
    required this.jobId,
    required this.textDetected,
    required this.ocrRuntimeSeconds,
    this.translatedImageUrl,
    this.manifestUrl,
  });

  final String jobId;
  final bool textDetected;
  final double ocrRuntimeSeconds;
  final String? translatedImageUrl;
  final String? manifestUrl;

  factory ProcessResult.fromJson(Map<String, dynamic> json) {
    return ProcessResult(
      jobId: json['job_id'] as String,
      textDetected: json['text_detected'] as bool,
      ocrRuntimeSeconds: (json['ocr_runtime_seconds'] as num).toDouble(),
      translatedImageUrl: json['translated_image_url'] as String?,
      manifestUrl: json['manifest_url'] as String?,
    );
  }
}

class TranslatedBlock {
  TranslatedBlock({required this.text, required this.translatedText});

  final String text;
  final String translatedText;

  factory TranslatedBlock.fromJson(Map<String, dynamic> json) {
    return TranslatedBlock(
      text: json['text'] as String? ?? '',
      translatedText: json['translated_text'] as String? ?? '',
    );
  }
}

/// `left_button_count`/`right_button_count` from the ESP32's `GET /status`
/// (see wireless_mvp/firmware/esp32_camera/src/main.cpp), incremented by
/// the physical GPIO21 (left) / GPIO41 (right) push buttons.
class ButtonPressCounts {
  ButtonPressCounts({required this.left, required this.right});

  final int left;
  final int right;
}

class Manifest {
  Manifest({required this.ocrEngine, required this.targetLanguage, required this.blocks});

  final String ocrEngine;
  final String targetLanguage;
  final List<TranslatedBlock> blocks;

  factory Manifest.fromJson(Map<String, dynamic> json) {
    final blocksJson = json['blocks'] as List<dynamic>? ?? const [];
    return Manifest(
      ocrEngine: json['ocr_engine'] as String? ?? '',
      targetLanguage: json['target_language'] as String? ?? '',
      blocks: blocksJson.map((b) => TranslatedBlock.fromJson(b as Map<String, dynamic>)).toList(),
    );
  }
}
