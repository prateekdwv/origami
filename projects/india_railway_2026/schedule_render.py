"""Offline timetable preview on inferred mapped tracks; never recorded operations."""
import argparse
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
import gzip
import hashlib
import json
import shutil
import tempfile
import time

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components, dijkstra
from scipy.spatial import cKDTree

from geography import boundary_hash, pixels, project
from prepare_tracks import simplify
from settings import MEDIA, ROOT, SCHEDULE_CATEGORIES, SCHEDULE_PALETTE_BASIS, classify_scheduled
from store import write_json
from tracks import DIRECTORY, load_tracks

SCHEDULES = ROOT / "assets" / "schedules"
OUTPUT = MEDIA / "scheduled_test"
# Bump when routing or movement preparation changes, not for presentation edits.
PREPARATION_VERSION = 1


def read_gzip(path):
    return json.loads(gzip.decompress(path.read_bytes()))


def input_hashes(day):
    paths = [SCHEDULES / name for name in ("trains.json.gz", "stations.json.gz", f"journeys-{day}.json.gz")]
    paths += [DIRECTORY / "geometry.json.gz"]
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def cache_matches(data, day):
    return (data is not None and data.get("date") == day
            and data.get("preparation_version") == PREPARATION_VERSION
            and data.get("source_hashes") == input_hashes(day)
            and data.get("boundary_sha256") == boundary_hash())


def update_categories(data):
    """Restyle cached movements without routing the network again."""
    previous = json.dumps([data.get("categories"), data.get("palette_basis"),
                           [j["category"] for j in data["journeys"]]], sort_keys=True)
    trains = {t["number"]: t for t in read_gzip(SCHEDULES / "trains.json.gz")}
    for journey in data["journeys"]:
        journey["category"] = category(trains[journey["id"].split("@")[0]])
    data["categories"], data["palette_basis"] = SCHEDULE_CATEGORIES, SCHEDULE_PALETTE_BASIS
    data["coverage"]["category_journeys"] = dict(Counter(j["category"] for j in data["journeys"]))
    return previous != json.dumps([data["categories"], data["palette_basis"],
                                   [j["category"] for j in data["journeys"]]], sort_keys=True)


def category(train):
    result = classify_scheduled(train["name"], train["service_type"])
    if result is None:
        raise ValueError(f"Non-passenger timetable: {train['number']}")
    return result


