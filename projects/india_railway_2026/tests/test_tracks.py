"""Coverage and geometry checks prevent regional extracts or invented chords slipping in."""
import unittest
import numpy as np
from geography import project
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

    def test_paths_use_track_vertices_and_measures(self):
        geometry, _ = load_tracks()
        vertices = {tuple(p) for line in geometry['network'] for p in line['coordinates']}
        self.assertGreater(len(geometry['routes']), 50)
        for route in geometry['routes']:
            with self.subTest(route=route['id']):
                points = route['coordinates']
                self.assertTrue(all(tuple(p) in vertices for p in points))
                distances = np.asarray(route['distances'])
                self.assertEqual(len(points), len(distances))
                self.assertEqual(distances[0], 0)
                self.assertTrue((np.diff(distances) >= 0).all())
                self.assertEqual(route['stops'][0], 0)
                self.assertEqual(route['stops'][-1], distances[-1])
                chords = np.linalg.norm(np.diff(project(points), axis=0), axis=1)
                self.assertTrue((chords <= np.diff(distances) + .01).all())
