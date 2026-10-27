import 'dart:async';

enum MessageRole { user, assistant }

class ChatMessage {
  const ChatMessage({
    required this.role,
    required this.text,
    required this.languageCode,
  });

  final MessageRole role;
  final String text;
  final String languageCode;
}

abstract interface class AiProvider {
  Future<ChatMessage> reply(String prompt, {required String languageCode});
}

class MockAiProvider implements AiProvider {
  const MockAiProvider();

  @override
  Future<ChatMessage> reply(
    String prompt, {
    required String languageCode,
  }) async {
    return ChatMessage(
      role: MessageRole.assistant,
      text: languageCode == 'ar'
          ? 'هذا رد تجريبي من جارفس.'
          : 'This is a mock JARVIS reply.',
      languageCode: languageCode,
    );
  }
}

abstract interface class SpeechEngine {
  bool get isSpeaking;
  Future<void> start(String text);
  Future<void> stop();
  Future<void> cancel();
}

class MockSpeechEngine implements SpeechEngine {
  MockSpeechEngine({this.duration = const Duration(seconds: 2)});

  final Duration duration;
  Timer? _timer;
  Completer<void>? _completion;

  @override
  bool get isSpeaking => _timer != null;

  @override
  Future<void> start(String text) async {
    if (text.trim().isEmpty) {
      throw ArgumentError.value(text, 'text', 'Speech text cannot be empty.');
    }
    if (isSpeaking) {
      throw StateError('Speech is already active.');
    }

    final completion = Completer<void>();
    _completion = completion;
    _timer = Timer(duration, _finish);
    await completion.future;
  }

  @override
  Future<void> stop() async => _finish();

  @override
  Future<void> cancel() async => _finish();

  void _finish() {
    _timer?.cancel();
    _timer = null;
    final completion = _completion;
    _completion = null;
    if (completion != null && !completion.isCompleted) {
      completion.complete();
    }
  }
}

class CapabilityResult {
  const CapabilityResult.unsupported()
    : supported = false,
      message = 'This capability is not implemented in the prototype.';

  final bool supported;
  final String message;
}

abstract interface class SystemCapabilities {
  Future<CapabilityResult> invoke(String capability);
}

class UnsupportedSystemCapabilities implements SystemCapabilities {
  const UnsupportedSystemCapabilities();

  @override
  Future<CapabilityResult> invoke(String capability) async {
    return const CapabilityResult.unsupported();
  }
}
