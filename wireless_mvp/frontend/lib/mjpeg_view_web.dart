/// Live MJPEG preview from the ESP32-S3 camera's `/stream` endpoint
/// (wireless_mvp/firmware/esp32_camera), rendered as a plain HTML <img>
/// element -- browsers natively decode multipart/x-mixed-replace inside
/// <img>, so no manual frame polling/decoding is needed here.
library;

// This file is only ever compiled for web builds (see the conditional
// import in main.dart), so dart:html is intentional here, not a mistake.
// ignore: avoid_web_libraries_in_flutter
import 'dart:html' as html;
import 'dart:ui_web' as ui_web;

import 'package:flutter/material.dart';

class MjpegView extends StatefulWidget {
  const MjpegView({super.key, required this.streamUrl});

  final String streamUrl;

  @override
  State<MjpegView> createState() => _MjpegViewState();
}

class _MjpegViewState extends State<MjpegView> {
  late final String _viewType;

  @override
  void initState() {
    super.initState();
    // Unique per State instance so re-mounting (e.g. leaving/returning to
    // this screen) doesn't collide with a previously registered factory.
    _viewType = 'esp32-mjpeg-view-${identityHashCode(this)}';
    ui_web.platformViewRegistry.registerViewFactory(_viewType, (int viewId) {
      return html.ImageElement()
        ..src = widget.streamUrl
        ..style.width = '100%'
        ..style.height = '100%'
        ..style.objectFit = 'contain';
    });
  }

  @override
  Widget build(BuildContext context) {
    return HtmlElementView(viewType: _viewType);
  }
}
