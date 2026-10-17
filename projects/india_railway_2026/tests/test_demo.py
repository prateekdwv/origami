"""A visual preview must stay populated, diverse, deterministic and isolated."""
import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
from demo import build_demo
from design import FrameRenderer, base_image
from model import active_counts, position
from replay import load_prepared, validate
from settings import CATEGORIES

class DemoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = build_demo()
    def test_populated_all_day_and_six_categories(self):
        validate(self.data)
        self.assertGreater(len(self.data["journeys"]), 100)
        self.assertGreaterEqual(min(self.data["activity"][:-1]), 20)
        self.assertGreater(max(self.data["activity"])-min(self.data["activity"][:-1]), 20)
        self.assertEqual({j["category"] for j in self.data["journeys"]}, set(CATEGORIES))
        self.assertTrue(all(active_counts(self.data["journeys"], 12*3600)[c] for c in CATEGORIES))
    def test_moves_and_pauses(self):
        moving = 0
        for j in self.data["journeys"]:
            a, b = position(j, 12*3600), position(j, 12*3600+120)
            if a is not None and b is not None and np.linalg.norm(a-b) > .1:
                moving += 1
        self.assertGreater(moving, 20)
        self.assertTrue(any(s["kind"] == "dwell" for j in self.data["journeys"] for s in j["segments"]))
    def test_deterministic_and_fiction_explicit(self):
        self.assertEqual(self.data, build_demo())
        self.assertTrue(self.data["synthetic_test_only"])
        self.assertIn("invented", self.data["basis"])
        self.assertTrue(all(j["id"].startswith("DEMO-") for j in self.data["journeys"]))
    def test_production_loader_rejects_demo(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            (directory / "prepared.json").write_text(json.dumps(self.data))
            with self.assertRaisesRegex(RuntimeError, "Synthetic previews"):
                load_prepared(directory)
    def test_light_map_and_visible_tracks(self):
        bare, busy = base_image(), base_image(self.data)
        self.assertGreater(min(bare.getpixel((0, 0))), 230)
        delta = np.abs(np.asarray(bare, dtype=np.int16)-np.asarray(busy, dtype=np.int16))
        self.assertGreater(np.count_nonzero(delta[450:1350].max(axis=2) > 25), 10000)
        # Two daytime frames must differ visibly, not merely advance a blank clock.
        compose = FrameRenderer(self.data)
        one = np.asarray(compose(20), dtype=np.int16)
        two = np.asarray(compose(21), dtype=np.int16)
        self.assertGreater(np.count_nonzero(np.abs(one-two)[450:1350].max(axis=2) > 25), 5000)

if __name__ == "__main__":
    unittest.main()
