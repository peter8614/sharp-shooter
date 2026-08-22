# Sharp Shooter

[![CI](https://github.com/peter8614/sharp-shooter/actions/workflows/ci.yml/badge.svg)](https://github.com/peter8614/sharp-shooter/actions/workflows/ci.yml)

An end-to-end basketball shot analysis system that turns a phone video into explainable feedback on shooting form and ball trajectory. Sharp Shooter combines a Flutter mobile experience, a secure Flask API, computer-vision pipelines, classical machine learning, and privacy-conscious LLM coaching.

## Demo videos

- [Demo 1 — processed shot and AI coaching](docs/demos/sharp-shooter-demo-1.mp4)
- [Demo 2 — trajectory analysis and reference comparison](docs/demos/sharp-shooter-demo-2.mp4)
- [Demo 3 — outdoor shot analysis and coaching summary](docs/demos/sharp-shooter-demo-3.mp4)

These short, silent screen recordings demonstrate the mobile analysis workflow.
Audio and device metadata were removed before publication. See the
[demo media notice](docs/demos/README.md) for attribution and usage context.

## What I built

- Delivered a cross-platform Flutter workflow for recording or selecting a shot, authenticated upload, asynchronous progress tracking, processed-video playback, analysis history, and coaching results.
- Built a Flask analysis service that extracts upper-body landmarks with MediaPipe, tracks the basketball with a YOLOv5 detector adapted from the MIT-licensed [basketball-detection](https://github.com/Stardust87/basketball-detection) project, classifies shooting form and trajectory, and returns an H.264 annotated video.
- Designed recording-level feature pipelines and versioned model bundles so training and inference share an enforced feature schema.
- Prevented validation leakage by treating each video as one sample instead of splitting frames from the same recording across training and validation.
- Added evidence-backed coaching: deterministic local logic selects at most two supported form findings, while the LLM only turns those findings into concise, actionable drills.
- Reduced the LLM privacy surface by sending anonymous aggregate measurements rather than raw frame landmarks, filenames, or videos.
- Hardened the upload and job pipeline with Firebase token verification, bounded concurrency, isolated workspaces, media validation, sanitized filenames, configurable size limits, and TLS-only production endpoints.
- Established CI for Python tests and compilation, Flutter tests and static analysis, and Android APK builds.

## Results

Models are evaluated with 5-fold, 10-repeat stratified cross-validation at the recording level. Reports include balanced accuracy, macro metrics, per-class recall, confusion matrices, and recording-level bootstrap confidence intervals.

| Model | Accuracy | Balanced accuracy | Macro F1 | Safety-focused result |
| --- | ---: | ---: | ---: | --- |
| Shot trajectory | 95.6% | 90.0% | 93.1% | 80.0% bad-trajectory recall |
| Shooting form | 81.7% | 66.4% | 67.9% | 41.4% bad-form recall |

The trajectory model demonstrates strong prototype performance. The form result also exposes the next data objective clearly: the current private dataset contains only seven bad-form recordings, so the model is presented as an engineering prototype rather than a production coaching or medical system. See the full [pose report](BackendServer/reports/landmark-evaluation.md), [trajectory report](BackendServer/reports/trajectory-evaluation.md), and [evaluation protocol](docs/model-evaluation.md).

## System architecture

```text
Flutter mobile app
    │  Firebase ID token + video upload
    ▼
Flask API / bounded job queue
    ├── MediaPipe pose landmarks ──► form features ──► Extra Trees classifier
    ├── YOLOv5 ball tracking ───────► arc features ──► trajectory classifier
    ├── OpenCV + FFmpeg ────────────► annotated H.264 video
    └── supported findings ─────────► constrained LLM coaching
                         │
                         ▼
              Firebase Storage / Firestore
```

## Technology

| Area | Technologies and techniques |
| --- | --- |
| Mobile | Flutter, Dart, Camera, Chewie, authenticated HTTP, Android/iOS permissions |
| Backend | Python, Flask, asynchronous bounded worker pool, REST APIs |
| Computer vision | MediaPipe Pose, Ultralytics YOLOv5, a third-party basketball detector, OpenCV, FFmpeg |
| Machine learning | scikit-learn, Extra Trees, recording-level feature engineering, repeated stratified cross-validation, bootstrap confidence intervals |
| Generative AI | OpenAI API, evidence-constrained prompting, data minimization, safety identifiers |
| Cloud and security | Firebase Authentication, Firestore, Cloud Storage, bearer-token verification, isolated job directories |
| Quality | unittest, Flutter Test, Dart analyzer, GitHub Actions, reproducible Markdown/JSON/CSV evaluation reports |

## Engineering highlights

### Trustworthy evaluation

The original frame-level approach could place frames from the same video in both training and validation. The current pipeline creates one feature row per recording, performs repeated stratified evaluation, reports class-sensitive metrics, and highlights false-good predictions rather than relying on accuracy alone.

### Explainable coaching

The pose model stores good-form reference bands for interpretable features such as elbow angle and wrist height. Local code ranks deviations and provides the LLM with named findings, correction goals, and drills. The prompt prevents unsupported injury claims, invented ideal angles, lower-body conclusions, and professional-player comparisons. The complete contract is documented in [docs/llm-coaching.md](docs/llm-coaching.md).

### Privacy and API security

The server derives identity from verified Firebase ID tokens instead of trusting a client-provided user ID. Raw videos and landmarks stay out of Git, uploads are validated and isolated per job, and LLM requests contain aggregate pose summaries rather than raw biometric sequences. See [PRIVACY.md](PRIVACY.md) and [SECURITY.md](SECURITY.md).

## Repository layout

```text
mobile/                  Flutter application
BackendServer/           Flask API, vision pipeline, training code, and tests
BackendServer/reports/   Reproducible, privacy-safe model evaluation artifacts
docs/                    Evaluation and LLM coaching design notes
docs/demos/              Privacy-sanitized product demonstration videos
frontend/                Static product concept UI
THIRD_PARTY_NOTICES.md   Attribution and third-party license summary
```

## Run locally

### Backend

Requirements: Python 3.11, FFmpeg, Firebase credentials, and the trusted project model checkpoint.

```powershell
cd BackendServer
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python server.py
```

Configure Firebase in `.env`. `OPENAI_API_KEY` is optional and is only required for generated coaching. The development server listens on `127.0.0.1`; production deployment requires a WSGI server, HTTPS, and least-privilege Firebase rules.

### Mobile

```powershell
cd mobile
flutter pub get
flutter run --dart-define=BACKEND_URL=https://your-api.example.com
```

## Test and evaluate

```powershell
cd BackendServer
python -m unittest discover -s tests -v
python -m compileall .
python landmark_classification.py
python trajectory_classification.py

cd ..\mobile
flutter analyze
flutter test
```

GitHub Actions repeats the backend checks, Flutter tests and analysis, and an Android debug build on pushes and pull requests to `main`.

## License and attribution

Sharp Shooter is released under the [GNU Affero General Public License v3.0](LICENSE). The bundled Ultralytics YOLOv5 source remains subject to AGPL-3.0.

The basketball detector weights and portions of the trajectory-processing pipeline originate from [Stardust87/basketball-detection](https://github.com/Stardust87/basketball-detection), created by Michał Szachniewicz and Anna Klimiuk and published under the MIT License. This project preserves the upstream copyright and license notice in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and [LICENSES/MIT-Stardust87.txt](LICENSES/MIT-Stardust87.txt).

## Scope

Sharp Shooter demonstrates full-stack product development, applied computer vision, ML evaluation, cloud authentication, and responsible AI integration. It is a portfolio prototype, not a medical device or a substitute for a qualified coach. Production validation would require a larger, coach-reviewed dataset split by shooter and session, an independent test set, formal retention/deletion controls, and production-grade deployment infrastructure.
