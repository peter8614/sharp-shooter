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

## Cognito Dev App API (Phase 10)

The new Dev path uses Cognito browser login with PKCE, a JWT-authenticated
`/app/jobs` API, direct presigned S3 PUT, then three-second polling and inline
result display. Supply `APP_API_URL`, `COGNITO_CLIENT_ID`, and
`COGNITO_ISSUER` together as public `--dart-define` values; see
[`docs/aws-phase10-cognito.md`](../docs/aws-phase10-cognito.md). Never put IAM
credentials in Flutter. Omitting all three values keeps the legacy backend
flow. Dev registration is invitation-only, and legacy history/account
features are not yet migrated to Cognito.

Completed App results show the annotated shot video and, when available, the
closest NBA catalog clip with an experimental similarity score. Playback uses
owner-checked API routes to obtain five-minute private S3 URLs on demand; the
URLs are not persisted. A video can become unavailable after the seven-day
result retention period. The score is a catalog-ranking heuristic, not a
validated probability. The older Flask result screen remains separate.

The App result also presents classifier findings in English without exposing
internal codes: shooting form and ball trajectory explicitly show the model's
Good/Bad judgment (or Unavailable) with confidence where available. Optional
AI coaching appears after the completed result when
the separate backend task finishes; a failure leaves video, score, and
evidence-based advice usable. Flutter never holds the OpenAI API key.
Android Dev testing confirmed playback of both private videos after the
Get Job Lambda received its S3 bucket configuration. iOS device testing is
still required before release.

Run `flutter pub get` before building or running the Cognito version. In
particular, do not use `--no-pub` on a fresh checkout: Flutter needs to
generate its native plugin registration file so the Android AppAuth redirect
activity and secure-storage plugin are included in the APK. A missing plugin
can make **Sign in securely** fail before any browser opens.

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
