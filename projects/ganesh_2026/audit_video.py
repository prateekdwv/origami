"""Compare every encoded frame with an independently rasterized SVG prefix."""

import argparse
import json
from pathlib import Path

import av
import cairo
import numpy as np
from PIL import Image, ImageDraw
from scipy.spatial import Delaunay

from artwork import ArcLength, load_curves
from motion import CameraMotion, FPS, OPENING, DRAWING, PULLBACK, HOLD, TOTAL, drawing_progress


def reference_frame(curves, arc, progress, pose):
    # Match the export's rasterization before downsampling; drawing directly
    # at thumbnail resolution gives different line-edge antialiasing.
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 1080, 1920)
    ctx = cairo.Context(surface)
    ctx.set_source_rgb(250/255, 249/255, 246/255)
    ctx.paint()
    center, width = pose
    ctx.translate(540, 960)
    ctx.scale(1080 / width, 1080 / width)
    ctx.translate(-center[0], -center[1])
    rng = np.random.default_rng(2026)
    vertices = np.vstack((rng.uniform([-4.5, -8], [4.5, 8], (100, 2)),
                          [[-4.5, -8], [4.5, -8], [4.5, 8], [-4.5, 8]]))
    for triangle in Delaunay(vertices).simplices:
        shade = rng.uniform(0.02, 0.105)
        polygon = vertices[triangle] * [120, -120] + [540, 960]
        ctx.move_to(*polygon[0])
        for point in polygon[1:]:
            ctx.line_to(*point)
        ctx.close_path()
        ctx.set_source_rgba(169/255, 156/255, 136/255, shade)
        ctx.fill()
    if progress >= 0:
        ctx.set_source_rgb(17/255, 17/255, 17/255)
        ctx.set_line_width(4)
        ctx.set_line_cap(cairo.LINE_CAP_ROUND)
        ctx.set_line_join(cairo.LINE_JOIN_ROUND)
        ctx.move_to(*curves[0, 0])
        position = float(arc.parameter(progress)) * len(curves)
        completed = min(int(position), len(curves))
        for curve in curves[:completed]:
            ctx.curve_to(*curve[1:].ravel())
        if completed < len(curves):
            # De Casteljau split: the left piece is precisely the visible prefix.
            t = position - completed
            p = curves[completed]
            a = (1-t)*p[:-1] + t*p[1:]
            b = (1-t)*a[:-1] + t*a[1:]
            end = (1-t)*b[0] + t*b[1]
            ctx.curve_to(*np.concatenate([a[0], b[0], end]))
        ctx.stroke()
    surface.flush()
    pixels = np.frombuffer(surface.get_data(), dtype=np.uint8).reshape(1920, 1080, 4)
    return np.asarray(Image.fromarray(pixels[:, :, [2, 1, 0]]).resize(
        (270, 480), Image.Resampling.LANCZOS
    ))


def audit(path):
    curves = load_curves()
    arc = ArcLength(curves)
    motion = CameraMotion(arc)
    sample_frames = [round(t * FPS) for t in (
        0, 3, 6, 12, 24, OPENING + DRAWING - 0.5,
        OPENING + DRAWING, OPENING + DRAWING + 0.5,
        OPENING + DRAWING + 1.5, OPENING + DRAWING + 2.5,
        OPENING + DRAWING + PULLBACK, TOTAL - 1 / FPS,
    )]
    sheet = Image.new("RGB", (270*4, 510*3), "#FAF9F6")
    draw = ImageDraw.Draw(sheet)
    errors = []
    color_offsets = []
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        assert (stream.width, stream.height) == (1080, 1920)
        assert stream.average_rate == 30
        assert stream.codec_context.name == "h264"
        assert stream.codec_context.format.name == "yuv420p"
        assert not container.streams.audio
        for index, frame in enumerate(container.decode(stream)):
            assert abs(float(frame.time) - index/30) < 1e-5
            thumbnail = frame.to_image().resize((270, 480), Image.Resampling.LANCZOS)
            actual = np.asarray(thumbnail).astype(float)
            progress = drawing_progress(index / FPS)
            expected = reference_frame(curves, arc, progress, motion.pose(index / FPS)).astype(float)
            # H.264/YUV conversion introduces a small uniform background offset.
            # Measure it only on flat background; still reject larger color shifts.
            # Exclude the canvas title's projected bounds from the SVG audit.
            # It follows the same camera transform as the artwork.
            comparison_mask = np.ones(expected.shape[:2], dtype=bool)
            center, width = motion.pose(index / FPS)
            bounds = (np.array([[140, 60], [940, 260]]) - center) * (270 / width) + [135, 240]
            left, top = np.maximum(np.floor(bounds[0]).astype(int), 0)
            right, bottom = np.minimum(np.ceil(bounds[1]).astype(int), [270, 480])
            if right > left and bottom > top:
                comparison_mask[top:bottom, left:right] = False
            background = np.all(expected > 225, axis=2) & comparison_mask
            offset = np.median((actual - expected)[background], axis=0)
            assert np.max(np.abs(offset)) <= 3, (index, offset)
            color_offsets.append(float(np.max(np.abs(offset))))
            difference = np.abs(actual - offset - expected)
            difference[~comparison_mask] = 0
            # Allow YUV compression, antialiasing, and downsampling differences.
            mean_error = float(difference.mean())
            changed_fraction = float((difference.max(axis=2) > 50).mean())
            assert mean_error < 2.0, (index, mean_error)
            assert changed_fraction < 0.004, (index, changed_fraction)
            errors.append(mean_error)
            if index in sample_frames:
                cell = sample_frames.index(index)
                x, y = (cell % 4)*270, (cell // 4)*510
                sheet.paste(thumbnail, (x, y))
                draw.text((x+12, y+488), f"{index/30:.2f} seconds", fill="#111111")
    assert len(errors) == round(TOTAL * FPS), len(errors)
    sheet.save(path.parent / "contact_sheet.png")
    report = {
        "frames": len(errors), "duration_seconds": len(errors)/30,
        "resolution": [1080, 1920], "fps": 30, "codec": "h264", "pixel_format": "yuv420p",
        "blank_frames": round(OPENING * FPS), "drawing_frames": round(DRAWING * FPS),
        "pullback_frames": round(PULLBACK * FPS), "completed_hold_frames": round(HOLD * FPS),
        "max_mean_pixel_error_against_source": max(errors),
        "max_background_codec_offset": max(color_offsets),
        "curves": len(curves), "stroke_length_px": float(arc.length),
        "every_frame_matches_continuous_prefix": True,
    }
    (path.parent / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("video", type=Path)
    audit(parser.parse_args().video)
