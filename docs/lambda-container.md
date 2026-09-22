# Phase 7: Lambda inference container

Phase 7 packages only the queue-driven inference worker into an AWS Lambda
container image. It does not create, update, or deploy any AWS resource. The
existing Flask image remains defined by `BackendServer/Dockerfile`; the worker
image is independently defined by `BackendServer/Dockerfile.lambda-worker`.

## Runtime contract

```text
AWS Lambda Python 3.12 base image (Amazon Linux 2023, linux/amd64)
    ├── CPU-only PyTorch 2.4.1 / torchvision 0.19.1
    ├── bundled YOLOv5 source + basketball weights
    ├── MediaPipe 0.10.21
    ├── OpenCV headless
    ├── scikit-learn 1.6.1 + two private classifier bundles
    └── inference_worker.lambda_handler
```

The production command is the existing SQS handler. S3 download, DynamoDB
lease ownership, worker-token protection, retries, and DLQ-compatible partial
batch failures are therefore unchanged. The local validation handler is enabled
only when `SHARP_SHOOTER_LOCAL_SMOKE=1` and is never the image default.

Python 3.12 / Amazon Linux 2023 is required to preserve MediaPipe 0.10.21 on
Linux x86_64: its Linux wheel requires glibc 2.28 or newer, while the Lambda
Python 3.11 base image uses Amazon Linux 2. AWS currently lists Python 3.12 for
deprecation on October 31, 2028.

## Model integrity and private assets

`lambda-model-manifest.json` fixes the expected byte length and SHA-256 digest
of all three inference models. The Docker build fails if any file is missing or
different. The two `.pkl` files remain ignored by Git and must be copied from a
trusted local deployment source before building:

```powershell
cd BackendServer
python scripts/prepare_lambda_assets.py `
  --source-backend "C:\trusted\sharp-shooter\BackendServer"
python scripts/verify_lambda_assets.py --root .
```

Do not publish classifier bundles in Git, a public registry, build logs, or
untrusted CI artifacts. Phase 8 should push the completed image only to private
ECR.

## One-command local validation

Requirements are Docker Desktop/Engine 25 or later with Buildx and sufficient
disk space for a roughly 3 GiB image. The local run sets a 6 GiB container
memory ceiling; the completed validation ran successfully with a roughly 2 GiB
Docker VM. From `BackendServer` on Windows:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_phase7_container.ps1 `
  -SourceBackend "C:\trusted\sharp-shooter\BackendServer"
```

The script performs these checks without contacting AWS:

1. stages and verifies all model assets;
2. builds one `linux/amd64` Lambda image with provenance disabled;
3. starts the AWS Runtime Interface Emulator with a 6 GiB/4 CPU local limit;
4. invokes every `docs/demos/*.mp4` sample through both Linux legacy and
   optimized paths and requires exact result equality on the target platform;
5. compares classification and coaching decisions with the Windows Phase 5.5
   baseline and separately records every exact numeric difference;
6. invokes the first video again in the same container and requires exact
   cold/warm result equality and YOLO reuse;
7. records image size, dependencies, inference duration, process RSS, and job `/tmp`
   usage in JSON and Markdown reports.

Generated reports:

- `BackendServer/reports/phase-7-container-validation.json`
- `BackendServer/reports/phase-7-container-validation.md`

The 2026-09-22 local run passed all Linux parity and cross-platform decision
checks. The `linux/amd64` image was 2,953.83 MiB. The first optimized invocation
took 60.34 seconds in the handler plus about 4.04 seconds of module import;
later optimized invocations took 42.96 and 22.77 seconds for the other videos,
and 55.70 seconds when repeating the first. YOLO was loaded once and reused.
The measured process RSS high-water mark was about 809 MiB; optimized job files
occupied at most 18.17 MiB in `/tmp`. These are local Docker/RIE measurements,
not AWS Lambda cold-start or billing measurements.

Windows and Linux did not produce byte-identical JSON on any of the three
videos. The classifications, coaching decisions, trajectory confidence, and
total frame counts matched; the MediaPipe-derived shot/release counts and form
confidence differed. For example, demo 1 had 40/11 shot/release frames and
0.849 form confidence on Windows, versus 34/8 and 0.845 on Linux. Identical
decoded video-frame hashes and matching first pose landmarks narrowed the
drift to later MediaPipe tracking. The Linux legacy and optimized paths yielded
exactly equal JSON for all three videos, so the container preserves Phase 5.5
behavior on its actual deployment platform. See the JSON report for every
numeric difference.

## Manual commands

```powershell
cd BackendServer
docker buildx build --platform linux/amd64 --provenance=false `
  -f Dockerfile.lambda-worker -t sharp-shooter-inference:phase7 --load .

docker run --rm -p 9000:8080 --platform linux/amd64 `
  --memory 6g --cpus 4 `
  -v "${PWD}\..\docs\demos:/tmp/videos:ro" `
  -e SHARP_SHOOTER_LOCAL_SMOKE=1 `
  sharp-shooter-inference:phase7 lambda_container_smoke.lambda_handler
```

Invoke it from another terminal:

```powershell
$body = '{"video_path":"/tmp/videos/sharp-shooter-demo-1.mp4"}'
Invoke-RestMethod -Method Post `
  -Uri http://localhost:9000/2015-03-31/functions/function/invocations `
  -ContentType application/json -Body $body
```

## Completion gates

Phase 7 passes only when all of the following are true:

- the image builds for `linux/amd64` and the inspected architecture is `amd64`;
- all three real demo videos return successful, JSON-serializable predictions;
- Linux legacy and optimized Phase 5.5 results match exactly for all videos;
- Windows/Linux classifications and coaching decisions match, with numeric
  drift explicitly reported;
- the first video's cold and warm Linux results match exactly;
- the repeated invocation reports `model_reused=true` and `cold_start=false`;
- the image size, peak RSS, per-job `/tmp` usage, and cold/warm timing are saved;
- the complete backend unit suite and Python compilation pass.

No ECR push, Lambda creation, SQS trigger, IAM change, or other AWS mutation is
part of this phase.
