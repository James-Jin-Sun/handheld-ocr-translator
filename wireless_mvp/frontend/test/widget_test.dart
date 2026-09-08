import 'package:flutter_test/flutter_test.dart';

import 'package:handheld_ocr_translator_web/main.dart';

void main() {
  testWidgets('Shows the initial camera / select-image screen', (WidgetTester tester) async {
    await tester.pumpWidget(const OcrTranslatorApp());

    expect(find.text('Select Image'), findsOneWidget);
    expect(find.text('Capture Image'), findsOneWidget);
    expect(find.textContaining("Press 'Capture Image' when ready"), findsOneWidget);
  });
}
