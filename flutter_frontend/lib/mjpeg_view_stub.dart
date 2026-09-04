/// Non-web fallback for [MjpegView]. The real implementation
/// (mjpeg_view_web.dart) needs dart:html/dart:ui_web, which don't exist
/// outside a browser -- this stub keeps `flutter test` (which runs on the
/// Dart VM) able to compile main.dart.
library;

import 'package:flutter/material.dart';

class MjpegView extends StatelessWidget {
  const MjpegView({super.key, required this.streamUrl});

  final String streamUrl;

  @override
  Widget build(BuildContext context) {
    return const Center(
      child: Text(
        'Live preview is only available in the web build.',
        textAlign: TextAlign.center,
        style: TextStyle(color: Colors.white70),
      ),
    );
  }
}
