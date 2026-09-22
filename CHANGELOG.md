# Changelog

## 2026-09-22 — Phase 8 minimal AWS Dev deployment

- Added repeatable CloudFormation bootstrap and Dev templates for private S3
  uploads, Standard SQS with DLQ, DynamoDB, private ECR, an x86_64 inference
  Lambda, two lightweight job API Lambdas, IAM-protected HTTP API, least-privilege
  roles, retained CloudWatch logs, and a DLQ alarm. No VPC/NAT or always-on server.
- Deployed to the confirmed AWS Dev account in `us-east-1` with a 10 USD monthly
  account-wide Budget and 50%/100% email alerts, two-day video expiration,
  five-receive DLQ redrive, batch size one, and a 300-second/3008-MiB Worker.
  The account's current Lambda memory quota rejected 3072 MiB; CloudFormation
  rolled that attempt back cleanly before the corrected deployment succeeded.
- Recognized S3's one-off `s3:TestEvent` notification in the SQS worker so the
  configuration probe is acknowledged without inference or false DLQ alarms.
  The deployed update overlays only the worker parser on the Phase 7-validated
  image; the model and inference pipeline are unchanged.
- Kept Flutter and the legacy Flask route unchanged. Real AWS video inference,
  failure/lease/DLQ exercises, cold/warm timings, and cost measurement remain
  Phase 9 work.

## 2026-09-18–22 — Phase 7 Lambda inference container

- Added a dedicated AWS Lambda Python 3.12 / Amazon Linux 2023 `linux/amd64`
  inference-worker image; the newer base preserves the existing MediaPipe
  0.10.21 Linux wheel requirement while preserving the existing Flask/Gunicorn
  image and SQS production handler.
- Pinned CPU-only PyTorch/torchvision and the Phase 5.5-compatible MediaPipe,
  OpenCV, scikit-learn, and Ultralytics runtime; excluded unused CUDA, JAX,
  audio, and GUI OpenCV dependencies from the worker image.
- Added a build-failing manifest check for the bundled YOLO checkpoint and two
  private classifier bundles. The classifiers remain ignored by Git and are
  staged only from a trusted local deployment source.
- Added an opt-in local Lambda Runtime Interface Emulator handler and runner for
  all real demo videos, exact Linux legacy/optimized parity, repeated warm invocation,
  YOLO singleton reuse, image size, dependency versions, inference time, peak
  RSS, and per-job `/tmp` use.
- Added container/asset contract tests and a complete local runbook. No AWS
  resource, Flutter code, prediction setting, model, or result schema changed.
- Local `linux/amd64` image built and ran all three real demo videos on
  2026-09-22. Linux legacy/optimized results matched exactly, the repeated
  call reused YOLO, and cross-platform classification/coaching decisions
  matched. Windows/Linux MediaPipe tracking produced numeric shot/release and
  form-confidence differences, documented in the validation report.

## 2026-09-17 — Inference optimization and AWS migration foundation

### Framework-independent inference

- Extracted the existing prediction flow into a reusable `predict_video()`
  boundary that can run without Flask and creates isolated temporary workspaces.
- Kept the legacy `/get_prediction` API as the working fallback while routing it
  through the shared inference implementation.
- Added warm-cached classifier bundles and a lazy process-wide YOLO detector so
  repeated jobs do not reconstruct the models.
- Moved runtime uploads and generated artifacts outside the source tree and added
  local inference and compatibility scripts.

### Phase 5.5 performance optimization

- Replaced the default YOLO subprocess and per-frame disk pipeline with
  sequential decoding, in-memory detection/rendering, and direct annotated-video
  writing.
- Preserved the established 640-pixel input, confidence and IoU thresholds, NMS,
  FP32 behavior, JPEG quality-95 compatibility transform, MediaPipe behavior,
  classifiers, trajectory output, and final prediction schema.
- Retained the original implementation as a selectable regression path and
  added exact detection, trajectory, classification, and final-JSON comparison.
