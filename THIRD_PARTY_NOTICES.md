# Third-party notices

Sharp Shooter incorporates third-party open-source software and model artifacts.
This file records their provenance and preserves the notices required by their
licenses. It does not replace the complete license texts.

## Basketball Detection

- Upstream project: [Stardust87/basketball-detection](https://github.com/Stardust87/basketball-detection)
- Authors named by the upstream project: Michał Szachniewicz and Anna Klimiuk
- Upstream copyright notice: Copyright (c) 2024 Anna Klimiuk
- Upstream project license: MIT
- Local use: the basketball detector weights in
  `BackendServer/models/yolov5s_basketball.pt` and portions of the video
  trajectory-processing pipeline and supporting utilities
- Local checkpoint SHA-256:
  `D3F34F56FF85160B185F3995AB807EE74D8FB752C1558E1F33F3D3B24A9A16D4`

The upstream repository describes the detector as trained on a custom dataset
of privately recorded videos and publishes the checkpoint inside its
MIT-licensed repository. No separate model-specific license was identified.
The upstream MIT notice is reproduced verbatim in
[`LICENSES/MIT-Stardust87.txt`](LICENSES/MIT-Stardust87.txt).

Sharp Shooter does not redistribute the upstream private training videos or
claim authorship of the upstream detector weights.

## Ultralytics YOLOv5

- Upstream project: [ultralytics/yolov5](https://github.com/ultralytics/yolov5)
- License: GNU Affero General Public License v3.0
- Local use: bundled detection, model-loading, and supporting source code under
  `BackendServer/yolov5/`
- Complete license text:
  [`BackendServer/yolov5/LICENSE`](BackendServer/yolov5/LICENSE)

The Basketball Detection upstream repository references Ultralytics YOLOv5
commit `3f02fdee1d8f1a6cf18a24be3438096466367d9f`. The bundled YOLOv5 source and
all modifications to it remain governed by AGPL-3.0.

## Other dependencies

Python and Flutter dependencies are declared in `BackendServer/requirements.txt`
and `mobile/pubspec.yaml`. Each dependency remains governed by its own
license. Their inclusion here does not relicense third-party work under the
Sharp Shooter project license.
