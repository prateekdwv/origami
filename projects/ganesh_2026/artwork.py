"""Strict single-path reader and shared portrait geometry (no SVG auto-tracing)."""

from pathlib import Path
import re
import xml.etree.ElementTree as ET

import cairo
import numpy as np

ROOT = Path(__file__).resolve().parent
SVG = ROOT / "ganesh.svg"
WIDTH, HEIGHT = 1080, 1920
BACKGROUND = "#FAF9F6"
INK = "#111111"
STROKE_PX = 4.0


def load_curves():
    """Return connected cubic control points in final-output pixel coordinates."""
    root = ET.parse(SVG).getroot()
    paths = root.findall(".//{http://www.w3.org/2000/svg}path")
    if len(paths) != 1:
        raise ValueError("Artwork must contain exactly one path")
    data = paths[0].attrib["d"]
    tokens = re.findall(r"[A-Za-z]|[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?", data)
    if tokens[0] != "M" or tokens.count("M") != 1:
        raise ValueError("Artwork must have one initial move")
    start = np.array(tokens[1:3], dtype=float)
    curves = []
    i = 3
    while i < len(tokens):
        if tokens[i] != "C":
            raise ValueError("Only explicit cubic curves are allowed after the move")
        controls = np.array(tokens[i + 1:i + 7], dtype=float).reshape(3, 2)
        curves.append(np.vstack([start, controls]))
        start = controls[-1]
        i += 7
    curves = np.array(curves)
    if not np.isfinite(curves).all():
        raise ValueError("Non-finite path coordinates")
    x, y, w, h = map(float, root.attrib["viewBox"].split())
    scale = min(820 / w, 1050 / h)
    # Align the forehead/crown axis with the title, rather than centering the
    # asymmetric trailing stroke and arms by the SVG view box.
    return (curves - [517, y + h / 2]) * scale + [540, 900]


def evaluate(curves, t):
    t = np.asarray(t)[..., None]
    return ((1-t)**3 * curves[..., 0, :] + 3*(1-t)**2*t * curves[..., 1, :]
            + 3*(1-t)*t**2 * curves[..., 2, :] + t**3 * curves[..., 3, :])


class ArcLength:
    """Map traveled distance to Manim's equally weighted cubic parameter."""

    def __init__(self, curves, samples_per_curve=256):
        self.curves = curves
        samples = evaluate(curves[:, None], np.linspace(0, 1, samples_per_curve + 1)[None, :])
        lengths = np.linalg.norm(np.diff(samples, axis=1), axis=2)
        if np.any(lengths.sum(axis=1) < 1e-7):
            raise ValueError("Zero-length cubic")
        self.distances = np.r_[0, np.cumsum(lengths.ravel())]
        self.parameters = np.linspace(0, 1, len(self.distances))
        self.length = self.distances[-1]

    def parameter(self, progress):
        return np.interp(np.clip(progress, 0, 1) * self.length, self.distances, self.parameters)

    def points(self, progress):
        position = np.asarray(self.parameter(progress)) * len(self.curves)
        index = np.minimum(position.astype(int), len(self.curves) - 1)
        return evaluate(self.curves[index], position - index)


def proof(output=Path("media/ganesh_2026/artwork_proof.png")):
    """Render the source directly with Cairo before animation is constructed."""
    output.parent.mkdir(parents=True, exist_ok=True)
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, WIDTH, HEIGHT)
    ctx = cairo.Context(surface)
    ctx.set_source_rgb(250/255, 249/255, 246/255)
    ctx.paint()
    ctx.set_source_rgb(17/255, 17/255, 17/255)
    ctx.set_line_width(STROKE_PX)
    ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    ctx.set_line_join(cairo.LINE_JOIN_ROUND)
    curves = load_curves()
    ctx.move_to(*curves[0, 0])
    for curve in curves:
        ctx.curve_to(*curve[1:].ravel())
    ctx.stroke()
    surface.write_to_png(str(output))
    print(output)


if __name__ == "__main__":
    proof()