- Verified all three public demo videos and 1,491 post-NMS detections. Average
  runtime fell from 42.09 to 32.00 seconds (24.0%), while average temporary disk
  usage fell from 117.61 MiB to 10.22 MiB (91.3%).

### AWS asynchronous job application layer

- Added Lambda-compatible `POST /jobs` and `GET /jobs/{job_id}` handlers,
  DynamoDB job persistence, S3 presigned uploads, and a queue-driven inference
  worker without deploying cloud resources.
- Derived private object keys from UUIDs and validated MIME types instead of
  trusting client filenames; no AWS credentials or account IDs are stored in
  source.
- Changed the target delivery path to S3 `ObjectCreated` -> Standard SQS queue ->
  inference Lambda, with one job per invocation and partial-batch failure output.
- Added processing leases, attempt counts, unique worker tokens, atomic stale
  lease reclamation, and token-protected completion/failure updates so a timed-out
  invocation cannot permanently strand or overwrite a job.
- Added retry release for recoverable exceptions and DLQ-compatible terminal
  behavior. The documented initial recommendation is three processing attempts
  with an SQS `maxReceiveCount` of five.

### Deployment preparation and validation

- Added a production Dockerfile, Gunicorn dependency, CodeBuild/ECR build spec,
  headless OpenCV, pinned runtime-compatible MediaPipe/scikit-learn versions, and
  support for injecting the Firebase service account as a managed JSON secret.
- Documented the API contract, S3 key layout, DynamoDB state machine, SQS event
  envelope, lease timing requirements, DLQ behavior, and remaining infrastructure
  work.
- Expanded the complete backend suite from 27 to 65 passing tests, including
  inference parity, model reuse, DynamoDB lease races, stale-worker protection,
  SQS/S3 parsing, retry behavior, and DLQ-compatible failures.
- Verified Python compilation and a clean Git whitespace check. Flutter and the
  production ML prediction behavior were intentionally left unchanged.

## 2026-09-15 — Mobile reliability and App Store readiness

### API compatibility and session lifecycle

- Centralized mobile HTTP behavior in a typed API client while preserving the
  existing backend endpoint and response-field contract.
- Added consistent timeout, server-error, empty-state, and terminal 401 handling;
  an unrecoverable authentication failure now clears the navigation stack.
- Added asynchronous job polling with bounded backoff and retry behavior that
  retains a known job ID after transient network errors to avoid duplicate uploads.
- Added proactive Firebase ID-token refresh, one-time reactive 401 refresh and
  retry, rotated refresh-token support, single-flight refresh coordination, and
  session revision checks that prevent a stale response from restoring a signed-out
  session.

### Typed history and navigation

- Replaced loosely typed history maps with nullable domain models and an enum
  that safely preserves unknown future classification values.
- Added loading, retry, pull-to-refresh, empty, sorted-list, and detail states for
  history, including direct processed-video playback and coaching details.
- Moved the main shell to Material 3 navigation and added direct routing from a
  completed analysis to the History destination.

### Account deletion and legal access

- Added authenticated `DELETE /account` support that deletes Firestore analysis
  records in bounded batches, private Firebase Storage objects, server job data,
  and finally the Firebase Authentication identity.
- Serialized deletion against per-user result publication so queued or running
  analysis work cannot recreate private data after an account has been deleted.
- Added an Account destination with sign-out, Privacy Policy, Terms of Service,
  and a clearly confirmed permanent account-deletion action.
- Made the policy and terms readable before account creation from both the login
  and registration flows. The included copy reflects the implemented Firebase
  and privacy-conscious LLM data paths and remains subject to owner/legal review
  before App Store submission.

### iOS release preparation

- Raised the Xcode project and Flutter framework deployment target from iOS 12
  to iOS 13 and restored the CocoaPods integration file required by native Flutter
  plugins.
- Added a canonical iOS release wrapper and a runtime safeguard that reject empty,
  non-HTTPS, local, reserved, query-bearing, fragment-bearing, or credential-bearing
  production API URLs.
