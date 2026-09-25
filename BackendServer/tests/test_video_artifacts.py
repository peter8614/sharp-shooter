"""MP4 conversion contract without invoking a local encoder in unit tests."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from aws_backend.video_artifacts import convert_annotated_video


class VideoArtifactTests(unittest.TestCase):
    def test_conversion_uses_h264_and_rejects_empty_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "annotated.avi"
            target = Path(temporary) / "processed.mp4"
            source.write_bytes(b"avi")

            def run(command, **kwargs):
                self.assertEqual(command[0], "/bin/ffmpeg")
                self.assertIn("libx264", command)
                self.assertIn("yuv420p", command)
                self.assertEqual(kwargs["timeout"], 120)
                target.write_bytes(b"mp4")
                return subprocess.CompletedProcess(command, 0, "", "")

            with (
                patch.dict(sys.modules, {"imageio_ffmpeg": SimpleNamespace(get_ffmpeg_exe=lambda: "/bin/ffmpeg")}),
                patch("aws_backend.video_artifacts.subprocess.run", side_effect=run),
            ):
                self.assertEqual(convert_annotated_video(source, target), target)
                target.write_bytes(b"")
                with patch("aws_backend.video_artifacts.subprocess.run", return_value=subprocess.CompletedProcess([], 0)):
                    with self.assertRaises(RuntimeError):
                        convert_annotated_video(source, target)


if __name__ == "__main__":
    unittest.main()
