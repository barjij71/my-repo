import 'dart:math' as math;

import 'package:flutter/material.dart';

/// A lightweight, animated holographic JARVIS avatar for the Windows/Android
/// prototype. It is drawn with Flutter Canvas, so it needs no native 3D plugin
/// and stays usable on both targets while a model-backed renderer is evaluated.
class JarvisAvatar extends StatefulWidget {
  const JarvisAvatar({super.key, this.height = 220});

  final double height;

  @override
  State<JarvisAvatar> createState() => _JarvisAvatarState();
}

class _JarvisAvatarState extends State<JarvisAvatar>
    with SingleTickerProviderStateMixin {
  late final AnimationController _motion = AnimationController(
    vsync: this,
    duration: const Duration(seconds: 12),
  )..repeat();

  @override
  void dispose() {
    _motion.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Semantics(
      label: 'JARVIS animated holographic avatar',
      child: Container(
        key: const ValueKey('jarvis-avatar'),
        height: widget.height,
        width: double.infinity,
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(18),
          border: Border.all(color: const Color(0x5538DFFF)),
          gradient: const RadialGradient(
            center: Alignment(0, -0.15),
            radius: 0.9,
            colors: [Color(0xFF0B3045), Color(0xFF061521), Color(0xFF030B12)],
          ),
        ),
        clipBehavior: Clip.antiAlias,
        child: Stack(
          children: [
            Positioned.fill(
              child: AnimatedBuilder(
                animation: _motion,
                builder: (context, child) => CustomPaint(
                  painter: _HologramPainter(phase: _motion.value * math.pi * 2),
                ),
              ),
            ),
            const Positioned(
              left: 14,
              top: 12,
              child: _HudLabel(text: 'J.A.R.V.I.S', color: Color(0xFF64EDFF)),
            ),
            const Positioned(
              right: 14,
              top: 13,
              child: _HudLabel(text: 'AVATAR / LIVE', color: Color(0xFF69CFE5)),
            ),
            const Positioned(
              left: 0,
              right: 0,
              bottom: 10,
              child: Center(
                child: Text(
                  'HOLOGRAPHIC INTERFACE · PROTOTYPE',
                  style: TextStyle(
                    color: Color(0xFF75B7C9),
                    fontSize: 9,
                    letterSpacing: 2.0,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _HudLabel extends StatelessWidget {
  const _HudLabel({required this.text, required this.color});

  final String text;
  final Color color;

  @override
  Widget build(BuildContext context) => Text(
        text,
        style: TextStyle(
          color: color,
          fontSize: 9,
          letterSpacing: 1.5,
          fontWeight: FontWeight.w700,
        ),
      );
}

class _HologramPainter extends CustomPainter {
  const _HologramPainter({required this.phase});

  final double phase;

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height * 0.51);
    final scale = math.min(size.width / 340, size.height / 210);
    final cyan = const Color(0xFF35E5FF);
    final blue = const Color(0xFF198FC4);

    final glow = Paint()
      ..color = cyan.withValues(alpha: 0.08)
      ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 22);
    canvas.drawCircle(center, 48 * scale, glow);

    final ringPaint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1
      ..color = cyan.withValues(alpha: 0.40);
    canvas.save();
    canvas.translate(center.dx, center.dy + 5 * scale);
    canvas.rotate(phase * 0.12);
    canvas.drawOval(
      Rect.fromCenter(
        center: Offset.zero,
        width: 154 * scale,
        height: 42 * scale,
      ),
      ringPaint,
    );
    canvas.rotate(-phase * 0.24);
    ringPaint.color = blue.withValues(alpha: 0.75);
    canvas.drawOval(
      Rect.fromCenter(
        center: Offset.zero,
        width: 126 * scale,
        height: 32 * scale,
      ),
      ringPaint,
    );
    canvas.restore();

    final head = Path()
      ..moveTo(center.dx - 28 * scale, center.dy - 38 * scale)
      ..cubicTo(
        center.dx - 30 * scale,
        center.dy - 57 * scale,
        center.dx - 15 * scale,
        center.dy - 67 * scale,
        center.dx,
        center.dy - 67 * scale,
      )
      ..cubicTo(
        center.dx + 20 * scale,
        center.dy - 67 * scale,
        center.dx + 31 * scale,
        center.dy - 51 * scale,
        center.dx + 28 * scale,
        center.dy - 34 * scale,
      )
      ..lineTo(center.dx + 24 * scale, center.dy - 13 * scale)
      ..cubicTo(
        center.dx + 22 * scale,
        center.dy + 1 * scale,
        center.dx + 12 * scale,
        center.dy + 11 * scale,
        center.dx,
        center.dy + 12 * scale,
      )
      ..cubicTo(
        center.dx - 13 * scale,
        center.dy + 10 * scale,
        center.dx - 23 * scale,
        center.dy,
        center.dx - 25 * scale,
        center.dy - 14 * scale,
      )
      ..close();

    final headFill = Paint()
      ..style = PaintingStyle.fill
      ..shader = const LinearGradient(
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
        colors: [Color(0xBB1AA7D0), Color(0x5537E8FF), Color(0x33206B9A)],
      ).createShader(Rect.fromCenter(
        center: center,
        width: 90 * scale,
        height: 110 * scale,
      ));
    canvas.drawPath(head, headFill);

    final outline = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.35
      ..color = cyan.withValues(alpha: 0.95);
    canvas.drawPath(head, outline);

    final faceLine = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.15
      ..strokeCap = StrokeCap.round
      ..color = const Color(0xFF9DF7FF).withValues(alpha: 0.9);
    final eyeY = center.dy - 28 * scale;
    canvas.drawLine(
      Offset(center.dx - 18 * scale, eyeY),
      Offset(center.dx - 7 * scale, eyeY + math.sin(phase) * scale),
      faceLine,
    );
    canvas.drawLine(
      Offset(center.dx + 7 * scale, eyeY + math.sin(phase) * scale),
      Offset(center.dx + 18 * scale, eyeY),
      faceLine,
    );
    canvas.drawLine(
      Offset(center.dx, center.dy - 23 * scale),
      Offset(center.dx - 2 * scale, center.dy - 9 * scale),
      faceLine,
    );
    canvas.drawLine(
      Offset(center.dx - 8 * scale, center.dy + 1 * scale),
      Offset(center.dx + 8 * scale, center.dy + 1 * scale),
      faceLine,
    );

    final shoulders = Path()
      ..moveTo(center.dx - 47 * scale, center.dy + 47 * scale)
      ..cubicTo(
        center.dx - 42 * scale,
        center.dy + 25 * scale,
        center.dx - 22 * scale,
        center.dy + 15 * scale,
        center.dx,
        center.dy + 15 * scale,
      )
      ..cubicTo(
        center.dx + 22 * scale,
        center.dy + 15 * scale,
        center.dx + 42 * scale,
        center.dy + 25 * scale,
        center.dx + 47 * scale,
        center.dy + 47 * scale,
      );
    canvas.drawPath(shoulders, outline);

    final scan = Paint()
      ..color = cyan.withValues(alpha: 0.13)
      ..strokeWidth = 1;
    for (var i = 0; i < 5; i++) {
      final y = center.dy - 54 * scale + i * 22 * scale;
      canvas.drawLine(
        Offset(center.dx - 63 * scale, y),
        Offset(center.dx + 63 * scale, y),
        scan,
      );
    }

    final orbitDot = Offset(
      center.dx + math.cos(phase) * 78 * scale,
      center.dy + 5 * scale + math.sin(phase) * 21 * scale,
    );
    canvas.drawCircle(
      orbitDot,
      2.4 * scale,
      Paint()..color = const Color(0xFFD8FCFF),
    );
  }

  @override
  bool shouldRepaint(covariant _HologramPainter oldDelegate) =>
      oldDelegate.phase != phase;
}
