"""Collect national timetable snapshots and enumerate a day; never render or call RailRadar."""
import argparse
from collections import Counter, defaultdict
import csv
from datetime import date, datetime, timedelta, timezone
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import struct
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parent / "assets" / "schedules"
WEEK = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
RAILRAAG = "https://raw.githubusercontent.com/shwetankg07/RailRaag/656f4d7db73d9d89ef2393377bd29987940d2cbc/"
ADDITIONAL = "https://raw.githubusercontent.com/prasenjit-27/Indian-Railway-Data/1dc0ddbc6a06b09ef69d4825ff3127c1f29640fa/"
SOURCES = {
    "gtfs.zip": "https://raw.githubusercontent.com/Neo2308/indianrailways-gtfs/b340b7048e99c18330ad333e8210d61161ac7a43/gtfs/gtfs.zip",
    "gtfs-README.txt": "https://raw.githubusercontent.com/Neo2308/indianrailways-gtfs/b340b7048e99c18330ad333e8210d61161ac7a43/README.md",
    "railraag-trains.bin": RAILRAAG + "public/data/trains.bin",
    "railraag-meta.json.gz": RAILRAAG + "public/data/trains-meta.json",
    "railraag-stations.json.gz": RAILRAAG + "public/data/stations.json",
    "railraag-build-report.json.gz": RAILRAAG + "pipeline/build-report-v2.json",
    "railraag-LICENSE.txt": RAILRAAG + "LICENSE",
    "additional-trains.json.gz": ADDITIONAL + "trains.json",
    "additional-LICENSE.txt": ADDITIONAL + "LICENSE",
}


def read_json(path):
    return json.loads(gzip.decompress(path.read_bytes()))


def save_json(path, value):
    raw = json.dumps(value, ensure_ascii=False, indent=2 if path.suffix != ".gz" else None,
                     separators=(",", ":") if path.suffix == ".gz" else None).encode("utf-8")
    path.write_bytes(gzip.compress(raw, mtime=0) if path.suffix == ".gz" else raw + b"\n")


def clock(value):
    hours, minutes, seconds = map(int, value.split(":"))
    if hours < 0 or not 0 <= minutes < 60 or not 0 <= seconds < 60:
        raise ValueError("Invalid timetable time")
    return hours*3600 + minutes*60 + seconds


def record(number, name, kind, source, days, stops, **extra):
    return dict(number=number, name=name, service_type=kind, source=source, run_days=days, stops=stops, **extra)


def read_gtfs(directory, stations):
    with zipfile.ZipFile(directory / "gtfs.zip") as archive:
        def rows(name):
            return list(csv.DictReader(io.StringIO(archive.read(name).decode("utf-8-sig"))))
        calendars = {row["service_id"]: row for row in rows("calendar.txt")}
        routes = {row["route_id"]: row for row in rows("routes.txt")}
        times = defaultdict(list)
        for row in rows("stops.txt"):
            stations[row["stop_id"]] = dict(name=row["stop_name"], latitude=float(row["stop_lat"]) if row["stop_lat"] else None,
                                            longitude=float(row["stop_lon"]) if row["stop_lon"] else None)
        for row in rows("stop_times.txt"):
            times[row["trip_id"]].append(dict(station=row["stop_id"], sequence=int(row["stop_sequence"]),
                arrival=clock(row["arrival_time"]), departure=clock(row["departure_time"]), distance_km=row["shape_dist_traveled"]))
        trains = []
        for trip in rows("trips.txt"):
            route, calendar = routes[trip["route_id"]], calendars.get(trip["service_id"])
            if calendar is None:
                trains.append(record(route["route_short_name"], route["route_long_name"], "unclassified", "gtfs", [],
                                     times[trip["trip_id"]], missing_service_calendar=trip["service_id"]))
                continue
            trains.append(record(route["route_short_name"], route["route_long_name"], "unclassified", "gtfs",
                [day for day in WEEK if calendar[{"mon":"monday", "tue":"tuesday", "wed":"wednesday", "thu":"thursday", "fri":"friday", "sat":"saturday", "sun":"sunday"}[day]] == "1"],
                sorted(times[trip["trip_id"]], key=lambda x: x["sequence"]),
                valid_from=date.fromisoformat(calendar["start_date"]).isoformat(),
                valid_until=date.fromisoformat(calendar["end_date"]).isoformat()))
        return trains, rows("feed_info.txt")[0]


