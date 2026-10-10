"""Read-only dataset integrity, exports, and encoded-frame verification."""
import hashlib
import json
import subprocess
import numpy as np
from PIL import Image
from design import base_image, draw_frame, second_at
from geography import boundary_hash, official_map
from model import active_counts, position
from settings import DATA, DAY, FPS, HEIGHT, INTRO, MEDIA, OUTRO, REPLAY, WIDTH
from store import write_json

def load_prepared(directory=DATA):
    path = directory / "prepared.json"
    if not path.exists():
        raise RuntimeError("No frozen dataset. Collect both passes, then run prepare; no synthetic fallback is allowed")
    data = json.loads(path.read_text())
    if data.get("synthetic_test_only"):
        raise RuntimeError("Synthetic previews cannot be loaded as a production replay")
    manifest = json.loads((directory / "manifest.json").read_text())
    if hashlib.sha256(path.read_bytes()).hexdigest() != manifest.get("frozen_sha256"):
        raise RuntimeError("Frozen dataset integrity check failed")
    if data["date"] != DAY or data["boundary_sha256"] != boundary_hash():
        raise RuntimeError("Replay date or official boundary has changed")
    for source in data["sources"]:
        if hashlib.sha256((directory / source["file"]).read_bytes()).hexdigest() != source["sha256"]:
            raise RuntimeError("Cached source integrity check failed")
    validate(data)
    return data

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
    expected = [sum(active_counts(data["journeys"], s).values()) for s in range(0, 86401, 300)]
    if expected != data["activity"]:
        raise ValueError("Activity chart disagrees with displayed sample")

def export_stills(data, directory=MEDIA):
    directory.mkdir(parents=True, exist_ok=True)
    base = base_image(data)
    peak_time = INTRO + int(np.argmax(data["activity"]))*300/86400*REPLAY
    draw_frame(base, data, peak_time).save(directory / "IndiaRailway_2026_poster.png")
    draw_frame(base, data, INTRO+REPLAY).save(directory / "IndiaRailway_2026_final.png")
    sheet = Image.new("RGB", (1080, 1280))
    for i, t in enumerate((0, 3, 16.5, 30, 43.5, 59)):
        thumb = draw_frame(base, data, t).resize((360, 640), Image.Resampling.LANCZOS)
        sheet.paste(thumb, ((i % 3)*360, (i//3)*640))
    sheet.save(directory / "contact_sheet.png")

def verify(data, video, directory=MEDIA, draft=False, frame_range=None):
    """Decode every frame; compare clock/count HUD, map, and each marker with the offline model."""
    start, end = frame_range or (0, 1800)
    if not 0 <= start < end <= 1800:
        raise ValueError("Invalid audit frame range")
    destination = directory / ("verification.json" if frame_range is None else f"verification_{start}_{end}.json")
    write_json(destination, {"passed": False, "status": "frame audit in progress", "frame_range": [start, end]})
    result = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-show_streams", "-show_format",
                             "-of", "json", str(video)], check=True, capture_output=True, text=True)
    info = json.loads(result.stdout)
    streams = info["streams"]
    videos = [s for s in streams if s["codec_type"] == "video"]
    width, height = (360, 640) if draft else (WIDTH, HEIGHT)
    stream = videos[0] if videos else {}
    checks = {
        "one_silent_video_stream": len(streams) == len(videos) == 1,
        "dimensions": (stream.get("width"), stream.get("height")) == (width, height),
        "h264_yuv420p": stream.get("codec_name") == "h264" and stream.get("pix_fmt") == "yuv420p",
        "30fps": stream.get("avg_frame_rate") == "30/1",
        "1800_frames": stream.get("nb_read_frames") == "1800",
        "60_seconds": abs(float(info["format"]["duration"])-60) < .02,
        "clock_endpoints": second_at(3) == 0 and second_at(57) == 86400,
    }
    report = {"checks": checks, "video": str(video), "coverage": data["coverage"],
              "synthetic_test_only": bool(data.get("synthetic_test_only")),
              "frame_range": [start, end], "video_sha256": hashlib.sha256(video.read_bytes()).hexdigest(),
              "dataset_sha256": hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest(),
              "boundary_sha256": boundary_hash(), "boundary_rings": len(official_map()[2]),
              "review_required": "Visual cartographic/label review and upstream accuracy cannot be certified by pixel checks."}
    if not all(checks.values()):
        write_json(destination, report)
        raise RuntimeError("Encoded video metadata failed verification")
    base = base_image(data)
    process = subprocess.Popen(["ffmpeg", "-v", "error", "-ss", str(start/FPS), "-i", str(video),
                                "-frames:v", str(end-start), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    max_error, max_hud, max_marker, frames, last_hold, hold_error = 0., 0., 0., 0, None, 0.
    try:
        for index in range(start, end):
            raw = process.stdout.read(width*height*3)
            if len(raw) != width*height*3:
                raise RuntimeError("Truncated video during frame audit")
            actual = np.frombuffer(raw, np.uint8).reshape(height, width, 3)
            expected = draw_frame(base, data, index/FPS)
            if draft:
                expected = expected.resize((width, height), Image.Resampling.LANCZOS)
            # Signed 16-bit differences avoid allocating multiple 50 MB float frames.
            delta = np.abs(np.subtract(actual, np.asarray(expected), dtype=np.int16))
            scale = width/WIDTH
            max_error = max(max_error, float(delta.mean()))
            max_hud = max(max_hud, float(delta[int(175*scale):int(255*scale)].mean()))
            if INTRO <= index/FPS < INTRO+REPLAY:
                for journey in data["journeys"]:
                    point = position(journey, second_at(index/FPS))
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
        process.stdout.close()
        process.wait()
    checks.update({"requested_frames_compared": frames == end-start and process.returncode == 0,
                   "pixel_comparison": max_error < 4 and max_hud < 6 and max_marker < 55,
                   "stationary_final_hold": hold_error < 1})
    report["frame_errors"] = {"max_mean": max_error, "max_hud_mean": max_hud,
                              "max_marker_mean": max_marker, "hold_mean": hold_error}
    report["passed"] = all(checks.values())
    if frame_range is None:
        checks["all_frames_compared"] = frames == 1800
    write_json(destination, report)
    if not report["passed"]:
        raise RuntimeError("Frame audit failed; see verification.json")
    return report


def merge_audits(data, video, directory):
    """Only certify the whole video when three matching, contiguous audits passed."""
    ranges = [(0, 600), (600, 1200), (1200, 1800)]
    reports = [json.loads((directory / f"verification_{a}_{b}.json").read_text()) for a, b in ranges]
    video_hash = hashlib.sha256(video.read_bytes()).hexdigest()
    data_hash = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
    for report, interval in zip(reports, ranges):
        if not (report.get("passed") and report["frame_range"] == list(interval)
                and report["video_sha256"] == video_hash and report["dataset_sha256"] == data_hash):
            raise RuntimeError("Missing, failed, or stale audit part; cannot certify all frames")
    merged = dict(reports[0])
    merged["checks"] = {key: all(r["checks"][key] for r in reports) for key in reports[0]["checks"]}
    merged["checks"]["all_frames_compared"] = True
    merged["frame_range"] = [0, 1800]
    merged["frame_errors"] = {key: max(r["frame_errors"][key] for r in reports) for key in reports[0]["frame_errors"]}
    write_json(directory / "verification.json", merged)
    return merged
