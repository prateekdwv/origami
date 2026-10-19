"""Read-only dataset integrity, exports, and encoded-frame verification."""
import hashlib
import json
import subprocess
import time
import av
import numpy as np
from PIL import Image
from design import FrameRenderer, second_at, traffic_series
from geography import boundary_hash, official_map
from model import active_counts, position
from settings import CATEGORIES, FPS, HEIGHT, INTRO, MEDIA, OUTRO, REPLAY, WIDTH
from store import write_json

def validate(data):
    ids = [j["id"] for j in data["journeys"]]
    if not ids or len(ids) != len(set(ids)):
        raise ValueError("Missing or duplicate journey instances")
    for journey in data["journeys"]:
        points, distances = np.asarray(journey["route_pixels"]), np.asarray(journey["distances"])
        if len(points) != len(distances) or not np.isfinite(points).all() or not np.isfinite(distances).all():
            raise ValueError("Invalid route coordinates")
        if (np.diff(distances) < 0).any():
            raise ValueError("Unordered route distances")
        previous = 0
        for segment in journey["segments"]:
            if not (previous <= segment["start"] < segment["end"] <= 86400
                    and 0 <= segment["from"] <= segment["to"] <= distances[-1]+.01):
                raise ValueError("Invalid movement interval")
            previous = segment["end"]
            if segment["kind"] == "dwell" and segment["from"] != segment["to"]:
                raise ValueError("A station stop moves")
    expected = [sum(active_counts(data["journeys"], s, data.get("categories", CATEGORIES)).values()) for s in range(0, 86401, 300)]
    if expected != data["activity"]:
        raise ValueError("Activity chart disagrees with displayed sample")