def read_railraag(directory, stations):
    meta = read_json(directory / "railraag-meta.json.gz")
    places = read_json(directory / "railraag-stations.json.gz")
    for station in places:
        stations.setdefault(station["c"], dict(name=station["n"], latitude=station["y"], longitude=station["x"]))
    data = (directory / "railraag-trains.bin").read_bytes()
    magic, count, stop_count, _ = struct.unpack_from("<IIII", data)
    if magic != 0x45544932 or count != len(meta):
        raise ValueError("Unexpected RailRaag binary format")
    offset, trains, read_stops = 16, [], 0
    for train in meta:
        size, category, days, km, first, last, reserved = struct.unpack_from("<HBBHHHH", data, offset)
        offset += 12
        stops = []
        for sequence in range(size):
            station, arrival, departure = struct.unpack_from("<HHH", data, offset)
            offset += 6
            stops.append(dict(station=places[station]["c"], sequence=sequence+1, arrival=arrival*60, departure=departure*60))
        read_stops += size
        trains.append(record(train["no"], train["n"], train["t"], "railraag",
            [day for index, day in enumerate(WEEK) if days & (1 << ((index+1) % 7))], stops,
            calendar_inferred_by_upstream=True))
    if offset != len(data) or read_stops != stop_count:
        raise ValueError("Truncated or trailing RailRaag binary data")
    return trains


def read_additional(directory, stations):
    trains = []
    for train in read_json(directory / "additional-trains.json.gz"):
        stops = []
        for stop in train["completeOrderedRoute"]:
            arrival, departure = stop["arrivalTime"], stop["departureTime"]
            if arrival is None:
                arrival = departure
            if departure is None:
                departure = arrival
            base = (int(stop["journeyDay"])-1)*86400
            stops.append(dict(station=stop["stationCode"], sequence=stop["sequence"],
                arrival=base+clock(arrival) if arrival else -1, departure=base+clock(departure) if departure else -1,
                distance_km=stop["distance"]))
            stations.setdefault(stop["stationCode"], dict(name=stop["stationName"], latitude=None, longitude=None))
        trains.append(record(train["trainNumber"], train["trainName"], train["type"], "additional",
            [day for day in WEEK if train["runningDays"].get(day.upper())], stops))
    return trains


def issues(train):
    stops = train["stops"]
    if not re.fullmatch(r"\d{5}", train["number"]) or len(stops) < 2 or not train["run_days"]:
        return "Invalid identity, missing timetable or operating days"
    if any(s["arrival"] < 0 or s["departure"] < s["arrival"] for s in stops):
        return "Invalid arrival/departure chronology"
    if any(b["arrival"] < a["departure"] for a, b in zip(stops, stops[1:])):
        return "Nonmonotonic stop times; source not silently repaired"
    duration = stops[-1]["arrival"]-stops[0]["departure"]
    if not 0 < duration <= 7*86400:
        return "Nonpositive or implausible passenger journey duration (over seven days)"
    return None