def mapped_legs(trains, stations):
    """Contract degree-two vertices before routing between adjacent timetable stops.

    Only existing OSM edges are traversed. Station snaps are bounded to 2.5 km;
    disconnected paths and detours over 3.5x straight distance are omitted.
    """
    geometry, _ = load_tracks()
    lines = [np.round(line["coordinates"], 5) for line in geometry["network"]]
    lonlat, inverse = np.unique(np.concatenate(lines), axis=0, return_inverse=True)
    xy = project(lonlat)
    ends = np.cumsum([len(line) for line in lines])
    inside = np.ones(len(inverse)-1, dtype=bool)
    inside[ends[:-1]-1] = False
    edges = np.unique(np.sort(np.column_stack((inverse[:-1][inside], inverse[1:][inside])), axis=1), axis=0)
    edges = edges[edges[:, 0] != edges[:, 1]]
    weights = np.linalg.norm(xy[edges[:, 0]]-xy[edges[:, 1]], axis=1)
    graph = coo_matrix((np.r_[weights, weights], (np.r_[edges[:, 0], edges[:, 1]], np.r_[edges[:, 1], edges[:, 0]])),
                       shape=(len(xy), len(xy))).tocsr()
    _, components = connected_components(graph, directed=False)
    sizes = np.bincount(components)
    tree = cKDTree(xy)
    codes = sorted({s["station"] for t in trains for s in t["stops"]})
    snaps, missing = {}, []
    for code in codes:
        station = stations.get(code, {})
        if station.get("longitude") is None or station.get("latitude") is None:
            missing.append(code)
            continue
        center = project([[station["longitude"], station["latitude"]]])[0]
        nearby = tree.query_ball_point(center, 2500)
        if not nearby:
            missing.append(code)
            continue
        # Prefer the nearest node on a substantial connected component over a siding.
        viable = [n for n in nearby if sizes[components[n]] >= 100]
        node = min(viable or nearby, key=lambda n: float(np.linalg.norm(xy[n]-center)))
        snaps[code] = node
    degree = np.bincount(edges.ravel(), minlength=len(xy))
    retained = degree != 2
    retained[list(snaps.values())] = True
    adjacency = [[] for _ in xy]
    for i, (a, b) in enumerate(edges):
        adjacency[a].append((int(b), i))
        adjacency[b].append((int(a), i))
    visited = np.zeros(len(edges), dtype=bool)
    compressed = {}
    for origin in np.flatnonzero(retained):
        for following, edge in adjacency[origin]:
            if visited[edge]:
                continue
            path, length = [int(origin)], 0.
            while True:
                visited[edge] = True
                path.append(following)
                length += weights[edge]
                if retained[following]:
                    break
                following, edge = next((n, e) for n, e in adjacency[following] if e != edge)
            if origin == following:
                continue
            key = tuple(sorted((int(origin), following)))
            if key not in compressed or length < compressed[key][0]:
                compressed[key] = (float(length), path if path[0] == key[0] else path[::-1])
    nodes = np.flatnonzero(retained)
    index = {int(n): i for i, n in enumerate(nodes)}
    pairs = np.array([(index[a], index[b]) for a, b in compressed])
    lengths = np.array([item[0] for item in compressed.values()])
    graph = coo_matrix((np.r_[lengths, lengths], (np.r_[pairs[:, 0], pairs[:, 1]], np.r_[pairs[:, 1], pairs[:, 0]])),
                       shape=(len(nodes), len(nodes))).tocsr()
    wanted = sorted({tuple(sorted((a["station"], b["station"])))
                     for t in trains for a, b in zip(t["stops"], t["stops"][1:])})
    groups, paths, failures = defaultdict(list), {}, Counter()
    for a, b in wanted:
        if a not in snaps or b not in snaps:
            failures["station_not_snapped"] += 1
        elif snaps[a] == snaps[b]:
            failures["coincident_station_snaps"] += 1
        elif components[snaps[a]] != components[snaps[b]]:
            failures["disconnected_tracks"] += 1
        else:
            groups[a].append(b)
    print(f"Track graph: {len(xy):,} vertices -> {len(nodes):,}; {len(wanted):,} station pairs; routing {len(groups):,} origins", flush=True)
    for count, (a, destinations) in enumerate(groups.items(), 1):
        origin = index[snaps[a]]
        direct = {b: float(np.linalg.norm(xy[snaps[a]]-xy[snaps[b]])) for b in destinations}
        distances, predecessors = dijkstra(graph, directed=False, indices=origin, return_predecessors=True,
                                            limit=max(max(10000., 3.5*d) for d in direct.values()))
        for b in destinations:
            target = index[snaps[b]]
            if not np.isfinite(distances[target]) or distances[target] > max(10000., 3.5*direct[b]):
                failures["excessive_or_missing_path"] += 1
                continue
            chain = [target]
            while chain[-1] != origin:
                chain.append(int(predecessors[chain[-1]]))
            chain.reverse()
            vertices = []
            for left, right in zip(chain, chain[1:]):
                u, v = int(nodes[left]), int(nodes[right])
                part = compressed[tuple(sorted((u, v)))][1]
                part = part if part[0] == u else part[::-1]
                vertices.extend(part if not vertices else part[1:])
            line = xy[vertices]
            along = np.r_[0., np.cumsum(np.linalg.norm(np.diff(line, axis=0), axis=1))]
            chosen = simplify(line)
            paths[(a, b)] = (pixels(line[chosen]), along[chosen])
        if count % 500 == 0:
            print(f"Routed {count:,}/{len(groups):,} origins; {len(paths):,} connected station pairs", flush=True)
    return paths, {"station_pairs": len(wanted), "mapped_station_pairs": len(paths),
                   "pair_exclusions": dict(failures), "unmapped_station_codes": missing,
                   "maximum_station_snap_metres": 2500, "path_method": "Shortest existing OSM path via every mapped timetable stop; inferred, not verified train itineraries"}


