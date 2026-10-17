"""Export orchestration and audit failures, using in-memory frames; no encoding."""
import json
from fractions import Fraction
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image
import replay
from demo import build_demo
from design import FrameRenderer


class AuditTests(unittest.TestCase):
    def test_decoder_seeks_exact_frames_and_closes_container(self):
        frame = lambda i: SimpleNamespace(time=Fraction(i, 30), to_ndarray=lambda **kw: i)
        container = unittest.mock.MagicMock()
        container.streams.video = [SimpleNamespace(time_base=Fraction(1, 30))]
        container.decode.side_effect = [iter([frame(0), frame(1)]), iter([frame(3), frame(4)])]
        with patch.object(replay.av, "open") as opened:
            opened.return_value.__enter__.return_value = container
            self.assertEqual(list(replay.decoded_frames("fixture", [1, 4], False)), [(1, 1), (4, 4)])
            self.assertEqual(container.seek.call_args_list[1].args, (4,))
            opened.return_value.__exit__.assert_called_once()
        container.decode.side_effect = [iter([frame(2)])]
        with patch.object(replay.av, "open") as opened:
            opened.return_value.__enter__.return_value = container
            with self.assertRaisesRegex(RuntimeError, "Missing video frame"):
                list(replay.decoded_frames("fixture", [1], False))

    def test_sample_boundaries_and_peak(self):
        data = build_demo()
        indices = replay.audit_indices(data)
        self.assertEqual(indices, sorted(set(indices)))
        self.assertTrue({0, 89, 90, 1709, 1710, 1799} <= set(indices))
        self.assertLessEqual(len(indices), 18)
        self.assertEqual(replay.audit_indices(data, True), list(range(1800)))

    def audit(self, full=False, metadata=None, truncate=False, corrupt=False):
        data = {"activity": [0, 2, 0], "coverage": {}, "journeys": []}
        indices = replay.audit_indices(data, full)
        stream = {"codec_type": "video", "width": 18, "height": 320, "codec_name": "h264",
                  "pix_fmt": "yuv420p", "avg_frame_rate": "30/1", "nb_frames": "1800", "nb_read_frames": "1800"}
        stream.update(metadata or {})
        info = {"streams": [stream], "format": {"duration": "60"}}
        frame = np.full((320, 18, 3), 255 if corrupt else 0, dtype=np.uint8)
        def decode(*args):
            for index in indices[:-1] if truncate else indices:
                yield index, frame
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            video = directory / "fixture.bin"
            video.write_bytes(b"unit fixture, not encoded video")
            with patch.multiple(replay, WIDTH=18, HEIGHT=320), \
                 patch.object(replay.subprocess, "run", return_value=SimpleNamespace(stdout=json.dumps(info))) as probe, \
                 patch.object(replay, "decoded_frames", decode), \
                 patch.object(replay, "boundary_hash", return_value="test"), \
                 patch.object(replay, "official_map", return_value=(None, None, [])), \
                 patch.object(replay, "FrameRenderer") as renderer:
                renderer.return_value.return_value = Image.new("RGB", (18, 320))
                renderer.return_value.routes = []
                try:
                    report = replay.verify(data, video, directory, full=full)
                except RuntimeError:
                    self.assertFalse(json.loads((directory / "verification.json").read_text())["passed"])
                    raise
                self.assertEqual("-count_frames" in probe.call_args.args[0], full)
                return report

    def test_quick_report_never_claims_full_audit(self):
        report = self.audit()
        self.assertTrue(report["passed"])
        self.assertFalse(report["all_frames_compared"])
        self.assertEqual(report["mode"], "quick")
        self.assertLessEqual(report["frames_compared"], 18)

    def test_full_compares_every_frame(self):
        report = self.audit(full=True)
        self.assertTrue(report["all_frames_compared"])
        self.assertEqual(report["frames_compared"], 1800)

    def test_metadata_truncation_and_pixel_errors_fail(self):
        for options in ({"metadata": {"nb_frames": "1799"}}, {"truncate": True}, {"corrupt": True}):
            with self.subTest(options=options), self.assertRaises(RuntimeError):
                self.audit(**options)

    def test_static_holds_are_cached_and_dataset_unchanged(self):
        data = build_demo()
        original = json.dumps(data, sort_keys=True)
        compose = FrameRenderer(data)
        with patch.object(compose, "draw", wraps=compose.draw) as draw:
            self.assertIs(compose(0), compose(2.9))
            self.assertIs(compose(57), compose(59.9))
            self.assertEqual(draw.call_count, 2)
        self.assertEqual(json.dumps(data, sort_keys=True), original)

    def test_shared_manim_helper_passes_dataset_and_restores_config(self):
        import scene
        data = {"synthetic_test_only": True}
        original = scene.config.copy()
        with patch.object(scene, "deny_network"), patch.object(scene, "IndiaRailway2026") as animation:
            scene.render_video(data, Path("unused-test-output"), True, "SYNTHETIC_TEST")
            animation.assert_called_once_with(dataset=data)
            animation.return_value.render.assert_called_once_with()
        self.assertEqual(dict(scene.config), dict(original))
