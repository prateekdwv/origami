"""Pixel checks on the actual native collection renderer, not a second drawing path."""
import unittest
import numpy as np
from matplotlib.colors import to_rgb
from design import FrameRenderer
from settings import INK, WIDTH, HEIGHT
from tests.fixtures import timetable


class RendererTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.renderer = FrameRenderer(timetable())

    def setUp(self):
        self.points = self.renderer.routes[0][1]
        self.original = self.points.copy()

    def tearDown(self):
        self.points[:] = self.original

    def test_fractional_positions_change_pixels_and_use_the_dataset_palette(self):
        self.points[:] = [540., 500.]
        a = np.asarray(self.renderer(30))
        self.points[:, 0] += .2
        b = np.asarray(self.renderer(30))
        self.assertEqual(a.shape, (HEIGHT, WIDTH, 3))
        self.assertTrue(np.any(a != b))
        np.testing.assert_array_equal(self.renderer.dots.get_offsets(), [[540.2, 500.]])
        np.testing.assert_allclose(self.renderer.dots.get_facecolors()[0], [*to_rgb('#0072B2'), 1])

    def test_city_glyphs_stay_in_front_of_a_train_and_halo(self):
        # Put a train through the centre of Delhi's label; every opaque ink pixel
        # in the static glyphs must survive the train overlay exactly.
        baseline = np.asarray(self.renderer(0))
        label = next(label for label in self.renderer.labels if label.get_text() == 'Delhi')
        box = label.get_window_extent(self.renderer.canvas.get_renderer())
        x0, x1 = int(box.x0), int(np.ceil(box.x1))
        y0, y1 = HEIGHT-int(np.ceil(box.y1)), HEIGHT-int(box.y0)
        self.points[:] = [(x0+x1)/2, (y0+y1)/2]
        actual = np.asarray(self.renderer(30))
        ink = np.rint(np.array(to_rgb(INK))*255).astype(np.uint8)
        mask = np.all(baseline[y0:y1, x0:x1] == ink, axis=2)
        self.assertGreater(int(mask.sum()), 30)
        np.testing.assert_array_equal(actual[y0:y1, x0:x1][mask], baseline[y0:y1, x0:x1][mask])

    def test_zero_opacity_at_the_day_start_has_no_visible_marker(self):
        np.testing.assert_array_equal(np.asarray(self.renderer(0)), np.asarray(self.renderer(3)))
