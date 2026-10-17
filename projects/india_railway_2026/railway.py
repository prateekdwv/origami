"""Run from the repository root; every operation is explicit, with no background polling."""
import argparse
import json
import sys
from settings import DATA, MEDIA
from store import Store, write_json

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    collect = commands.add_parser("collect")
    collect.add_argument("phase", choices=("initial", "completion"))
    collect.add_argument("--remaining-quota", type=int, required=True,
                         help="Current remaining monthly account allowance, checked in your dashboard")
    for name in ("status", "prepare", "proof"):
        commands.add_parser(name)
    for name in ("render", "verify"):
        command = commands.add_parser(name)
        command.add_argument("--draft", action="store_true")
        command.add_argument("--full", action="store_true", help="Audit every frame instead of a quick sample")
    args = parser.parse_args()
    if args.command == "collect":
        from acquire import collect_pass
        with Store(DATA).locked() as store:
            collect_pass(store, args.phase, args.remaining_quota)
            if reason := store.manifest.get("pass_stop_reason", {}).get(args.phase):
                print(reason)
        print("Pass finished. Inspect status and coverage before preparing.")
    elif args.command == "status":
        manifest = Store(DATA).manifest
        print(json.dumps({"day": manifest["day"], "gate": manifest["gate"], "passes": manifest["passes"],
                          "requests_consumed": len(manifest["requests"]), "budget_total": manifest["budget_total"],
                          "selected": len(manifest["selection"]),
                          "complete": sum(j["complete"] for j in manifest["selection"]),
                          "pending": sum(not j["complete"] for j in manifest["selection"]),
                          "halt": manifest.get("halt"),
                          "failures": sum(r["status"] != "ok" for r in manifest["requests"]),
                          "frozen": bool(manifest.get("frozen_sha256"))}, indent=2))
    else:
        from offline import deny_network
        deny_network()
        if args.command == "prepare":
            from model import prepare
            with Store(DATA).locked() as store:
                data = prepare(store)
            print(f"Frozen {len(data['journeys'])} usable journeys. Coverage: {DATA / 'coverage.json'}")
        elif args.command == "proof":
            from design import FrameRenderer
            from geography import boundary_hash, official_map
            MEDIA.mkdir(parents=True, exist_ok=True)
            FrameRenderer()().save(MEDIA / "design_proof.png")
            write_json(MEDIA / "design_proof.json", {"status": "awaiting actual observations; not a factual replay",
                       "boundary_sha256": boundary_hash(), "rings": len(official_map()[2]), "simplified": False})
            print(MEDIA / "design_proof.png")
        else:
            from replay import export_stills, load_prepared, verify
            data = load_prepared()
            directory = MEDIA / "draft" if args.draft else MEDIA
            directory.mkdir(parents=True, exist_ok=True)
            video = directory / "IndiaRailway_2026.mp4"
            if args.command == "render":
                from scene import render_video
                render_video(data, directory, args.draft)
                export_stills(data, directory)
            report = verify(data, video, directory, args.draft, full=args.full)
            print(f"{report['mode']} verification: {report['frames_compared']} frames compared: {video}")

if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError, OSError) as error:
        print(f"Stopped: {error}", file=sys.stderr)
        sys.exit(1)
