import 'dart:async';

import 'package:flutter/material.dart';
import 'package:jarvis_core/jarvis_core.dart';

import 'jarvis_avatar.dart';

void main() {
  runApp(const JarvisPocApp());
}

class JarvisPocApp extends StatelessWidget {
  const JarvisPocApp({
    super.key,
    this.aiProvider = const MockAiProvider(),
    this.speechEngine,
    this.systemCapabilities = const UnsupportedSystemCapabilities(),
  });

  final AiProvider aiProvider;
  final SpeechEngine? speechEngine;
  final SystemCapabilities systemCapabilities;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'JARVIS prototype',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: Colors.teal),
        scaffoldBackgroundColor: const Color(0xFF06111B),
        appBarTheme: const AppBarTheme(
          backgroundColor: Color(0xFF071A27),
          foregroundColor: Color(0xFFE3FAFF),
        ),
      ),
      home: ChatScreen(
        aiProvider: aiProvider,
        speechEngine: speechEngine ?? MockSpeechEngine(),
        systemCapabilities: systemCapabilities,
      ),
    );
  }
}

class ChatScreen extends StatefulWidget {
  const ChatScreen({
    super.key,
    required this.aiProvider,
    required this.speechEngine,
    required this.systemCapabilities,
  });

  final AiProvider aiProvider;
  final SpeechEngine speechEngine;
  final SystemCapabilities systemCapabilities;

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  final _input = TextEditingController();
  final _messages = <ChatMessage>[];
  String _languageCode = 'en';
  bool _waitingForReply = false;
  bool _speaking = false;
  String? _capabilityNotice;

  @override
  void dispose() {
    _input.dispose();
    unawaited(widget.speechEngine.cancel());
    super.dispose();
  }

  Future<void> _sendMessage() async {
    final prompt = _input.text.trim();
    if (prompt.isEmpty || _waitingForReply) return;

    setState(() {
      _messages.add(
        ChatMessage(
          role: MessageRole.user,
          text: prompt,
          languageCode: _languageCode,
        ),
      );
      _waitingForReply = true;
      _capabilityNotice = null;
      _input.clear();
    });

    try {
      final reply = await widget.aiProvider.reply(
        prompt,
        languageCode: _languageCode,
      );
      if (!mounted) return;
      setState(() => _messages.add(reply));
    } finally {
      if (mounted) setState(() => _waitingForReply = false);
    }
  }

  Future<void> _simulateSpeech() async {
    final lastReply = _messages.lastWhere(
      (message) => message.role == MessageRole.assistant,
      orElse: () => const ChatMessage(
        role: MessageRole.assistant,
        text: '',
        languageCode: 'en',
      ),
    );
    if (lastReply.text.isEmpty || _speaking) return;

    setState(() => _speaking = true);
    try {
      await widget.speechEngine.start(lastReply.text);
    } finally {
      if (mounted) setState(() => _speaking = false);
    }
  }

  Future<void> _stopSpeech() async {
    await widget.speechEngine.stop();
    if (mounted) setState(() => _speaking = false);
  }

  Future<void> _showUnsupportedCapability() async {
    final result = await widget.systemCapabilities.invoke('device_control');
    if (mounted) setState(() => _capabilityNotice = result.message);
  }

  @override
  Widget build(BuildContext context) {
    final direction = _languageCode == 'ar'
        ? TextDirection.rtl
        : TextDirection.ltr;

    return Directionality(
      textDirection: direction,
      child: Scaffold(
        appBar: AppBar(title: const Text('JARVIS · technology prototype')),
        body: SafeArea(
          child: Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 760),
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  children: [
                    const Card(
                      child: Padding(
                        padding: EdgeInsets.all(12),
                        child: Text(
                          'Proof of concept only: AI and speech are mocked. '
                          'No microphone, network provider, or device controls are active.',
                        ),
                      ),
                    ),
                    const SizedBox(height: 10),
                    const JarvisAvatar(height: 220),
                    const SizedBox(height: 10),
                    SegmentedButton<String>(
                      key: const ValueKey('language-selector'),
                      segments: const [
                        ButtonSegment(value: 'en', label: Text('English')),
                        ButtonSegment(value: 'ar', label: Text('العربية')),
                      ],
                      selected: {_languageCode},
                      onSelectionChanged: (selection) {
                        setState(() => _languageCode = selection.first);
                      },
                    ),
                    const SizedBox(height: 8),
                    Expanded(
                      child: ListView.builder(
                        itemCount: _messages.length,
                        itemBuilder: (context, index) {
                          final message = _messages[index];
                          final isUser = message.role == MessageRole.user;
                          return Align(
                            alignment: isUser
                                ? AlignmentDirectional.centerEnd
                                : AlignmentDirectional.centerStart,
                            child: Card(
                              color: isUser
                                  ? Theme.of(context)
                                        .colorScheme
                                        .secondaryContainer
                                  : Theme.of(context)
                                        .colorScheme
                                        .surfaceContainerHighest,
                              child: Padding(
                                padding: const EdgeInsets.all(12),
                                child: Text(
                                  message.text,
                                  textDirection: message.languageCode == 'ar'
                                      ? TextDirection.rtl
                                      : TextDirection.ltr,
                                ),
                              ),
                            ),
                          );
                        },
                      ),
                    ),
                    TextField(
                      key: const ValueKey('chat-input'),
                      controller: _input,
                      textDirection: direction,
                      minLines: 1,
                      maxLines: 4,
                      onSubmitted: (_) => _sendMessage(),
                      decoration: const InputDecoration(
                        labelText: 'Message the mock assistant',
                        border: OutlineInputBorder(),
                      ),
                    ),
                    const SizedBox(height: 8),
                    Wrap(
                      spacing: 8,
                      runSpacing: 8,
                      alignment: WrapAlignment.center,
                      children: [
                        FilledButton.icon(
                          key: const ValueKey('send-button'),
                          onPressed: _waitingForReply ? null : _sendMessage,
                          icon: const Icon(Icons.send),
                          label: const Text('Send mock message'),
                        ),
                        OutlinedButton.icon(
                          key: const ValueKey('speech-button'),
                          onPressed: _speaking ? null : _simulateSpeech,
                          icon: const Icon(Icons.volume_up),
                          label: const Text('Simulate speech'),
                        ),
                        OutlinedButton.icon(
                          key: const ValueKey('stop-speech-button'),
                          onPressed: _speaking ? _stopSpeech : null,
                          icon: const Icon(Icons.stop),
                          label: const Text('Stop'),
                        ),
                        OutlinedButton(
                          key: const ValueKey('device-control-button'),
                          onPressed: _showUnsupportedCapability,
                          child: const Text('Device control status'),
                        ),
                      ],
                    ),
                    if (_waitingForReply)
                      const Padding(
                        padding: EdgeInsets.only(top: 8),
                        child: Text('Waiting for the local mock provider…'),
                      ),
                    if (_speaking)
                      const Padding(
                        padding: EdgeInsets.only(top: 8),
                        child: Text('Mock speech active — no audio is played.'),
                      ),
                    if (_capabilityNotice != null)
                      Padding(
                        padding: const EdgeInsets.only(top: 8),
                        child: Text(
                          _capabilityNotice!,
                          key: const ValueKey('capability-notice'),
                        ),
                      ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