def prepare_route(train, paths):
    points, distances, measures, valid = [], [], [None]*len(train["stops"]), set()
    for i, (a, b) in enumerate(zip(train["stops"], train["stops"][1:])):
        left, right = a["station"], b["station"]
        leg = paths.get(tuple(sorted((left, right))))
        if leg is None:
            continue
        screen, along = leg
        if left > right:
            screen, along = screen[::-1], along[-1]-along[::-1]
        # A measure gap keeps trails from crossing missing geometry.
        base = distances[-1] if measures[i] is not None else (distances[-1]+1 if distances else 0)
        start = 1 if measures[i] is not None else 0
        points.extend(screen[start:].tolist())
        distances.extend((base+along[start:]).tolist())
        measures[i], measures[i+1] = base, base+float(along[-1])
        valid.add(i)
    return points, distances, measures, valid


def movement_segments(train, instance, measures, valid):
    """Clip scheduled dwells/travel without repairing missing times or geometry."""
    offset = (date.fromisoformat(instance["origin_date"])-date.fromisoformat(instance["target_date"])).days*86400
    segments, rejected = [], 0
    def add(start, end, a, b, kind):
        if a is None or b is None or end <= start:
            return
        lo, hi = max(0, start+offset), min(86400, end+offset)
        if hi > lo:
            segments.append({"start": lo, "end": hi, "from": a+(b-a)*(lo-start-offset)/(end-start),
                             "to": a+(b-a)*(hi-start-offset)/(end-start), "kind": kind})
    for i, stop in enumerate(train["stops"]):
        add(stop["arrival"], stop["departure"], measures[i], measures[i], "dwell")
        if i+1 < len(measures) and i in valid:
            arrival = train["stops"][i+1]["arrival"]
            duration = arrival-stop["departure"]
            if duration > 0 and (measures[i+1]-measures[i])/duration <= 350/3.6:
                add(stop["departure"], arrival, measures[i], measures[i+1], "travel")
            else:
                rejected += 1
    return segments, rejected


