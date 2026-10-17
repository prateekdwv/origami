"""Deterministic offline Manim scene, composed in original portrait pixels."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from manim import Camera, ImageMobject, Scene, ValueTracker, config, linear, tempconfig
import numpy as np
from PIL import Image
from design import FrameRenderer
from offline import deny_network
from replay import load_prepared
from settings import INTRO, REPLAY, OUTRO, ROOT


def render_video(data, directory, draft=False, name="IndiaRailway_2026"):
    """Shared production/preview export using the project Manim configuration."""
    deny_network()
    with tempconfig({}):
        config.digest_file(str(ROOT / "manim.cfg"))
        config.update({"media_dir": str(directory), "video_dir": str(directory),
                       "partial_movie_dir": str(directory / "partial"), "output_file": name,
                       "progress_bar": "none"})
        if draft:
            config.update({"pixel_width": 360, "pixel_height": 640})
        IndiaRailway2026(dataset=data).render()


class PixelAlignedCamera(Camera):
    """Fast path for this fixed, opaque, full-frame raster; no perspective transform."""
    def display_image_mobject(self, image_mobject, pixel_array):
        if getattr(image_mobject, "replay_frame", False):
            if image_mobject.pixel_array.shape != pixel_array.shape:
                raise ValueError("Replay frame does not match the camera's pixel grid")
            np.copyto(pixel_array, image_mobject.pixel_array)
        else:
            super().display_image_mobject(image_mobject, pixel_array)


class IndiaRailway2026(Scene):
    def __init__(self, dataset=None, **kwargs):
        self.dataset = dataset
        kwargs.setdefault("camera_class", PixelAlignedCamera)
        super().__init__(**kwargs)

    def construct(self):
        deny_network()
        compose = FrameRenderer(self.dataset if self.dataset is not None else load_prepared())
        time = ValueTracker(0)
        def frame():
            result = compose(time.get_value())
            if result.size != (config.pixel_width, config.pixel_height):
                result = result.resize((config.pixel_width, config.pixel_height), Image.Resampling.LANCZOS)
            return np.asarray(result.convert("RGBA"))
        image = ImageMobject(frame())
        image.replay_frame = True
        image.height = 16
        image.add_updater(lambda mob: setattr(mob, "pixel_array", frame()))
        self.add(image)
        self.play(time.animate.set_value(INTRO+REPLAY+OUTRO),
                  run_time=INTRO+REPLAY+OUTRO, rate_func=linear)
        image.clear_updaters()
