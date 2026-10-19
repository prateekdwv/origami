"""Offline preparation using ONLY timestamped actual station events."""
import hashlib
import json
from datetime import datetime

import numpy as np

from geography import boundary_hash, pixels, project
from settings import CATEGORIES, DAY, END, START, classify, timestamp
from store import write_json

def route_arrays(journey):
    return np.asarray(journey["route_pixels"]), np.asarray(journey["distances"])


def merge_observations(responses, item):
    """Keep known actuals when a later response contains null, applying explicit corrections."""
    stops, metadata, issues = {}, {}, []
    for wrapper in responses:
        data = wrapper["payload"]["data"]
        retrieved = timestamp(wrapper["retrieved_at"])
        if not isinstance(data, dict) or str(data.get("trainNumber")) != item["number"] or data.get("startDate") != item["start_date"]:
            issues.append("wrong journey identity in response")
            continue
        if not isinstance(data.get("route"), list) or any(not isinstance(row, dict) for row in data["route"]):
            issues.append("invalid station observation schema")
            continue
        metadata = data
        if data.get("exceptions"):
            # Without verified diversion geometry, don't draw through the original route.
            issues.append("operational exception: requires manual route review")
            return None, issues
        if str(data.get("status", "")).lower() in ("cancelled", "canceled"):
            return None, issues + ["journey cancelled"]
        for row in data.get("route", []):
            if "sequence" not in row or not row.get("stationCode"):
                continue
            try:
                key = (int(row["sequence"]), str(row["stationCode"]))
            except (ValueError, TypeError, OverflowError):
                issues.append("invalid station sequence")
                continue
            target = stops.setdefault(key, {})
            target.update({k: v for k, v in row.items() if v is not None and k not in ("actualArrival", "actualDeparture")})
            if str(row.get("status", "")).lower() in ("upcoming", "scheduled", "predicted", "expected") or row.get("isActual") is False:
                if row.get("actualArrival") or row.get("actualDeparture"):
                    issues.append(f'{key[1]}: actual-labelled values contradict unobserved status; ignored')
                continue
            for field in ("actualArrival", "actualDeparture"):
                actual = timestamp(row.get(field))
                if actual is not None and retrieved is not None and actual <= retrieved:
                    target[field] = actual.isoformat()
                elif row.get(field) is not None:
                    issues.append(f'{key[1]}: invalid, undated, or future {field}')
    if not metadata:
        return None, issues
    rows = [stops[key] for key in sorted(stops)]
    train = metadata.get("train") or {}
    if not isinstance(train, dict):
        return None, issues + ["invalid train metadata"]
    name = metadata.get("trainName") or train.get("name", item["name"])
    category = classify(name, str(train.get("type", "")) + " " + str(train.get("category", "")))
    if category is None:
        return None, issues + ["unclassified or non-passenger service"]
    return {"id": item["id"], "name": name, "category": category, "stops": rows}, issues


def station_measures(line, stops):
    """Snap sequential stops to ordered track segments, including revisited stations."""
    vectors = np.diff(line, axis=0)
    lengths = np.linalg.norm(vectors, axis=1)
    cumulative = np.r_[0, np.cumsum(lengths)]
    previous = 0.0
    measures = []
    for row in stops:
        if row.get("lat") is None or row.get("lng") is None:
            measures.append(None)
            continue
        point = project([[row["lng"], row["lat"]]])[0]
        fractions = np.clip(((point-line[:-1])*vectors).sum(axis=1)/np.maximum(lengths**2, 1e-12), 0, 1)
        locations = line[:-1] + fractions[:, None]*vectors
        errors = np.linalg.norm(locations-point, axis=1)
        along = cumulative[:-1] + fractions*lengths
        possible = np.flatnonzero((along >= previous-0.1) & (errors < 2500) & (lengths > 0))
        if not len(possible):
            measures.append(None)
            continue
        # Timetable distances disambiguate a station revisited after a loop/reversal;
        # they never supply time or synthesize track geometry.
        expected = float(row.get("distance", 0)) * 1000
        if expected > 0 and float(stops[-1].get("distance", 0)) > 0:
            expected *= cumulative[-1] / (float(stops[-1]["distance"])*1000)
        else:
            expected = previous
        best_error = errors[possible].min()
        nearest = possible[errors[possible] <= best_error+50]
        chosen = nearest[np.argmin(np.abs(along[nearest]-expected))]
        previous = float(along[chosen])
        measures.append(previous)
    return measures, cumulative


