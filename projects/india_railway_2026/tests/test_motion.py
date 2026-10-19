"""Presentation smoothing preserves positions, canvas size and observation gaps."""
import unittest
from model import motion_sample
from model import position


class MotionTests(unittest.TestCase):
    def setUp(self):
        self.segments = [
            {"start": 0, "end": 1000, "from": 0, "to": 100, "kind": "travel"},
            {"start": 1000, "end": 1240, "from": 100, "to": 100, "kind": "dwell"},
            {"start": 1240, "end": 2240, "from": 100, "to": 200, "kind": "travel"},
        ]

    def test_fades_only_at_visibility_boundaries(self):
        self.assertEqual(motion_sample(self.segments, 0, 0)[2], 0)
        self.assertAlmostEqual(motion_sample(self.segments, 0, 120)[2], .5)
        for index, second in ((0, 500), (1, 1000), (2, 1240)):
            self.assertEqual(motion_sample(self.segments, index, second)[2], 1)
        self.assertLess(motion_sample(self.segments, 2, 2239)[2], .001)

    def test_trail_survives_station_and_retreats_gradually(self):
        before, point, _ = motion_sample(self.segments, 0, 999)
        after, stopped, _ = motion_sample(self.segments, 1, 1001)
        self.assertAlmostEqual(after-before, .2)
        self.assertEqual(stopped, 100)
        self.assertGreater(stopped-after, 40)
        self.assertAlmostEqual(motion_sample(self.segments, 2, 1241)[0], 82.1)

    def test_no_trail_or_opacity_crosses_a_gap(self):
        self.segments[2].update(start=1300, end=2300)
        tail, point, opacity = motion_sample(self.segments, 2, 1300)
        self.assertEqual((tail, point, opacity), (100, 100, 0))
        self.segments[2].update(start=1240, end=2240, **{"from": 110})
        self.assertEqual(motion_sample(self.segments, 2, 1240), (110, 110, 0))

    def test_display_positions_match_model(self):
        journey = {"segments": self.segments, "route_pixels": [[0, 0], [200, 0]], "distances": [0, 200]}
        for index, second in ((0, 120), (1, 1100), (2, 1500)):
            self.assertAlmostEqual(motion_sample(self.segments, index, second)[1], position(journey, second)[0])
