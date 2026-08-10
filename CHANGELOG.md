# Changelog

## 2026-08-11 — Authenticated API and mobile client update

### Security and privacy

- Added Firebase bearer-token verification to protected API routes and stopped
  trusting caller-provided user IDs.
- Replaced committed credentials with environment-variable configuration and a
  safe `.env.example` template.
- Added upload size limits, sanitized filenames, video-content validation,
  per-user Storage prefixes, and per-job temporary directories.
- Removed TLS certificate bypasses and hard-coded plaintext API endpoints from
  the Flutter client.
- Excluded raw videos, pose landmarks, private dataset indexes, model outputs,
  service-account files, and mobile platform credentials from Git.
- Disabled OpenAI response storage for pose-derived coaching requests and added
  a privacy-preserving safety identifier.

### Analysis and machine learning

- Corrected MediaPipe shoulder, elbow, and wrist indices and fixed arm-angle and
  release calculations.
- Changed both classifiers to one feature row per video, preventing frames from
  the same recording from leaking across training and validation sets.
- Added body-scale pose normalization, time-aware trajectory interpolation, and
  versioned model bundles with enforced feature schemas.
- Added frame indices to trajectory files and preserved source-video FPS and
  frames without detections.
- Reworked NBA-reference similarity to use normalized absolute differences
  instead of signed differences that could cancel each other.

### Backend and mobile application

- Added a bounded asynchronous analysis queue, job-status endpoint, isolated
  cleanup, H.264 MP4 conversion, authenticated history, video, NBA comparison,
  and optional LLM coaching routes.
- Added the Flutter mobile client with authenticated uploads and history access,
  normal TLS validation, safe local-video playback, controller cleanup, and
  Android/iOS camera and microphone permission descriptions.
- Replaced the stale Flutter counter test and improved camera error handling.

### Validation

- Added feature-extraction regression tests and retained pose/trajectory core
  tests; all six backend tests pass.
- Added example dataset indexes containing only anonymous placeholder names.
- Updated dependency constraints and deployment, privacy, retraining, and HTTPS
  documentation.

### Remaining data requirement

The private local trajectory dataset currently has too few negative recordings
for trustworthy training. The trainer intentionally refuses that dataset until
more reviewed negative samples are collected. Existing landmarks generated with
the old indices should also be regenerated before model training.