def prepare_journey(journey, route_payload):
    if not isinstance(route_payload.get("data"), dict):
        return None, ["invalid geometry response schema"]
    if str(route_payload.get("data", {}).get("trainNumber", "")) != journey["id"].split("@")[0]:
        return None, ["route geometry has wrong train identity"]
    feature = route_payload.get("data", {}).get("geojson", {})
    if not isinstance(feature, dict) or not isinstance(feature.get("geometry"), dict):
        return None, ["invalid GeoJSON feature"]
    geometry = feature.get("geometry", {})
    if geometry.get("type") != "LineString":
        return None, ["missing verified LineString geometry"]
    coordinates = geometry.get("coordinates", [])
    if len(coordinates) < 2:
        return None, ["empty route geometry"]
    line = project(coordinates)
    # Reuse station metadata shipped with the cached route if live rows omit GPS.
    metadata = {(str(row.get("code", row.get("stationCode", ""))), row.get("sequence")): row
                for row in route_payload.get("data", {}).get("stops", [])}
    stops = []
    for original in journey["stops"]:
        row = dict(original)
        source = metadata.get((row["stationCode"], row["sequence"]), {})
        for coordinate in ("lat", "lng"):
            if row.get(coordinate) is None and source.get(coordinate) is not None:
                row[coordinate] = source[coordinate]
        stops.append(row)
    if len(stops) < 2:
        return None, ["fewer than two observed stops"]
    measures, cumulative = station_measures(line, stops)
    issues, segments = [], []

    def add(a, b, sa, sb, kind):
        if a is None or b is None or sa is None or sb is None:
            return False
        if b <= a or sb < sa or a < datetime.fromisoformat(journey["id"].split("@")[1]).replace(tzinfo=START.tzinfo):
            return False
        if kind == "travel" and (sb <= sa or (sb-sa) / (b-a).total_seconds() > 350/3.6):
            return False
        left, right = max(a, START), min(b, END)
        if right <= left:
            return True
        duration = (b-a).total_seconds()
        segments.append({"start": (left-START).total_seconds(), "end": (right-START).total_seconds(),
                         "from": sa+(sb-sa)*(left-a).total_seconds()/duration,
                         "to": sa+(sb-sa)*(right-a).total_seconds()/duration, "kind": kind})
        return True

    for i, row in enumerate(stops):
        arrival, departure = timestamp(row.get("actualArrival")), timestamp(row.get("actualDeparture"))
        add(arrival, departure, measures[i], measures[i], "dwell")
        if i+1 < len(stops):
            following = timestamp(stops[i+1].get("actualArrival"))
            if not add(departure, following, measures[i], measures[i+1], "travel"):
                issues.append(f'{row["stationCode"]} → {stops[i+1]["stationCode"]}: missing/invalid actual timing or route alignment')
    segments.sort(key=lambda x: x["start"])
    if any(b["start"] < a["end"] for a, b in zip(segments, segments[1:])):
        return None, issues + ["conflicting chronological observations"]
    if not segments or not any(s["kind"] == "travel" for s in segments):
        return None, issues + ["no usable movement inside the day"]
    # Preserve only the source geometry; never connect station dots with straight lines.
    return {"id": journey["id"], "name": journey["name"], "category": journey["category"],
            "route_pixels": pixels(line).tolist(), "distances": cumulative.tolist(), "segments": segments}, issues


def position(journey, second, arrays=None):
    for segment in journey["segments"]:
        if segment["start"] <= second < segment["end"]:
            alpha = (second-segment["start"])/(segment["end"]-segment["start"])
            distance = segment["from"] + alpha*(segment["to"]-segment["from"])
            points, distances = arrays if arrays is not None else route_arrays(journey)
            return np.array([np.interp(distance, distances, points[:, axis]) for axis in (0, 1)])
    return None


def active_counts(journeys, second, categories=CATEGORIES):
    counts = dict.fromkeys(categories, 0)
    for journey in journeys:
        if any(s["start"] <= second < s["end"] for s in journey["segments"]):
            counts[journey["category"]] += 1
    return counts


def prepare(store):
    destination = store.root / "prepared.json"
    if destination.exists():
        from replay import load_prepared
        return load_prepared(store.root)
    if store.manifest["passes"].get("completion") != "finished":
        raise RuntimeError("Completion pass must finish before freezing the replay")
    journeys, exclusions, sources = [], [], []
    for item in store.manifest["selection"]:
        records = store.successful("live", item["id"])
        wrappers = []
        for record in records:
            path = store.root / record["file"]
            wrappers.append(json.loads(path.read_text(encoding="utf-8")))
            sources.append({"file": record["file"], "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        journey, issues = merge_observations(wrappers, item)
        geometry = store.successful("geometry", item["number"])
        if journey and geometry:
            record = geometry[-1]
            path = store.root / record["file"]
            sources.append({"file": record["file"], "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
            try:
                journey, more = prepare_journey(journey, store.response(record))
            except (ValueError, TypeError, KeyError, OverflowError):
                journey, more = None, ["invalid route or station coordinate schema"]
            issues.extend(more)
        else:
            journey = None
            issues.append("missing observation or geometry response")
        exclusions.append({"id": item["id"], "included": bool(journey), "issues": issues})
        if journey:
            journeys.append(journey)
    category_counts = {category: sum(j["category"] == category for j in journeys) for category in CATEGORIES}
    report = {"selected": len(store.manifest["selection"]), "included": len(journeys), "records": exclusions,
              "category_journeys": category_counts,
              "not_represented": [CATEGORIES[c][0] for c, count in category_counts.items() if not count],
              "requests_consumed": len(store.manifest["requests"]),
              "still_pending_after_completion": [j["id"] for j in store.manifest["selection"] if not j["complete"]],
              "selection": [{k: j.get(k) for k in ("id", "name", "category", "region_hint", "start_date")}
                            for j in store.manifest["selection"]]}
    write_json(store.root / "coverage.json", report)
    if not journeys:
        raise RuntimeError("No verified movements can be prepared; see data/coverage.json")
    prepared = {"version": 1, "date": DAY, "timezone": "Asia/Kolkata", "boundary_sha256": boundary_hash(),
                "basis": "recorded station timings; interpolated positions; representative sample",
                "journeys": journeys, "sources": sources, "coverage": report,
                "activity": [sum(active_counts(journeys, second).values()) for second in range(0, 86401, 300)]}
    # Stage atomically; persist its expected hash before publishing the frozen file.
    staged = store.root / "prepared.staged.json"
    write_json(staged, prepared)
    store.manifest["frozen_sha256"] = hashlib.sha256(staged.read_bytes()).hexdigest()
    store.save()
    staged.replace(destination)
    return prepared
