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
