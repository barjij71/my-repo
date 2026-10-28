import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:jarvis_core/jarvis_core.dart';
import 'package:jarvis_poc/main.dart';

void main() {
  testWidgets('mock chat sends a message and renders a local reply', (
    tester,
  ) async {
    await tester.pumpWidget(const JarvisPocApp());
    expect(find.byKey(const ValueKey('jarvis-avatar')), findsOneWidget);

    await tester.enterText(
      find.byKey(const ValueKey('chat-input')),
      'Hello JARVIS',
    );
    await tester.tap(find.byKey(const ValueKey('send-button')));
    await tester.pump(const Duration(milliseconds: 300));

    expect(find.text('Hello JARVIS'), findsOneWidget);
    expect(find.text('This is a mock JARVIS reply.'), findsOneWidget);
  });

  testWidgets('Arabic mode switches direction and keeps mock reply RTL', (
    tester,
  ) async {
    await tester.pumpWidget(const JarvisPocApp());

    await tester.tap(find.text('العربية'));
    await tester.pump(const Duration(milliseconds: 300));
    expect(
      Directionality.of(
        tester.element(find.byKey(const ValueKey('chat-input'))),
      ),
      TextDirection.rtl,
    );

    await tester.enterText(
      find.byKey(const ValueKey('chat-input')),
      'مرحبا بجارفيس',
    );
    await tester.tap(find.byKey(const ValueKey('send-button')));
    await tester.pump(const Duration(milliseconds: 300));

    final reply = find.text('هذا رد تجريبي من جارفس.');
    expect(reply, findsOneWidget);
    expect(tester.widget<Text>(reply).textDirection, TextDirection.rtl);
  });

  testWidgets(
    'device capability is reported unsupported without native access',
    (tester) async {
      await tester.pumpWidget(const JarvisPocApp());

      await tester.tap(find.byKey(const ValueKey('device-control-button')));
      await tester.pump(const Duration(milliseconds: 300));

      expect(
        find.text('This capability is not implemented in the prototype.'),
        findsOneWidget,
      );
    },
  );

  test('mock speech rejects overlap and can be cancelled', () async {
    final engine = MockSpeechEngine(duration: const Duration(seconds: 30));
    final firstPlayback = engine.start('first');

    expect(engine.isSpeaking, isTrue);
    await expectLater(engine.start('second'), throwsA(isA<StateError>()));

    await engine.cancel();
    await firstPlayback;
    expect(engine.isSpeaking, isFalse);
  });
}
