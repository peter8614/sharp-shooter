# Changelog

## 2026-08-13 — Model retraining and Android build validation

### Model training

- Replaced the shooting-form Random Forest with a class-balanced Extra Trees
  classifier selected through repeated stratified cross-validation.
- Refit deployable pose and trajectory models on all labeled recordings after
  holdout evaluation, while retaining the holdout solely for reporting.
- Expanded the private trajectory dataset from one to ten negative examples by
  extracting nine reviewed bad-arc candidate videos with valid ball tracks.
- Recorded 5-fold, 10-repeat cross-validation results: pose accuracy 81.7%,
  balanced accuracy 68.3%, macro F1 64.0%; trajectory accuracy 95.6%, balanced
  accuracy 90.0%, macro F1 91.7%.
- Added the aggregate, privacy-safe training visualization at
  `docs/training-results-1024.png`. Raw videos, private indexes, and serialized
  models remain excluded from Git.

### Training environment and pipeline

- Added a project-local Python environment workflow and dependency constraints
  compatible with the bundled legacy YOLOv5 checkpoint.
- Pinned PyTorch below 2.6 and setuptools below 81 to retain trusted legacy
  checkpoint and `pkg_resources` compatibility; declared GitPython explicitly.
- Kept Ultralytics and Matplotlib generated configuration beside run artifacts
  instead of writing user-profile caches.
- Added English comments explaining the compatibility and final-refit choices.

### Android build compatibility

- Upgraded Gradle to 8.14, Android Gradle Plugin to 8.11.1, and Kotlin Gradle
  Plugin to 2.2.20 for Flutter 3.44 compatibility on JDK 17.
- Removed the obsolete generated `FlutterMultiDexApplication` that referenced a
  missing legacy multidex library.
- Verified dependency resolution, Flutter tests, and a successful debug APK
  build. Static analysis still reports maintainability lints that will be
  addressed separately.

### Continuous integration

- Added a secret-free GitHub Actions workflow for pull requests and `main`.
- Added backend unit tests and Python bytecode compilation on Python 3.11.
- Added Flutter dependency resolution, tests, static analysis, and a JDK 17
  Android debug APK build using Flutter 3.44.9.
- Kept current warning/info lint debt visible but non-blocking; analyzer errors,
  test failures, and build failures remain blocking.
- Added a bounded three-attempt retry for transient Gradle or Maven download
  interruptions without hiding persistent compilation failures.

### Interpretation limits

- The trajectory result may be optimistic because the added negative examples
  originate from one related video group.
- The pose model remains constrained by only seven negative recordings.
- Future evaluation must split by shooter/session and use a held-out external
  test set before making statistical-significance or production claims.

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
