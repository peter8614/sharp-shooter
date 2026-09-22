# Phase 7 Lambda container validation

Generated: 2026-09-22T19:34:02.596804+00:00

- Result: PASS
- Image: `sha256:d1fd273032e222c40997d459410773406e2ad0d25e30e21e9292f73b3d855724`
- Platform: `amd64/linux`
- Image size: 2953.83 MiB
- Warm YOLO reuse: True

| Video | Purpose | Inference seconds | Peak RSS MiB | Job /tmp MiB | YOLO reused | Linux exact parity | Cross-platform decisions | Windows exact parity |
| --- | --- | ---: | ---: | ---: | --- | --- | --- | --- |
| sharp-shooter-demo-1.mp4 | parity | 60.336052 | 750.23 | 18.17 | False | True | True | False |
| sharp-shooter-demo-2.mp4 | parity | 42.958485 | 808.61 | 13.94 | True | True | True | False |
| sharp-shooter-demo-3.mp4 | parity | 22.768113 | 808.61 | 5.05 | True | True | True | False |
| sharp-shooter-demo-1.mp4 | warm-runtime-reuse | 55.704514 | 808.61 | 18.17 | True | True | True | False |

## Cross-platform compatibility notes

Windows/Linux numeric difference: sharp-shooter-demo-1.mp4
Windows/Linux numeric difference: sharp-shooter-demo-2.mp4
Windows/Linux numeric difference: sharp-shooter-demo-3.mp4
Windows/Linux numeric difference on warm run: sharp-shooter-demo-1.mp4

## Failures

None.
