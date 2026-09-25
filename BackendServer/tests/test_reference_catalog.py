"""Validation and matching for private NBA reference catalog."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from NBA_compare import LANDMARK_NAMES
from aws_backend import reference_catalog
from scripts.build_reference_catalog import build_catalog, transcode_reference_video


def variance(value: float) -> dict:
    return {name: [value, value, value] for name in LANDMARK_NAMES}


class ReferenceCatalogTests(unittest.TestCase):
    def test_catalog_builds_only_samples_with_matching_video(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data = root / "NBA Data"
            videos = root / "NBA Players"
            data.mkdir()
            videos.mkdir()
            (data / "Example Player_1_variance.txt").write_text(json.dumps(variance(1.0)))
            (data / "Other Player_1_variance.txt").write_text(json.dumps(variance(2.0)))
            (videos / "Example Player_1.mp4").write_bytes(b"example video")
            def fake_transcode(source, destination, _ffmpeg):
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(b"h264 version of " + source.read_bytes())
                return destination

            with patch("scripts.build_reference_catalog.transcode_reference_video", side_effect=fake_transcode):
                catalog, uploads, skipped = build_catalog(data, videos, root / "out", "ffmpeg")
            self.assertEqual(len(catalog["entries"]), 1)
            self.assertEqual(catalog["entries"][0]["player_name"], "Example Player")
            self.assertEqual(skipped, ["Other Player_1"])
            self.assertEqual(len(uploads), 1)
            self.assertTrue(uploads[0]["key"].startswith("references/videos/example-player-1-"))
            self.assertEqual(Path(uploads[0]["source"]).read_bytes(), b"h264 version of example video")
            parsed = reference_catalog.parse_catalog(json.dumps(catalog).encode())
            self.assertEqual(parsed[0].reference_id, "example-player-1")

    def test_transcoding_uses_phone_compatible_h264(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.mp4"
            output = root / "output.mp4"
            source.write_bytes(b"mpeg4 video")

            def fake_run(command, **_kwargs):
                output.write_bytes(b"h264 video")
                return type("Result", (), {"returncode": 0})()

            with patch("scripts.build_reference_catalog.subprocess.run", side_effect=fake_run) as run:
                self.assertEqual(transcode_reference_video(source, output, "ffmpeg"), output)
            command = run.call_args.args[0]
            for required in ("libx264", "baseline", "yuv420p", "+faststart", "-an"):
                self.assertIn(required, command)

    def test_closest_reference_reuses_normalized_variance_score(self):
        document = {"version": 1, "entries": [
            {"id": "same-1", "player_name": "Same", "variance": variance(1.0),
             "video_key": "references/videos/same-1-abc.mp4"},
            {"id": "other-1", "player_name": "Other", "variance": variance(2.0),
             "video_key": "references/videos/other-1-def.mp4"},
        ]}
        entries = reference_catalog.parse_catalog(json.dumps(document).encode())
        with patch.object(reference_catalog, "find_landmark_variances", return_value=variance(1.0)):
            closest, score = reference_catalog.closest_reference("unused.csv", entries)
        self.assertEqual(closest.player_name, "Same")
        self.assertEqual(score, 100.0)

    def test_catalog_rejects_non_reference_video_key(self):
        document = {"version": 1, "entries": [
            {"id": "sample-1", "player_name": "Sample", "variance": variance(1.0),
             "video_key": "uploads/another-user/input.mp4"}
        ]}
        with self.assertRaises(ValueError):
            reference_catalog.parse_catalog(json.dumps(document).encode())


if __name__ == "__main__":
    unittest.main()
