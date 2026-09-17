# Phase 5.5 inference optimization benchmark

Measured locally on CPU with Python 3.11, PyTorch 2.4.1, and the existing
`yolov5s_basketball.pt` weights. The optimized implementation retained the
legacy 640-pixel input size, 0.25 confidence threshold, 0.45 IoU threshold,
1,000 maximum detections, FP32 inference, NMS behavior, and JPEG quality-95
pixel compatibility transform.

## Regression result

| Check | Result |
| --- | ---: |
| Videos tested | 3 |
| Final JSON matches | 3/3 |
| Pose classification matches | 3/3 |
| Trajectory classification matches | 3/3 |
| Detection-set matches | 3/3 |
| Trajectory-coordinate matches | 3/3 |

Across all videos, 1,491 post-NMS detections were compared. Normalized bounding
boxes and confidence values matched exactly after reproducing the legacy `%g`
serialization boundary in memory.

## Performance result

| Video | Frames | Legacy total | Optimized total | Legacy peak temp | Optimized peak temp |
| --- | ---: | ---: | ---: | ---: | ---: |
| `sharp-shooter-demo-1.mp4` | 471 | 56.87 s | 45.30 s | 163.26 MiB | 15.03 MiB |
| `sharp-shooter-demo-2.mp4` | 342 | 42.96 s | 32.44 s | 131.86 MiB | 11.31 MiB |
| `sharp-shooter-demo-3.mp4` | 195 | 26.44 s | 18.25 s | 57.71 MiB | 4.33 MiB |

Average total runtime fell from 42.09 seconds to 32.00 seconds (24.0%). Average
temporary disk usage fell from 117.61 MiB to 10.22 MiB (91.3%). The optimized
figures conservatively include detection diagnostics used by the comparison;
normal production inference does not write that diagnostics file.

| Model-loading measurement | Time |
| --- | ---: |
| Legacy average model construction | 1.215 s per job |
| Optimized initial construction and warmup | 0.636 s |
| Optimized second invocation | 0.000 s |

On the 471-frame sample, optimized cold and warm total times were 45.30 and
44.61 seconds. The second invocation reused the exact same detector object.

## Compatibility notes

- The legacy subprocess and JPEG-frame implementation remains selectable with
  `--pipeline legacy` for future regression checks.
- The optimized annotated AVI is written directly from rendered memory frames.
  Its pixels are visually equivalent but the file is not binary-identical to
  the legacy AVI, which performed another JPEG encode/decode before video write.
- MediaPipe and YOLO still decode the source video in separate passes. Combining
  them is intentionally deferred because it would broaden the proven change.
- The bundled detector exposes the basketball class; it has no separate basket
  or hoop class to compare.

Machine-readable measurements are stored in `phase-5.5-benchmark.json`.
