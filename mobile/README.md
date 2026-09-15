# Sharp Shooter mobile client

This Flutter application records or selects a basketball-shot video, uploads it
to the authenticated Sharp Shooter API, and displays processed analysis history.

The backend endpoint is intentionally not committed. Supply a valid HTTPS URL at
build or run time:

```bash
flutter pub get
flutter run --dart-define=BACKEND_URL=https://your-api.example.com
```

Firebase credentials are handled by the backend. Do not place service-account
keys, API secrets, signing keys, personal videos, or generated pose data in this
directory.

## iOS release build

iOS 13 is the minimum deployment target. From macOS, install the supported
Flutter/Xcode toolchain and CocoaPods, then generate the plugin workspace:

```bash
flutter pub get
cd ios && pod install && cd ..
```

Release builds must use the checked release wrapper. It rejects an empty,
insecure, local, or placeholder API URL before Flutter creates the archive:

```bash
BACKEND_URL=https://api.your-production-domain.com \
  bash tool/build_ios_release.sh --build-name=1.1.0 --build-number=2
```

The API URL is public application configuration, not a secret. Keep service
credentials and App Store signing material outside `--dart-define` values.