def export_stills(data, directory=MEDIA, compose=None):
    directory.mkdir(parents=True, exist_ok=True)
    compose = compose or FrameRenderer(data)
    times, counts = traffic_series(data["journeys"])
    peak_time = np.nextafter(INTRO + float(times[np.argmax(counts)])/86400*REPLAY, np.inf)
    compose(peak_time).save(directory / "IndiaRailway_2026_poster.png")
    compose(INTRO+REPLAY).save(directory / "IndiaRailway_2026_final.png")
    sheet = Image.new("RGB", (1080, 1280))
    for i, t in enumerate((0, 3, 16.5, 30, 43.5, 59)):
        thumb = compose(t).resize((360, 640), Image.Resampling.LANCZOS)
        sheet.paste(thumb, ((i % 3)*360, (i//3)*640))
    sheet.save(directory / "contact_sheet.png")

def audit_indices(data, full=False):
    total = (INTRO+REPLAY+OUTRO)*FPS
    times, counts = traffic_series(data["journeys"])
    peak = round((INTRO + float(times[np.argmax(counts)])/86400*REPLAY)*FPS)
    boundaries = {int(t*FPS)+offset for t in (INTRO, INTRO+REPLAY) for offset in (-1, 0)}
    return list(range(total)) if full else sorted(set(range(0, total, 150)) | boundaries | {min(total-1, peak), total-1})


def render_video(data, destination, compose=None):
    """Encode exactly one frame per tick, directly through FFmpeg's PyAV bindings."""
    started = time.perf_counter()
    compose = compose or FrameRenderer(data)
    initialization = time.perf_counter()-started
    started = time.perf_counter()
    with av.open(str(destination), "w", options={"movflags": "+faststart"}) as container:
        stream = container.add_stream("libx264", rate=FPS)
        stream.width, stream.height, stream.pix_fmt = WIDTH, HEIGHT, "yuv420p"
        stream.options = {"crf": "23", "preset": "medium"}
        total = (INTRO+REPLAY+OUTRO)*FPS
        for index in range(total):
            frame = av.VideoFrame.from_ndarray(np.asarray(compose(index/FPS)), format="rgb24")
            frame.pts = index
            for packet in stream.encode(frame):
                container.mux(packet)
            if index % 150 == 0:
                print(f"Encoded {index}/{total} frames", flush=True)
        for packet in stream.encode():
            container.mux(packet)
    return {"initialization_seconds": initialization, "export_seconds": time.perf_counter()-started,
            "frames": total, "encoder": "libx264", "preset": "medium", "crf": 23}


def decoded_frames(video, indices, full):
    with av.open(str(video)) as container:
        stream = container.streams.video[0]
        if full:
            for index, frame in enumerate(container.decode(stream)):
                yield index, frame.to_ndarray(format="rgb24")
        else:
            for index in indices:
                container.seek(int(index/FPS/stream.time_base), stream=stream)
                frame = next((f for f in container.decode(stream) if round(float(f.time)*FPS) >= index), None)
                if frame is None or round(float(frame.time)*FPS) != index:
                    raise RuntimeError(f"Missing video frame {index}")
                yield index, frame.to_ndarray(format="rgb24")


def verify(data, video, directory=MEDIA, *, full=False, compose=None):
    """Quick sampled audit by default; --full decodes and compares every frame."""
    indices = audit_indices(data, full)
    destination = directory / "verification.json"
    report = {"passed": False, "mode": "full" if full else "quick", "frames_compared": 0,
              "all_frames_compared": False, "status": "audit in progress"}
    write_json(destination, report)
    result = subprocess.run(["ffprobe", "-v", "error", *(["-count_frames"] if full else []),
                             "-show_streams", "-show_format", "-of", "json", str(video)],
                            check=True, capture_output=True, text=True)
    info = json.loads(result.stdout)
    streams = info["streams"]
    videos = [s for s in streams if s["codec_type"] == "video"]
    width, height = WIDTH, HEIGHT
    stream = videos[0] if videos else {}
    checks = {
        "one_silent_video_stream": len(streams) == len(videos) == 1,
        "dimensions": (stream.get("width"), stream.get("height")) == (width, height),
        "h264_yuv420p": stream.get("codec_name") == "h264" and stream.get("pix_fmt") == "yuv420p",
        "30fps": stream.get("avg_frame_rate") == "30/1",
        "1800_frames": stream.get("nb_read_frames" if full else "nb_frames") == "1800",
        "60_seconds": abs(float(info["format"]["duration"])-60) < .02,
        "clock_endpoints": second_at(3) == 0 and second_at(57) == 86400,
    }
    with video.open("rb") as source:
        video_hash = hashlib.file_digest(source, "sha256").hexdigest()
    report.update({"checks": checks, "video": str(video), "coverage": data["coverage"],
                   "scheduled_preview": bool(data.get("scheduled_preview")), "date": data.get("date"), "basis": data.get("basis"),
                   "categories": data.get("categories", CATEGORIES),
                   "palette_basis": data.get("palette_basis"),
                   "sample_indices": indices, "video_sha256": video_hash,
                   "dataset_sha256": hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest(),
                   "boundary_sha256": boundary_hash(), "boundary_rings": len(official_map()[2]),
                   "review_required": "Pixel checks cannot certify upstream data or replace visual review."})
    if not all(checks.values()):
        report["status"] = "failed"
        write_json(destination, report)
        raise RuntimeError("Encoded video metadata failed verification")
    compose = compose or FrameRenderer(data)
    max_error, max_hud, max_marker, frames, last_hold, hold_error = 0., 0., 0., 0, None, 0.
    decoded = decoded_frames(video, indices, full)
    try:
        for index, actual in decoded:
            if frames >= len(indices) or index != indices[frames] or actual.shape != (height, width, 3):
                raise RuntimeError("Unexpected video frame count or dimensions")
            expected = compose(index/FPS)
            # Signed 16-bit differences avoid allocating multiple 50 MB float frames.
            delta = np.abs(np.subtract(actual, np.asarray(expected), dtype=np.int16))
            scale = width/WIDTH
            max_error = max(max_error, float(delta.mean()))
            max_hud = max(max_hud, float(delta[int(40*scale):int(173*scale)].mean()))
            if INTRO <= index/FPS < INTRO+REPLAY:
                for journey, points, distances in compose.routes:
                    point = position(journey, second_at(index/FPS), (points, distances))
                    if point is not None:
                        x, y = (point*scale).astype(int)
                        radius = max(2, int(5*scale))
                        patch = delta[max(0, y-radius):y+radius+1, max(0, x-radius):x+radius+1]
                        if patch.size:
                            max_marker = max(max_marker, float(patch.mean()))
            if index >= (INTRO+REPLAY)*FPS:
                if last_hold is not None:
                    hold_error = max(hold_error, float(np.abs(np.subtract(actual, last_hold, dtype=np.int16)).mean()))
                last_hold = actual.copy()
            frames += 1
    finally:
        decoded.close()
    checks.update({"requested_frames_compared": frames == len(indices),
                   "pixel_comparison": max_error < 4 and max_hud < 6 and max_marker < 55,
                   "stationary_final_hold": hold_error < 1})
    report["frame_errors"] = {"max_mean": max_error, "max_hud_mean": max_hud,
                              "max_marker_mean": max_marker, "hold_mean": hold_error}
    report["passed"] = all(checks.values())
    report["status"] = "passed" if report["passed"] else "failed"
    report.update({"frames_compared": frames, "all_frames_compared": full and frames == 1800})
    write_json(destination, report)
    if not report["passed"]:
        raise RuntimeError("Frame audit failed; see verification.json")
    return report
