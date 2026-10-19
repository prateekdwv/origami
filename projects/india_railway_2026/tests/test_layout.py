"""Exact graph peaks and full-boundary alignment in the compact portrait layout."""
import unittest
import numpy as np

from design import display_points, traffic_series
from geography import official_map, pixels


class LayoutTests(unittest.TestCase):
    def test_brief_peak_between_five_minute_samples_is_retained(self):
        journeys = [{"segments": [{"start": 0, "end": 86400}]},
                    {"segments": [{"start": 121, "end": 122}]}]
        times, counts = traffic_series(journeys)
        self.assertEqual(int(max(counts)), 2)
        self.assertEqual(times[np.argmax(counts)], 121)
        self.assertEqual(counts[np.searchsorted(times, 300, side="right")-1], 1)
        self.assertEqual(counts[-1], 0)

    def test_simultaneous_travel_and_dwell_boundaries_do_not_double_count(self):
        journeys = [{"segments": [{"start": 0, "end": 100}, {"start": 100, "end": 200}]},
                    {"segments": [{"start": 200, "end": 300}]}]
        times, counts = traffic_series(journeys)
        np.testing.assert_array_equal(times, [0, 100, 200, 300, 86400])
        np.testing.assert_array_equal(counts, [1, 1, 1, 0, 0])

    def test_entire_unsimplified_boundary_fits_between_header_and_legend(self):
        original = pixels(np.concatenate(official_map()[2]))
        frozen = original.copy()
        transformed = display_points(original)
        self.assertTrue((transformed[:, 0] >= 39.9).all())
        self.assertTrue((transformed[:, 0] <= 1040.1).all())
        self.assertTrue((transformed[:, 1] >= 190).all())
        self.assertTrue((transformed[:, 1] <= 1380).all())
        np.testing.assert_array_equal(original, frozen)
        # A uniform display scale preserves bearings and shape proportions.
        scale = np.linalg.norm(np.diff(transformed[:2], axis=0))/np.linalg.norm(np.diff(original[:2], axis=0))
        self.assertGreater(scale, 1)
