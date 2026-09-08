/// Data models matching the JSON shapes returned by the FastAPI backend
/// (see wireless_mvp/src/api/server.py and src/main.py's manifest output).
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
