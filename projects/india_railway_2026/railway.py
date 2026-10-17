"""Run from the repository root; every operation is explicit, with no background polling."""
import argparse
import json
import os
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
    diagnostic = commands.add_parser("diagnose-directory", help="Explicitly retry one failed directory HTTP request; preserves quota accounting")
    diagnostic.add_argument("--remaining-quota", type=int, required=True)
    for name in ("status", "prepare", "proof", "doctor"):
        commands.add_parser(name)
    for name in ("render", "verify"):
        command = commands.add_parser(name)
        command.add_argument("--draft", action="store_true")
        command.add_argument("--full", action="store_true", help="Audit every frame instead of a quick sample")
    args = parser.parse_args()
    if args.command == "doctor":
        from acquire import key_issues, auth_mode
        key = os.environ.get("RAILRADAR_API_KEY", "")
        issues = key_issues(key)
        print(json.dumps({"python": sys.version.split()[0], "executable": sys.executable,
                          "key_present": bool(key), "key_format_issues": issues, "auth_mode": auth_mode(),
                          "network_requests_made": 0,
                          "note": "This checks local configuration, not whether RailRadar accepts the key"}, indent=2))
    elif args.command == "diagnose-directory":
        from acquire import Client, CollectionStopped
        with Store(DATA).locked() as store:
            if store.manifest.get("frozen_sha256") or (DATA / "prepared.json").exists():
                raise CollectionStopped("Dataset is frozen")
            if store.manifest.get("gate") == "failed":
                raise CollectionStopped("History feasibility failed; review the cache before further requests")
            records = [r for r in store.manifest["requests"] if r["kind"] == "directory" and r["identity"] == "trains"]
            if not records or records[-1]["status"] != "http_failed":
                raise CollectionStopped("No directory HTTP failure to diagnose")
            phase = records[-1]["phase"]
            if store.manifest["passes"].get(phase) == "finished":
                raise CollectionStopped("The collection pass is already finished")
            client = Client(store, phase, os.environ.get("RAILRADAR_API_KEY", ""), args.remaining_quota)
            try:
                payload = client.get("directory", "trains", "/lookup/trains", retry_directory=True)
            finally:
                last = store.manifest["requests"][-1]
                print(json.dumps({k: last[k] for k in ("path", "status", "http_status", "auth_mode", "response_bytes", "error") if k in last}, indent=2))
            if payload is not None:
                print("Directory response cached. Resume the original collect command to validate and select trains.")
    elif args.command == "collect":
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
