"""Validate single-stroke geometry and distance parameterization; no extra deps."""

import unittest

import numpy as np
from scipy.spatial import cKDTree

from artwork import ArcLength, evaluate, load_curves
from motion import CameraMotion, FPS, OPENING, DRAWING, PULLBACK, TOTAL, WIDTH, ZOOM, FULL_CENTER, SAFE_BOX_HALF_SIZE


def overlap_runs(curves):
    """Find sustained near-coincident strokes, excluding crossings and neighbors.

    Sample every 0.35 output pixels. A candidate must stay within 0.7 pixels,
    have parallel tangents, and extend for at least 10 pixels of traveled path.
    This is a numerical screen, not a proof against arbitrary geometric overlap.
    """
    arc = ArcLength(curves)
    progress = np.linspace(0, 1, int(arc.length / 0.35) + 1)
    points = arc.points(progress)
    tangents = np.gradient(points, axis=0)
    tangents /= np.maximum(np.linalg.norm(tangents, axis=1, keepdims=True), 1e-12)
    pairs = cKDTree(points).query_pairs(0.7, output_type="ndarray")
    pairs = pairs[np.abs(pairs[:, 1] - pairs[:, 0]) > 40]
    parallel = np.abs((tangents[pairs[:, 0]] * tangents[pairs[:, 1]]).sum(axis=1)) > 0.995
    pairs = pairs[parallel]
    marked = np.zeros(len(points), dtype=bool)
    marked[pairs.ravel()] = True
    changes = np.diff(np.r_[False, marked, False].astype(int))
    runs = list(zip(np.flatnonzero(changes == 1), np.flatnonzero(changes == -1)))
    result = []
    for start, stop in runs:
        if (stop - start) * arc.length / (len(points) - 1) >= 10:
            result.append({
                "curve": int(arc.parameter(progress[start]) * len(curves)),
                "end_curve": int(arc.parameter(progress[stop - 1]) * len(curves)),
                "length_px": round((stop-start) * arc.length / (len(points)-1), 2),
            })
    return result


class ArtworkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.curves = load_curves()
        cls.arc = ArcLength(cls.curves)

    def test_single_open_connected_path(self):
        self.assertTrue(np.array_equal(self.curves[:-1, 3], self.curves[1:, 0]))
        self.assertFalse(np.allclose(self.curves[0, 0], self.curves[-1, -1]))
        self.assertTrue(np.isfinite(self.curves).all())

    def test_no_duplicate_or_reversed_cubics(self):
        seen = set()
        for curve in self.curves:
            forward = tuple(curve.ravel())
            reverse = tuple(curve[::-1].ravel())
            self.assertNotIn(forward, seen)
            self.assertNotIn(reverse, seen)
            seen.add(forward)

    def test_no_sustained_retracing(self):
        self.assertEqual(overlap_runs(self.curves), [])

    def test_overlap_detector_catches_reversed_curve(self):
        curve = np.array([[0., 0.], [10., 0.], [20., 0.], [30., 0.]])
        self.assertTrue(overlap_runs(np.array([curve, curve[::-1]])))

    def test_constant_speed_and_endpoints(self):
        reference = ArcLength(self.curves, samples_per_curve=2048)
        progress = np.linspace(0, 1, round(DRAWING * FPS) + 1)
        parameters = self.arc.parameter(progress)
        actual_distances = np.interp(parameters, reference.parameters, reference.distances)
        expected_step = reference.length / (DRAWING * FPS)
        self.assertLess(np.max(np.abs(np.diff(actual_distances) - expected_step)), 0.03)
        self.assertTrue(np.all(np.diff(parameters) > 0))
        np.testing.assert_allclose(self.arc.points(0), self.curves[0, 0])
        np.testing.assert_allclose(self.arc.points(1), self.curves[-1, -1])

    def test_artwork_fits_portrait_box(self):
        points = evaluate(self.curves[:, None], np.linspace(0, 1, 257)[None, :])
        self.assertTrue((points >= [60, 375]).all())
        self.assertTrue((points <= [950, 1425]).all())

    def test_each_animation_frame_is_one_contiguous_prefix(self):
        from manim import VMobject
        original = VMobject()
        original.set_points(np.pad(self.curves.reshape(-1, 2), ((0, 0), (0, 1))))
        growing = original.copy()
        for progress in np.linspace(0, 1, round(DRAWING * FPS) + 1):
            growing.pointwise_become_partial(original, 0, self.arc.parameter(progress))
            points = growing.points.reshape(-1, 4, 3)
            np.testing.assert_allclose(points[:-1, 3], points[1:, 0], atol=1e-9)
            np.testing.assert_allclose(points[:-1], original.points[:4*(len(points)-1)].reshape(-1, 4, 3))
            np.testing.assert_allclose(points[-1, -1, :2], self.arc.points(progress), atol=1e-8)

    def test_camera_keeps_tip_in_central_half(self):
        motion = CameraMotion(self.arc)
        tips = self.arc.points(motion.times / DRAWING)
        self.assertTrue((np.abs(tips - motion.centers) <= [WIDTH/ZOOM/4, 1920/ZOOM/4]).all())
        np.testing.assert_allclose(motion.pose(0)[0], tips[0])

    def test_camera_guide_moves_only_after_tip_leaves_safe_box(self):
        motion = CameraMotion(self.arc)
        tips = self.arc.points(motion.times / DRAWING)
        outside = (np.abs(tips[1:] - motion.guides[:-1]) > SAFE_BOX_HALF_SIZE).any(axis=1)
        moved = (np.abs(np.diff(motion.guides, axis=0)) > 1e-12).any(axis=1)
        np.testing.assert_array_equal(moved, outside)

    def test_camera_pullback_continuity_and_final_pose(self):
        motion = CameraMotion(self.arc)
        start = OPENING + DRAWING
        finish = start + PULLBACK
        epsilon = 1e-6
        np.testing.assert_allclose(motion.pose(start-epsilon)[0], motion.pose(start+epsilon)[0], atol=0.002)
        incoming = (motion.pose(start)[0] - motion.pose(start-epsilon)[0]) / epsilon
        outgoing = (motion.pose(start+epsilon)[0] - motion.pose(start)[0]) / epsilon
        np.testing.assert_allclose(incoming, outgoing, atol=0.002)
        widths = [motion.pose(t)[1] for t in np.linspace(start, finish, 301)]
        self.assertTrue((np.diff(widths) > 0).all())
        self.assertEqual(widths[0], WIDTH/ZOOM)
        self.assertEqual(widths[-1], WIDTH)
        np.testing.assert_allclose(motion.pose(finish-epsilon)[0], FULL_CENTER, atol=1e-7)
        for t in np.linspace(finish, TOTAL, 76):
            np.testing.assert_array_equal(motion.pose(t)[0], FULL_CENTER)
            self.assertEqual(motion.pose(t)[1], WIDTH)


if __name__ == "__main__":
    unittest.main()
