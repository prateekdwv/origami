"""Coverage and geometry checks prevent regional extracts or invented chords slipping in."""
import unittest
import numpy as np
from tracks import load_tracks


class TrackTests(unittest.TestCase):
    def test_national_extent_and_integrity(self):
        geometry, provenance = load_tracks()
        self.assertGreater(len(geometry['network']), 90000)
        points = np.concatenate([line['coordinates'] for line in geometry['network']])
        self.assertTrue(np.isfinite(points).all())
        west, south = points.min(axis=0)
        east, north = points.max(axis=0)
        self.assertLess(west, 70)
        self.assertGreater(east, 94)
        self.assertLess(south, 9)
        self.assertGreater(north, 33)
        self.assertEqual(provenance['license'], 'ODbL-1.0')

    def test_display_simplification_retains_endpoints_without_adding_vertices(self):
        from prepare_tracks import simplify
        points = np.array([[0., 0.], [100., 1.], [200., 0.], [200., 400.]])
        chosen = simplify(points, tolerance=10)
        self.assertEqual(chosen, [0, 2, 3])