def build_dataset(day):
    trains = {t["number"]: t for t in read_gzip(SCHEDULES / "trains.json.gz")}
    instances = read_gzip(SCHEDULES / f"journeys-{day}.json.gz")
    selected = {i["number"]: trains[i["number"]] for i in instances}
    paths, mapping = mapped_legs(selected.values(), read_gzip(SCHEDULES / "stations.json.gz"))
    routes = {number: prepare_route(train, paths) for number, train in selected.items()}
    journeys, excluded, rejected = [], [], 0
    for instance in instances:
        train = selected[instance["number"]]
        points, distances, measures, valid = routes[train["number"]]
        segments, errors = movement_segments(train, dict(instance, target_date=day), measures, valid)
        rejected += errors
        if not any(s["kind"] == "travel" for s in segments):
            excluded.append(instance["id"])
            continue
        journeys.append({"id": instance["id"], "name": train["name"], "category": category(train),
                         "route_pixels": points, "distances": distances, "segments": segments})
    coverage = {"selected": len(instances), "included": len(journeys), "excluded_journey_ids": excluded,
                "rejected_speed_or_duration_segments": rejected, "category_journeys": dict(Counter(j["category"] for j in journeys)),
                "complete_national_coverage": False, "historical_date_certified": False, **mapping}
    # Difference-array counts avoid rescanning every stop at every chart sample.
    times = np.arange(0, 86401, 300)
    activity = np.zeros(len(times), dtype=int)
    for journey in journeys:
        for segment in journey["segments"]:
            activity += (times >= segment["start"]) & (times < segment["end"])
    _, provenance = load_tracks()
    return {"version": 1, "preparation_version": PREPARATION_VERSION,
            "date": day, "timezone": "Asia/Kolkata", "scheduled_preview": True,
            "categories": SCHEDULE_CATEGORIES,
            "palette_basis": SCHEDULE_PALETTE_BASIS,
            "basis": "Provisional collected timetables; interpolated movement on inferred OSM paths, not actual operations",
            "track_source": "OpenStreetMap", "railway_geometry_sha256": provenance["geometry_sha256"],
            "boundary_sha256": boundary_hash(), "source_hashes": input_hashes(day), "coverage": coverage,
            "journeys": journeys, "activity": activity.tolist()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default="2026-10-15", type=lambda value: date.fromisoformat(value).isoformat())
    parser.add_argument("--final", action="store_true", help="Higher-quality upload export with every frame audited")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--stills-only", action="store_true")
    mode.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    cache = OUTPUT / args.date
    cache.mkdir(parents=True, exist_ok=True)
    output = MEDIA / "final" / args.date if args.final else cache
    output.mkdir(parents=True, exist_ok=True)
    path = cache / "preview_dataset.json.gz"
    started = time.perf_counter()
    data = read_gzip(path) if path.exists() else None
    rebuilt = not cache_matches(data, args.date)
    if rebuilt:
        if args.verify_only:
            raise RuntimeError("Preview inputs changed; regenerate before verification")
        data = build_dataset(args.date)
    restyled = update_categories(data)
    from replay import export_stills, render_video, validate, verify
    from design import FrameRenderer, traffic_series
    validate(data)
    if (rebuilt or restyled) and not args.verify_only:
        temporary = path.with_suffix(".tmp")
        temporary.write_bytes(gzip.compress(json.dumps(data, separators=(",", ":")).encode(), mtime=0))
        temporary.replace(path)
    _, counts = traffic_series(data["journeys"])
    print(f"Displaying {len(data['journeys']):,}/{data['coverage']['selected']:,} timetable journeys; exact peak {max(counts):,}", flush=True)
    video = output / (f"India_Railways_{args.date}.mp4" if args.final else "SCHEDULED_TEST.mp4")
    preparation = {"cache_rebuilt": rebuilt, "seconds": time.perf_counter()-started}
    if args.stills_only:
        export_stills(data, output)
        write_json(output / "coverage.json", data["coverage"])
        return
    if args.verify_only:
        report = verify(data, video, output, full=args.final)
    else:
        # Publish only after audit: an interrupted/failed export keeps the last video.
        with tempfile.TemporaryDirectory(prefix=".render-", dir=output) as folder:
            staging = Path(folder)
            started = time.perf_counter()
            compose = FrameRenderer(data)
            initialization = time.perf_counter()-started
            export_stills(data, staging, compose)
            performance = render_video(data, staging / video.name, compose, crf=18 if args.final else 23)
            performance["initialization_seconds"] = initialization
            report = verify(data, staging / video.name, staging, full=args.final, compose=compose)
            report.update(video=str(video), performance=performance, preparation=preparation)
            write_json(staging / "verification.json", report)
            write_json(staging / "coverage.json", data["coverage"])
            for artifact in staging.iterdir():
                # Copy content into this folder before replacing: Windows must not
                # retain TemporaryDirectory's owner-only permissions on exports.
                incoming = output / (artifact.name+".tmp")
                shutil.copyfile(artifact, incoming)
                incoming.replace(output / artifact.name)
    print(f"Video audit: {report['status']} ({report['frames_compared']} frames, {report.get('mode', 'quick')} audit). {video}", flush=True)


if __name__ == "__main__":
    main()
