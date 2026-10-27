# JARVIS technology proof of concept

This isolated Flutter app is a technology-selection prototype only. It does not
connect to an AI service, capture microphone audio, play synthesized speech, or
control the host device.

## Run on Windows

Install Flutter 3.47.8 and the Windows desktop build prerequisites, then run:

```powershell
flutter pub get
flutter run -d windows
```

## Build for Android 16

Install Android SDK Platform 36 and JDK 21, then run:

```powershell
flutter pub get
flutter build apk --debug
```

The prototype sets Android API 29 as a provisional minimum and API 36 as the
compile/target API. API 29 is not a production support decision.

## What to verify

- Switch between English LTR and Arabic RTL, then submit mock messages.
- Confirm responses are local canned data; no AI credentials or network calls
  are used.
- Start and stop the speech simulation. It does not produce audio; tests verify
  that overlapping playback is rejected and cancellation completes.
- The device-control status must report that the capability is unsupported.
- Run `flutter analyze` and `flutter test` before building.

The app does not demonstrate real speech recognition, real TTS quality,
physical-device permissions, background behavior, or native system control.