- Documented the macOS `pod install` and signed IPA workflow without embedding
  backend credentials or Apple signing material in application configuration.

### Validation

- Expanded the backend suite to 27 passing tests, including bounded, retry-safe
  account cleanup and the authentication compatibility contract.
- Expanded the Flutter suite to 15 passing tests, including account/legal UI,
  deletion requests, typed API behavior, token refresh, and release URL validation.
- Verified Python compilation, a successful Android debug APK build, and no new
  analyzer errors or warnings; the existing information-level style debt remains
  visible.

## 2026-08-15 — Safer, lower-cost LLM coaching

### Model and request configuration

- Replaced the required unspecified model setting with a configurable
  `gpt-5.4-nano` low-cost default; OpenAI API usage remains metered, not free.
- Added explicit low reasoning effort and low response verbosity defaults for
  the short coaching workload, with environment overrides for model and effort.

### Prompt quality and privacy

- Replaced raw frame-level landmark uploads with a local anonymous summary of
  elbow angles, wrist heights, forearm offsets, shoulder tilt, and data quality.
- Added a deterministic coaching-label generator that stores good-form reference
  bands during pose-model training and reports up to two ranked, evidence-backed
  deviations for bad-form predictions.
- Added prediction confidence and sanitized coaching labels to Firestore analysis
  records, while preserving compatibility with older model bundles.
- Restricted the LLM to explaining locally generated findings, correction goals,
  and drills instead of inventing posture problems from aggregate measurements.
- Changed user-facing coaching to English-only `Main Findings` and
  action-focused `How to Improve` sections. Internal label codes, redundant
  generic flags, data-quality sections, and limits/safety sections are no longer
  shown to users.
- Rewrote the coaching prompt with evidence boundaries, known pose-estimation
  limitations, a two-section English output contract, and a 180-word response
  limit.
- Prevented conclusions when fewer than five usable shot frames are available
  and prohibited invented ideal angles, injury claims, handedness assumptions,
  professional-player comparisons, and unsupported lower-body feedback.
- Added unit tests for reference-profile creation, label ranking, predicted-class
  confidence, legacy-bundle fallback, context sanitization, and the existing API
  privacy and insufficient-data contracts.

### Retraining validation

- Retrained the pose classifier on 36 recording-level samples (7 bad-form and
  29 good-form recordings) with repeated stratified 5-fold cross-validation over
  10 repeats.
- Recorded 81.7% accuracy, 66.4% balanced accuracy, and 67.9% macro F1. Bad-form
  recall remained only 41.4%, with a 58.6% false-good rate, so this model is kept
  for development and label integration testing rather than presented as a
  production-quality result.
- Verified that the local model bundle contains four aggregate good-form reference
  features and can produce a specific evidence-backed elbow label. Generated model
  files remain excluded from Git; the reproducible evaluation report stays under
  `BackendServer/reports/`.

## 2026-08-15 — Reproducible model evaluation reports

### Evaluation metrics

- Added one shared repeated-stratified-cross-validation evaluator for the pose
  and trajectory classifiers, using five folds and ten repeats by default.
- Standardized every report on accuracy, balanced accuracy, macro precision,
  macro recall, macro F1, a confusion matrix, and per-class recall.
- Added deterministic 95% percentile confidence intervals that bootstrap whole
  recordings within each class together with their repeated predictions.
- Made bad-form recall the pose model's safety-focused metric and added the
  complementary false-good rate to expose bad poses misclassified as good.

### Reproducibility and validation

- Added privacy-safe Markdown, JSON, and confusion-matrix CSV report artifacts
  generated by both training commands.
- Moved the 2026-08-13 figure and metrics to a dated historical report while
  keeping the README focused on the current evaluation summary.
- Added regression tests for the complete metric contract, confidence-interval
  bounds, confusion-matrix counts, false-good reporting, and output files.
- Documented the evaluation protocol and clarified that internal bootstrap
  intervals do not replace shooter/session grouping or an external test set.

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
