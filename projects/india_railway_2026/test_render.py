"""Explicit synthetic video preview; never collects or modifies production data."""
import argparse
from offline import deny_network
from demo import build_demo
from replay import export_stills, verify
from settings import MEDIA
from store import write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--draft", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--stills-only", action="store_true")
    parser.add_argument("--render-only", action="store_true")
    parser.add_argument("--full", action="store_true", help="Audit every frame instead of a quick sample")
    args = parser.parse_args()
    deny_network()
    data = build_demo()
    output = MEDIA / "synthetic_test" / ("draft" if args.draft else "full")
    output.mkdir(parents=True, exist_ok=True)
    if not args.verify_only:
        write_json(output / "preview_dataset.json", data)
        export_stills(data, output)
        if args.stills_only:
            return
        from scene import render_video
        write_json(output / "verification.json", {"passed": False, "status": "new render awaiting audit"})
        render_video(data, output, args.draft, "SYNTHETIC_TEST")
    if not args.render_only:
        print(verify(data, output / "SYNTHETIC_TEST.mp4", output, args.draft, full=args.full))


if __name__ == "__main__":
    main()
