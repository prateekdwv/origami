"""Explicit opt-in integration test: full 60-second Manim export, never production data.

Run directly with --draft for 360×640 or without it for the full-resolution test.
"""
import argparse
from unittest.mock import patch
from manim import tempconfig
from offline import deny_network
from demo import build_demo
from replay import export_stills, merge_audits, verify
from scene import IndiaRailway2026
from settings import MEDIA
from store import write_json

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--draft", action="store_true")
    parser.add_argument("--verify-only", action="store_true", help="Audit an existing synthetic export without rerendering")
    parser.add_argument("--stills-only", action="store_true", help="Generate the busy demo poster and contact sheet without encoding video")
    parser.add_argument("--render-only", action="store_true", help="Encode video now; run --verify-only separately for a long audit")
    parser.add_argument("--audit-part", type=int, choices=range(3), help="Audit one 600-frame range (0–2), without rendering")
    parser.add_argument("--merge-audits", action="store_true", help="Certify all 1800 frames from three matching range audits")
    args = parser.parse_args()
    deny_network()
    data = build_demo()
    output = MEDIA / "synthetic_test" / ("draft" if args.draft else "full")
    output.mkdir(parents=True, exist_ok=True)
    if args.audit_part is not None:
        a = args.audit_part*600
        if args.audit_part == 0:
            write_json(output / "verification.json", {"passed": False, "status": "frame-range audits in progress",
                                                       "synthetic_test_only": True})
        print(verify(data, output / "SYNTHETIC_TEST.mp4", output, args.draft, (a, a+600)))
        return
    if args.merge_audits:
        print(merge_audits(data, output / "SYNTHETIC_TEST.mp4", output))
        return
    write_json(output / "preview_dataset.json", data)
    export_stills(data, output)
    if args.stills_only:
        print(f"Synthetic poster and contact sheet: {output}")
        return
    if not args.verify_only:
        write_json(output / "verification.json", {"passed": False, "status": "new render awaiting frame audit",
                                                  "synthetic_test_only": True})
    width, height = (360, 640) if args.draft else (1080, 1920)
    with tempconfig({"renderer": "cairo", "pixel_width": width, "pixel_height": height,
                     "frame_width": 9, "frame_height": 16, "frame_rate": 30,
                     "media_dir": str(output), "video_dir": str(output),
                     "partial_movie_dir": str(output / "partial"), "output_file": "SYNTHETIC_TEST",
                     "progress_bar": "none",
                     "disable_caching": True, "write_to_movie": True, "format": "mp4"}), \
            patch("scene.load_prepared", return_value=data):
        if not args.verify_only:
            IndiaRailway2026().render()
    if not args.render_only:
        report = verify(data, output / "SYNTHETIC_TEST.mp4", output, args.draft)
        print(report)

if __name__ == "__main__":
    main()
