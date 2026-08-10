# Sharp Shooter

Sharp Shooter is an experimental basketball shooting-form analysis pipeline. It
combines MediaPipe pose estimation with a custom YOLOv5 basketball detector to
extract upper-body motion, track the ball, draw its trajectory, and prepare
video-level features for form and shot-arc classifiers.

> **Project status:** research prototype. The video-processing pipeline works,
> but meaningful form and arc predictions require a sufficiently large,
> representative, and carefully labeled dataset.

## Features

- Extracts shoulder, elbow, and wrist landmarks with MediaPipe Pose.
- Supports right- and left-handed shooters.
- Detects likely shooting and release frames from arm elevation and extension.
- Detects basketball positions with a bundled custom YOLOv5 model.
- Draws a continuous trajectory without dropping frames that have no detection.
- Preserves the source video's frame rate in the rendered output.
- Builds one fixed-size machine-learning sample per video.
- Trains and saves Random Forest classifiers for shooting form and ball arc.
- Includes unit tests for pose indexing, safe trajectory loading, feature
  aggregation, and missing-detection frame handling.

## Architecture

```text
Input video
   |
   +-- MediaPipe Pose --> shot-frame landmarks --> form features --> form model
   |
   +-- YOLOv5 detector --> ball centers --> rendered trajectory --> arc features
                                                        |
                                                        +--> arc model
```

The pose and ball-detection paths run independently and write their artifacts to
the same per-video output directory. Trained classifiers are optional: before
model files exist, analysis still produces landmarks, trajectory data, and an
annotated video.

## Repository layout

```text
.
|-- BackendServer/
|   |-- main.py                         # Main analysis and dataset workflow
|   |-- video_pipeline.py               # YOLOv5 detection and video rendering
|   |-- landmark_classification.py      # Form feature extraction and training
|   |-- trajectory_classification.py    # Arc feature extraction and training
|   |-- requirements.txt
|   |-- models/
|   |   `-- yolov5s_basketball.pt       # Custom basketball detector
|   |-- data/                           # Empty dataset index files
|   |-- tests/                          # Unit tests
|   |-- utils/                          # Frame conversion and drawing helpers
|   `-- yolov5/                         # Bundled third-party YOLOv5 runtime
|-- frontend/                           # Static project landing-page prototype
|-- PRIVACY.md
|-- SECURITY.md
`-- README.md
```

## Requirements

- Python 3.11 or 3.12
- Windows, macOS, or Linux
- A recent FFmpeg/OpenCV-compatible video environment
- CPU for basic use; a CUDA-capable PyTorch installation is optional

The default dependency constraints keep NumPy below version 2 because the
supported MediaPipe release requires it.

## Installation

Clone the repository and create a fresh virtual environment:

```bash
git clone <your-repository-url>
cd sharp-shooter/BackendServer
python -m venv .venv
```

Activate it on Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Activate it on macOS or Linux:

```bash
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

For CUDA, install the appropriate PyTorch build for the local CUDA version before
installing the remaining requirements.

## Analyze a video

Run the command from `BackendServer`:

```bash
python main.py path/to/shot.mp4 --device cpu
```

Useful options:

```text
--arm R|L          Shooting arm (default: R)
--device cpu|0     YOLOv5 inference device
--output PATH      Output root directory
--clean            Remove extracted and rendered intermediate frames
--form-label 0|1   Register the video as bad/good form training data
--arc-label 0|1    Register the video as bad/good arc training data
```

Example for a left-handed shooter on the first CUDA device:

```bash
python main.py path/to/left_hand_shot.mp4 --arm L --device 0 --clean
```

## Output artifacts

For `shot.mp4`, the default output directory is `BackendServer/output/shot/`:

```text
landmark_data.csv       Upper-body landmarks for detected shot frames
trajectory.txt          Accepted basketball center coordinates
output_shot.avi         Annotated video with the ball trajectory
labels/                 YOLO detection labels
images_raw/             Extracted frames unless --clean is used
images_draw/            Annotated frames unless --clean is used
```

The command also reports frame counts and optional classifier results. Until
trained model bundles are available, `form_prediction` and `arc_prediction` are
`None`.

## Build a labeled dataset

Labels use `1` for good and `0` for bad. The following command analyzes a video
and registers its generated data in both dataset indexes:

```bash
python main.py path/to/shot.mp4 --form-label 1 --arc-label 1
```

Review every generated CSV and trajectory before accepting its label. For useful
models, collect diverse examples across shooters, heights, camera positions,
lighting conditions, distances, and both outcome classes. Avoid putting clips
from the same recording session in both training and evaluation sets.

No training videos or personal landmark datasets are included in this repository.

## Train the classifiers

Each trainer requires at least six videos, both labels, and at least two videos
per label:

```bash
python landmark_classification.py
python trajectory_classification.py
```

Successful training writes:

```text
models/landmark_classifier.joblib
models/trajectory_classifier.joblib
```

Each model bundle stores both the estimator and its expected feature-column order.
`main.py` automatically loads these files during future analyses.

## Run tests

```bash
python -m unittest discover -s tests -v
```

The current tests are intentionally small and do not download external assets.
Before production use, add integration tests for damaged videos, no-detection
videos, repeated filenames, concurrent jobs, left-handed clips, and model loading.

## Privacy and security

This repository intentionally excludes:

- Private keys, access tokens, passwords, and `.env` files
- Raw basketball videos and extracted frames
- Pose-landmark training datasets
- Personal documents, presentations, and archives
- Virtual environments, IDE configuration, and generated outputs

See [PRIVACY.md](PRIVACY.md) before collecting or sharing videos. See
[SECURITY.md](SECURITY.md) for secret-handling and vulnerability reporting guidance.

The included detector checkpoint was scanned for obvious usernames, email
addresses, private paths, and key material before publication. Its SHA-256 digest
is:

```text
d3f34f56ff85160b185f3995ab807ee74d8fb752c1558e1f33f3d3b24a9a16d4
```

## Known limitations

- Release detection is heuristic and is not a validated biomechanical assessment.
- Raw 2D pose estimates remain sensitive to camera angle, framing, and occlusion.
- Ball selection uses the highest-confidence detection rather than a tracker ID.
- Trajectory files do not yet store frame indices or timestamps.
- The current detector does not provide reliable hoop-relative measurements.
- The static frontend is a visual prototype and is not connected to an API.
- AVI/DIVX output may require conversion for browser playback.
- Processing is synchronous and can be slow on CPU.

Do not use this software for medical, safety-critical, scouting, or eligibility
decisions without independent validation.

## Roadmap

- Add unique run IDs and safe concurrent processing.
- Store timestamps and confidence values with trajectory observations.
- Add temporal ball tracking and hoop detection.
- Normalize pose features by body scale and derive joint-angle sequences.
- Evaluate models by shooter/session groups rather than random clips alone.
- Add an upload API, background jobs, and a results dashboard.
- Produce web-compatible H.264/MP4 output.

## Third-party software and licensing

The `BackendServer/yolov5` directory contains third-party YOLOv5 software and its
license file. It remains subject to the license included in that directory. This
snapshot does not assign a separate license to the project's original source code;
choose and add one before redistributing or accepting external contributions.

## Responsible use

Record and analyze only people who have given informed consent. Obtain guardian
consent where legally required for minors, minimize retention, and delete raw video
and landmark data when it is no longer needed.
