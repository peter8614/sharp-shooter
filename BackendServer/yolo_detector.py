"""In-process, warm-reusable adapter around the bundled YOLOv5 detector."""

from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np


BACKEND_DIR = Path(__file__).resolve().parent
YOLO_ROOT = BACKEND_DIR / "yolov5"
DEFAULT_WEIGHTS = BACKEND_DIR / "models" / "yolov5s_basketball.pt"
DEFAULT_DATA = YOLO_ROOT / "data" / "coco128.yaml"

# Ultralytics creates settings and Matplotlib creates a font cache on import.
# Lambda's application directory is read-only, so keep both below /tmp.
RUNTIME_CACHE = Path(tempfile.gettempdir()) / "sharp-shooter-runtime"
RUNTIME_CACHE.mkdir(parents=True, exist_ok=True)
(RUNTIME_CACHE / ".ultralytics").mkdir(parents=True, exist_ok=True)
(RUNTIME_CACHE / ".matplotlib").mkdir(parents=True, exist_ok=True)
os.environ.setdefault("YOLO_CONFIG_DIR", str(RUNTIME_CACHE / ".ultralytics"))
os.environ.setdefault("MPLCONFIGDIR", str(RUNTIME_CACHE / ".matplotlib"))

_runtime = None
_runtime_lock = threading.Lock()


def _get_yolo_runtime():
    """Import PyTorch and vendored YOLO only when inference is first requested."""
    global _runtime
    with _runtime_lock:
        if _runtime is None:
            # The vendored YOLOv5 code uses top-level `models` and `utils` imports.
            if str(YOLO_ROOT) not in sys.path:
                sys.path.insert(0, str(YOLO_ROOT))
            import torch
            from models.common import DetectMultiBackend
            from utils.augmentations import letterbox
            from utils.general import (
                check_img_size,
                non_max_suppression,
                scale_boxes,
                xyxy2xywh,
            )
            from utils.torch_utils import select_device

            _runtime = SimpleNamespace(
                torch=torch,
                DetectMultiBackend=DetectMultiBackend,
                letterbox=letterbox,
                check_img_size=check_img_size,
                non_max_suppression=non_max_suppression,
                scale_boxes=scale_boxes,
                xyxy2xywh=xyxy2xywh,
                select_device=select_device,
            )
    return _runtime


class YoloDetector:
    """YOLOv5 detector with the legacy detect.py settings frozen in one object."""

    image_size = (640, 640)
    confidence_threshold = 0.25
    iou_threshold = 0.45
    maximum_detections = 1000
    classes = None
    agnostic_nms = False
    augment = False
    half = False
    dnn = False

    def __init__(
        self,
        weights_path: str | Path = DEFAULT_WEIGHTS,
        device: str = "cpu",
    ) -> None:
        self.weights_path = Path(weights_path).expanduser().resolve()
        if not self.weights_path.is_file():
            raise FileNotFoundError(f"Missing basketball weights: {self.weights_path}")

        self._runtime = _get_yolo_runtime()
        started = time.perf_counter()
        self.device_name = str(device)
        self.device = self._runtime.select_device(self.device_name)
        self.model = self._runtime.DetectMultiBackend(
            self.weights_path,
            device=self.device,
            dnn=self.dnn,
            data=DEFAULT_DATA,
            fp16=self.half,
        )
        self.stride = self.model.stride
        self.names = self.model.names
        self.pt = self.model.pt
        self.image_size = self._runtime.check_img_size(
            self.image_size, s=self.stride
        )
        self.model.warmup(
            imgsz=(1 if self.pt or self.model.triton else 1, 3, *self.image_size)
        )
        self.load_seconds = time.perf_counter() - started
        self._inference_lock = threading.Lock()

    def detect(self, frame: np.ndarray) -> list[dict]:
        """Return post-NMS detections for one BGR frame."""
        if frame is None or frame.ndim != 3 or frame.shape[2] != 3:
            raise ValueError("YOLO input must be one BGR image")

        with self._runtime.torch.inference_mode():
            return self._detect(frame)

    def _detect(self, frame: np.ndarray) -> list[dict]:
        """Run one inference while the caller holds PyTorch inference mode."""
        torch = self._runtime.torch

        original = frame
        image = self._runtime.letterbox(
            original,
            self.image_size,
            stride=self.stride,
            auto=self.pt,
        )[0]
        image = image.transpose((2, 0, 1))[::-1]
        image = np.ascontiguousarray(image)
        tensor = torch.from_numpy(image).to(self.model.device)
        tensor = tensor.half() if self.model.fp16 else tensor.float()
        tensor /= 255
        if tensor.ndim == 3:
            tensor = tensor[None]

        with self._inference_lock:
            prediction = self.model(
                tensor,
                augment=self.augment,
                visualize=False,
            )
            prediction = self._runtime.non_max_suppression(
                prediction,
                self.confidence_threshold,
                self.iou_threshold,
                self.classes,
                self.agnostic_nms,
                max_det=self.maximum_detections,
            )

        detections = prediction[0]
        if len(detections):
            detections[:, :4] = self._runtime.scale_boxes(
                tensor.shape[2:], detections[:, :4], original.shape
            ).round()

        height, width = original.shape[:2]
        normalization = torch.tensor([width, height, width, height])
        results: list[dict] = []
        for *xyxy, confidence, class_id in reversed(detections):
            coordinates = torch.tensor(
                [float(value.detach().cpu()) for value in xyxy]
            ).view(1, 4)
            relative = (
                self._runtime.xyxy2xywh(coordinates) / normalization
            ).view(-1).tolist()
            # Legacy detect.py persisted values with `%g` before trajectory
            # rendering. Reapply that six-significant-digit boundary in memory
            # so integer pixel centers remain bit-for-bit compatible.
            legacy_confidence = float(f"{float(confidence.detach().cpu()):g}")
            legacy_relative = [float(f"{value:g}") for value in relative]
            results.append(
                {
                    "class_id": int(class_id.detach().cpu()),
                    "confidence": legacy_confidence,
                    "xyxy": [int(value) for value in coordinates.view(-1).tolist()],
                    "relative_coordinates": {
                        "center_x": legacy_relative[0],
                        "center_y": legacy_relative[1],
                        "width": legacy_relative[2],
                        "height": legacy_relative[3],
                    },
                }
            )
        return results


_detectors: dict[tuple[str, str], YoloDetector] = {}
_detector_lock = threading.Lock()


def get_detector(
    weights_path: str | Path = DEFAULT_WEIGHTS,
    device: str = "cpu",
) -> YoloDetector:
    """Return one detector per weights/device pair for warm runtime reuse."""
    key = (str(Path(weights_path).expanduser().resolve()), str(device))
    with _detector_lock:
        detector = _detectors.get(key)
        if detector is None:
            detector = YoloDetector(key[0], key[1])
            _detectors[key] = detector
        return detector


def detector_is_cached(
    weights_path: str | Path = DEFAULT_WEIGHTS,
    device: str = "cpu",
) -> bool:
    key = (str(Path(weights_path).expanduser().resolve()), str(device))
    with _detector_lock:
        return key in _detectors


def clear_detector_cache() -> None:
    """Release singleton references for tests and controlled benchmarks."""
    with _detector_lock:
        _detectors.clear()