def day_journeys(train, target):
    """Weekly schedule projection; include earlier origin dates, never assume daily."""
    first, last = train["stops"][0]["departure"], train["stops"][-1]["arrival"]
    for days_back in range(last//86400+1):
        origin = target - timedelta(days=days_back)
        if WEEK[origin.weekday()] not in train["run_days"]:
            continue
        if train.get("valid_from") and not train["valid_from"] <= origin.isoformat() <= train["valid_until"]:
            continue
        start, end = first-days_back*86400, last-days_back*86400
        if start < 86400 and end > 0:
            yield dict(id=f"{train['number']}@{origin.isoformat()}", number=train["number"], origin_date=origin.isoformat(),
                departure_seconds=start, arrival_seconds=end, window_start=max(0, start), window_end=min(86400, end),
                source=train["source"], date_certified=False)


def collect(target, download=False):
    directory = ROOT / "sources"
    directory.mkdir(parents=True, exist_ok=True)
    if download:
        for name, url in SOURCES.items():
            path = directory / name
            if not path.exists():
                with urllib.request.urlopen(url, timeout=120) as response:
                    raw = response.read()
                path.write_bytes(gzip.compress(raw, mtime=0) if name.endswith(".gz") else raw)
    missing = [name for name in SOURCES if not (directory / name).exists()]
    if missing:
        raise RuntimeError(f"Missing snapshots; use --download: {missing}")
    stations = {}
    gtfs, feed = read_gtfs(directory, stations)
    variants = defaultdict(list)
    rejected, freight = [], []
    inputs = gtfs + read_railraag(directory, stations) + read_additional(directory, stations)
    parcel_numbers = {t["number"] for t in inputs if t["source"] == "railraag" and t["service_type"] == "Premium Express"}
    for train in inputs:
        if reason := issues(train):
            rejected.append(dict(number=train["number"], source=train["source"], reason=reason))
        elif train["number"] in parcel_numbers or re.search(r"\b(PARCEL|CARGO|FREIGHT|GOODS)\b", train["name"].upper()):
            freight.append(dict(number=train["number"], source=train["source"], name=train["name"]))
        else:
            variants[train["number"]].append(train)
    trains, differences = [], []
    for number, choices in sorted(variants.items()):
        train = choices[0]  # GTFS first, then RailRaag, then the additional snapshot.
        train["sources_available"] = [c["source"] for c in choices]
        if train["service_type"] == "unclassified":
            train["service_type"] = next((c["service_type"] for c in choices[1:]), "unclassified")
        endpoints = lambda c: (c["stops"][0]["station"], c["stops"][-1]["station"], c["stops"][0]["departure"], c["stops"][-1]["arrival"], tuple(c["run_days"]))
        if any(endpoints(c) != endpoints(train) for c in choices[1:]):
            differences.append(number)
        trains.append(train)
    journeys = [j for train in trains if train["source"] != "additional" for j in day_journeys(train, target)]
    review_journeys = [j for train in trains if train["source"] == "additional" for j in day_journeys(train, target)]
    save_json(ROOT / "trains.json.gz", trains)
    save_json(ROOT / "stations.json.gz", stations)
    save_json(ROOT / f"journeys-{target}.json.gz", journeys)
    save_json(ROOT / f"review-only-journeys-{target}.json.gz", review_journeys)
    by_number = {t["number"]:t for t in trains}
    midnight = datetime.combine(target, datetime.min.time(), timezone(timedelta(hours=5, minutes=30)))
    columns = ["number", "name", "service_type", "origin_date", "from_station", "to_station",
               "scheduled_departure_ist", "scheduled_arrival_ist", "source", "date_certified"]
    with (ROOT / f"journeys-{target}.csv").open("w", encoding="utf-8", newline="") as table:
        writer = csv.DictWriter(table, fieldnames=columns)
        writer.writeheader()
        for journey in journeys:
            train = by_number[journey["number"]]
            writer.writerow(dict(number=train["number"], name=train["name"], service_type=train["service_type"],
                origin_date=journey["origin_date"], from_station=train["stops"][0]["station"], to_station=train["stops"][-1]["station"],
                scheduled_departure_ist=(midnight+timedelta(seconds=journey["departure_seconds"])).isoformat(),
                scheduled_arrival_ist=(midnight+timedelta(seconds=journey["arrival_seconds"])).isoformat(),
                source=journey["source"], date_certified=False))
    coverage = dict(target_date=str(target), timezone="Asia/Kolkata", scope="Indian Railways passenger including suburban/local",
        basis="Weekly timetable projection, not actual operations or historical certification", complete_national_coverage=False,
        historical_date_certified=False, input_records=dict(Counter(t["source"] for t in inputs)),
        train_schedules=len(trains), scheduled_journey_candidates=len(journeys), stations=len(stations),
        undated_supplemental_train_schedules=sum(t["source"] == "additional" for t in trains),
        review_only_journey_candidates=len(review_journeys),
        origin_dates=dict(Counter(j["origin_date"] for j in journeys)),
        hourly_candidate_activity={f"{hour:02d}:00":sum(j["window_start"] <= hour*3600 < j["window_end"] for j in journeys) for hour in range(24)},
        service_types=dict(Counter(t["service_type"] for t in trains)), selected_sources=dict(Counter(t["source"] for t in trains)),
        source_disagreement_numbers=differences, rejected_records=rejected, excluded_freight_records=freight,
        no_target_day_candidate=[t["number"] for t in trains if not list(day_journeys(t, target))],
        gtfs_feed_info=feed, upstream_railraag_build=read_json(directory / "railraag-build-report.json.gz"),
        limitations=["Snapshots are not a complete verified national roster for the requested date.",
            "GTFS feed-wide validity ends before the target date, although some service calendars extend beyond it.",
            "RailRaag reduces run dates to weekday masks and defaults missing calendars to daily; exact validity is lost.",
            "RailRaag drops unplaced stations and some trains; its PEXP label is not reliable for passenger classification.",
            "Additional snapshot has weekday flags but no effective date range.",
            "Additional-only records are retained for review and excluded from the default dated projection.",
            "Special services, cancellations, timetable changes and remaining non-passenger misclassifications need review."])
    save_json(ROOT / "coverage.json", coverage)
    provenance = dict(prepared_at=datetime.now(timezone.utc).isoformat(), target_date=str(target),
        selection="All valid available timetable records; no geographic or train-count sampling",
        precedence=["gtfs", "railraag", "additional"], sources={name:dict(url=url,
            stored_sha256=hashlib.sha256((directory / name).read_bytes()).hexdigest(),
            stored_bytes=(directory / name).stat().st_size,
            local_snapshot_saved_at=datetime.fromtimestamp((directory / name).stat().st_mtime, timezone.utc).isoformat()) for name, url in SOURCES.items()},
        licenses={"gtfs":"No explicit dataset license found; upstream notices retained. Redistribution rights not established.",
            "railraag":"Upstream license claims CC0 timetable data, but build code says NTES; provenance inconsistency retained.",
            "additional":"MIT; see sources/additional-LICENSE.txt"})
    save_json(ROOT / "provenance.json", provenance)
    print(json.dumps({k:coverage[k] for k in ("target_date", "train_schedules", "scheduled_journey_candidates", "stations", "complete_national_coverage")}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", type=date.fromisoformat, default=date(2026, 10, 15))
    parser.add_argument("--download", action="store_true", help="Download missing pinned public snapshots once")
    args = parser.parse_args()
    collect(args.date, args.download)
