# Sharp Shooter backend

## Setup

Use Python 3.11 or 3.12 in a fresh virtual environment. Do not reuse the checked-in
`.venv`; its NumPy version is incompatible with MediaPipe.

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

Production containers install `requirements-production.txt` and run the Flask
application with Gunicorn. Managed runtimes that cannot mount a credential file
may inject the complete service-account object through the
`FIREBASE_SERVICE_ACCOUNT_JSON` secret instead of
`GOOGLE_APPLICATION_CREDENTIALS`; configure only one of the two.

The checked `Dockerfile` listens on `PORT` (default `8080`) and uses one
Gunicorn worker so the in-memory job registry remains coherent. The CodeBuild
spec builds the private deployment source bundle and pushes its image to ECR;
private classifier bundles belong in that deployment bundle, not in Git.

The queue-driven inference worker has a separate, CPU-only AWS Lambda image in
`Dockerfile.lambda-worker`; it does not include or replace the Flask process.
Its build verifies the bundled YOLO and private classifier files against
`lambda-model-manifest.json`, targets `linux/amd64`, and retains
`inference_worker.lambda_handler` as the production command. The Phase 7 local
runner checks exact Linux legacy/optimized parity, cross-platform prediction
decisions, cold/warm reuse, memory, `/tmp`, and image size. See
[`docs/lambda-container.md`](../docs/lambda-container.md).

## Authentication sessions

`POST /sign_in` and `POST /register` keep their original `idToken` and
`user_id` response fields and also return `refreshToken` and `expiresIn` when
Firebase supplies them. Newer clients can exchange the refresh credential at
`POST /refresh_token` using this JSON body:

```json
{"refresh_token": "<firebase-refresh-token>"}
```

The refresh response uses the same four session fields as sign-in. Clients
should replace both tokens because Firebase may rotate the refresh token. Only
the ID token belongs in the `Authorization: Bearer ...` header; refresh tokens
must never be logged or sent to protected resource endpoints.

`DELETE /account` uses the authenticated ID token and permanently deletes the
user's analysis documents, every Storage object below the user's private prefix,
and then the Firebase Authentication identity. Authentication is removed last so
a partial data-service failure remains retryable. The service serializes deletion
against background analysis publication to prevent a running job from recreating
data after deletion.

## Analyze one video

Run commands from the `BackendServer` folder:

```powershell
.venv\Scripts\python main.py shot\Irvine_good.mp4 --device cpu
```

The run writes landmarks, ball trajectory, extracted frames, and an annotated AVI
under `output/<video-name>/`. To add a labeled example to the two datasets:

```powershell
.venv\Scripts\python main.py shot\Irvine_good.mp4 --form-label 1 --arc-label 1
```

Use `--arm L` for a left-handed shooter. CUDA users can pass `--device 0`.

## Test inference without Flask

Run the reusable inference core directly from the repository root:

```powershell
python BackendServer/scripts/test_inference.py docs/demos/sharp-shooter-demo-3.mp4
```

The command prints a JSON result and does not require Flask, Firebase, or AWS.
By default it creates an isolated temporary workspace and removes every generated
frame and artifact when inference finishes. Pass `--work-dir <path>` to retain
the CSV, trajectory, and annotated-video artifacts for inspection.

The default pipeline keeps YOLOv5 in the Python process so its weights are
reused by subsequent jobs. Frames are decoded sequentially and pass through an
in-memory JPEG quality-95 compatibility transform; no per-frame JPEG files are
written. The original subprocess/disk pipeline remains available for regression
comparison:

```powershell
python BackendServer/scripts/test_inference.py docs/demos/sharp-shooter-demo-3.mp4 --pipeline legacy
python BackendServer/scripts/compare_inference.py
```

The comparison command tests every `docs/demos/*.mp4` sample and exits non-zero
if detections, trajectory points, classifications, or final JSON differ.

## AWS asynchronous jobs

The local AWS application layer exposes Lambda-compatible handlers for creating
an upload job, polling its status, and processing S3 notifications delivered
through a Standard SQS queue. DynamoDB processing leases recover jobs after a
timeout or crash, while worker tokens prevent stale invocations from committing
results. It keeps boto3 access behind reusable service modules and calls the same
optimized `predict_video()` entry point used above. This phase does not deploy
resources, and the legacy `/get_prediction` route remains available.

Required runtime settings are `AWS_REGION`, `UPLOAD_BUCKET`, `JOBS_TABLE`,
`PROCESSING_LEASE_SECONDS`, and `MAX_PROCESSING_ATTEMPTS`.
See [`docs/aws-async-jobs.md`](../docs/aws-async-jobs.md) for the exact HTTP
contract, DynamoDB state machine, S3 object layout, duplicate-event behavior,
and local mock-test commands.

Containerize and validate the worker locally before Phase 8 deployment:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_phase7_container.ps1 `
  -SourceBackend "C:\trusted\sharp-shooter\BackendServer"
```

## Train classifiers

Each dataset needs at least five labeled recordings in every class so the fixed
five-fold repeated evaluation can place every class in every validation fold.

```powershell
.venv\Scripts\python landmark_classification.py
.venv\Scripts\python trajectory_classification.py
```

Each command performs five-fold, ten-repeat stratified cross-validation before
refitting the deployable model on all labeled recordings. Aggregate Markdown and
JSON reports plus confusion-matrix CSV files are written to `reports/`. The pose
report highlights bad-form recall and the complementary false-good rate. See
[`docs/model-evaluation.md`](../docs/model-evaluation.md) for the full protocol.

Pose training also stores good-form reference bands for interpretable elbow-angle
and wrist-height features. The inference service uses them to turn a bad-form
prediction into at most two evidence-backed coaching labels. Retrain the pose
model after upgrading an older bundle so these specific labels are available.

The pose model is stored at `data/landmark_data/basketball_shot_model.pkl`, and
the trajectory model is stored at `data/trajectory_data/trajectory_model.pkl`.
The API loads these versioned bundles automatically; until they are available,
the corresponding classification result is reported as `unavailable`.

## LLM coaching

OpenAI API usage is metered; there is no free API text model. The backend uses
`gpt-5.4-nano` as its low-cost default and allows operators to override it with
`OPENAI_MODEL`. Before an API request, raw frame landmarks are reduced locally
to anonymous aggregate angles, offsets, tracking quality, and known limitations.
The LLM receives locally generated coaching labels and may only explain their
named findings, correction goals, and drills; it is not allowed to invent a
posture problem from raw statistics. User-facing coaching is English-only and
contains `Main Findings` plus an action-focused `How to Improve` section. Internal
label codes and redundant generic classifier flags are removed before the request.
Configure `OPENAI_REASONING_EFFORT` as needed. The full prompt and privacy
contract are documented in
[`docs/llm-coaching.md`](../docs/llm-coaching.md).

## Tests

```powershell
.venv\Scripts\python -m unittest discover -s tests -v
```
