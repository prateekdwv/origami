"""Render with the project-local manim.cfg; see README.md for exact commands."""

from pathlib import Path
import sys

import manimpango
import numpy as np
from manim import Animation, CapStyleType, LineJointType, MovingCameraScene, Polygon, Text, UP, UpdateFromAlphaFunc, VGroup, VMobject, config, linear
from scipy.spatial import Delaunay

# Manim loads scene files by filename, so imports must work from the repo root too.
PROJECT = Path(__file__).resolve().parent
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))
from artwork import ArcLength, HEIGHT, INK, STROKE_PX, WIDTH, load_curves
from motion import CameraMotion, OPENING, DRAWING, PULLBACK, HOLD


class ContinuousInk(Animation):
    """Reveal just one connected prefix, at constant traveled-distance speed."""

    def __init__(self, mobject, arc, **kwargs):
        self.arc = arc
        super().__init__(mobject, rate_func=linear, **kwargs)

    def interpolate_mobject(self, alpha):
        self.mobject.pointwise_become_partial(
            self.starting_mobject, 0, float(self.arc.parameter(alpha))
        )


class Ganesh2026(MovingCameraScene):
    def construct(self):
        # One lightweight vector object of faint, scattered paper fibers.
        # This avoids resizing/compositing a full bitmap on every camera frame.
        rng = np.random.default_rng(2026)
        # Irregular softly shaded facets suggest crumpled paper without a
        # per-frame bitmap resize. Deterministic geometry stays on the canvas.
        vertices = np.vstack((rng.uniform([-4.5, -8], [4.5, 8], (100, 2)),
                              [[-4.5, -8], [4.5, -8], [4.5, 8], [-4.5, 8]]))
        folds = VGroup()
        for triangle in Delaunay(vertices).simplices:
            shade = rng.uniform(0.02, 0.105)
            folds.add(Polygon(*[np.r_[p, 0] for p in vertices[triangle]],
                              stroke_width=0, fill_color="#A99C88",
                              fill_opacity=shade))
        folds.set_z_index(-21)
        self.add(folds)
        background = VMobject(stroke_color="#C5B9A6", stroke_opacity=0.16,
                              stroke_width=0.45, fill_opacity=0)
        for _ in range(1800):
            start = np.array([rng.uniform(-4.5, 4.5), rng.uniform(-8, 8), 0])
            end = start + np.array([rng.uniform(0.025, 0.09),
                                    rng.uniform(-0.018, 0.018), 0])
            background.start_new_path(start)
            background.add_line_to(end)
        background.set_z_index(-20)
        self.add(background)
        curves = load_curves()
        arc = ArcLength(curves)
        motion = CameraMotion(arc)
        points = np.zeros((curves.shape[0] * 4, 3))
        # The SVG is laid out in final-output pixels, independent of draft quality.
        points[:, 0] = (curves.reshape(-1, 2)[:, 0] - WIDTH / 2) * config.frame_width / WIDTH
        points[:, 1] = (HEIGHT / 2 - curves.reshape(-1, 2)[:, 1]) * config.frame_height / HEIGHT
        # Cairo scales Manim's width by 0.01 scene units, then by pixels per unit.
        stroke_width = STROKE_PX * config.frame_width / WIDTH / self.camera.cairo_line_width_multiple
        ink = VMobject(
            stroke_color=INK, stroke_width=stroke_width, fill_opacity=0,
            cap_style=CapStyleType.ROUND, joint_type=LineJointType.ROUND,
        )
        ink.set_points(points)

        title_font = PROJECT / "NotoSansDevanagari-Regular.ttf"
        manimpango.register_font(str(title_font))
        title = Text(
            "श्री गणेशाय नमः",
            color=INK,
            font="Noto Sans Devanagari",
            font_size=34,
            weight="NORMAL",
        )
        # The forehead and title share the canvas's horizontal center.
        title.set(width=6.0)
        title.set_z_index(10)
        title.to_edge(UP, buff=0.65)
        self.add(title)

        def camera_at(time):
            center, width = motion.pose(time)
            self.camera.frame.set(width=width * config.frame_width / WIDTH)
            self.camera.frame.move_to([
                (center[0] - WIDTH/2) * config.frame_width / WIDTH,
                (HEIGHT/2 - center[1]) * config.frame_height / HEIGHT, 0,
            ])

        camera_at(0)
        self.wait(OPENING)
        self.play(
            ContinuousInk(ink, arc),
            UpdateFromAlphaFunc(self.camera.frame, lambda _, alpha: camera_at(OPENING + DRAWING * alpha), rate_func=linear),
            run_time=DRAWING,
        )
        self.play(
            UpdateFromAlphaFunc(self.camera.frame, lambda _, alpha: camera_at(OPENING + DRAWING + PULLBACK * alpha), rate_func=linear),
            run_time=PULLBACK,
        )
        self.wait(HOLD)

        # Export the actual rendered final frame, in addition to the MP4.
        # A frozen hold caches the background. Clear it before drawing all
        # objects, otherwise translucent paper facets are composited twice.
        self.renderer.static_image = None
        self.renderer.update_frame(self, ignore_skipping=True)
        destination = Path(config.media_dir) / "Ganesh_2026.png"
        destination.parent.mkdir(parents=True, exist_ok=True)
        self.renderer.camera.get_image().save(destination)
