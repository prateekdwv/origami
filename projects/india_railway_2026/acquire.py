"""Two bounded RailRadar passes; no polling and no renderer network access."""
from datetime import datetime, timedelta, timezone
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from settings import CATEGORIES, COMPLETION, DAY, END, IST, START, classify, timestamp
from store import write_json


class CollectionStopped(RuntimeError):
    pass

class BudgetReached(CollectionStopped):
    pass

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None  # Never forward the authorization header to another origin.


def transport(url, key):
    request = urllib.request.Request(url, headers={"Authorization": "Bearer " + key, "Accept": "application/json"})
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=35) as response:
            return response.status, response.headers, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.headers, b""  # Do not persist echoed headers or error text.


class Client:
    def __init__(self, store, phase, key, remaining=None, send=transport, clock=time.time, sleep=time.sleep):
        if not key:
            raise CollectionStopped("RAILRADAR_API_KEY is not configured; no API requests made")
        if store.manifest.get("halt"):
            raise CollectionStopped("Account access/quota halted collection. Resolve the saved halt before any further requests")
        self.store, self.phase, self.key = store, phase, key
        self.send, self.clock, self.sleep = send, clock, sleep
        used = len(store.manifest["requests"])
        if remaining is not None:
            if remaining < 0:
                raise ValueError("Remaining quota must be nonnegative")
            store.manifest["budget_total"] = min(store.manifest["budget_total"], used + max(0, remaining-10), 90)

    def get(self, kind, identity, path, params=None, refresh=False):
        records = self.store.manifest["requests"]
        cached = self.store.successful(kind, identity)
        if cached and (not refresh or cached[-1]["phase"] == self.phase):
            return self.store.response(cached[-1])
        if any(r["kind"] == kind and r["identity"] == identity and r["phase"] == self.phase for r in records):
            return None  # Failed/inflight attempts are not repeated within a pass.
        limit = {"initial": 40, "completion": 50}[self.phase]
        if sum(r["phase"] == self.phase for r in records) >= limit or len(records) >= self.store.manifest["budget_total"]:
            raise BudgetReached("Request budget reached; pending records are saved for inspection")
        if records:
            self.sleep(max(0, 7 - (self.clock() - records[-1]["epoch"])))
        params = params or {}
        number = len(records) + 1
        record = {"kind": kind, "identity": identity, "phase": self.phase, "path": path,
                  "params": params, "epoch": self.clock(), "status": "inflight",
                  "file": f"raw/{number:03d}.json"}
        records.append(record)
        self.store.save()  # Count the attempt BEFORE the request, including uncertain crashes.
        url = "https://api.railradar.in/v1" + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        try:
            status, headers, body = self.send(url, self.key)
            record["http_status"] = status
            # A generic rate-limit header may describe a minute, not a month.
            allowance = headers.get("X-Monthly-RateLimit-Remaining")
            if allowance is not None and str(allowance).isdigit():
                self.store.manifest["budget_total"] = min(self.store.manifest["budget_total"], len(records) + max(0, int(allowance)-10))
            if status in (401, 403, 429):
                record["status"] = "auth_failed" if status != 429 else "rate_limited"
                self.store.manifest["halt"] = record["status"]
                raise CollectionStopped(f"HTTP {status}: stopped; check account access/quota before resuming")
            if status != 200:
                record["status"] = "http_failed"
                return None
            # Defensive redaction if the provider unexpectedly echoes a secret.
            payload = json.loads(body.decode().replace(self.key, "[REDACTED]"))
            if not isinstance(payload, dict) or payload.get("success") is not True or not isinstance(payload.get("data"), (dict, list)):
                record["status"] = "invalid_response"
                return None
            write_json(self.store.root / record["file"], {
                "retrieved_at": datetime.fromtimestamp(self.clock(), timezone.utc).isoformat(),
                "path": path, "params": params, "payload": payload,
            })
            record["status"] = "ok"
            return payload
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            record["status"] = "network_or_decode_failed"
            return None
        finally:
            self.store.save()


def select_sample(directory):
    """Balanced deterministic name-based shortlist, before observing any delays."""
    regions = {
        "northeast": ("GUWAHATI", "DIBRUGARH", "AGARTALA", "SILCHAR", "NAHARLAGUN"),
        "south": ("CHENNAI", "BENGALURU", "BANGALORE", "HYDERABAD", "SECUNDERABAD", "TRIVANDRUM", "MYSURU"),
        "east": ("HOWRAH", "KOLKATA", "PATNA", "RANCHI", "BHUBANESWAR", "PURI"),
        "west": ("MUMBAI", "AHMEDABAD", "JAIPUR", "PUNE", "SURAT"),
        "central": ("BHOPAL", "NAGPUR", "RAIPUR", "INDORE", "JABALPUR"),
        "north": ("DELHI", "JAMMU", "SRINAGAR", "LUCKNOW", "AMRITSAR", "CHANDIGARH"),
    }
    pools = {c: [] for c in CATEGORIES}
    for number, value in sorted(directory.items()):
        if not re.fullmatch(r"\d{5}", str(number)):
            continue
        name = value if isinstance(value, str) else value.get("name", "")
        category = classify(name)
        if category:
            region = next((r for r, words in regions.items() if any(w in name.upper() for w in words)), "unassigned")
            pools[category].append({"number": str(number), "name": name, "category": category, "region_hint": region})
    selected, region_counts = [], {}
    for round_index in range(4):
        for category, pool in pools.items():
            if not pool:
                continue
            pool.sort(key=lambda x: (x["region_hint"] == "unassigned", region_counts.get(x["region_hint"], 0), x["number"]))
            item = pool.pop(0).copy()
            region_counts[item["region_hint"]] = region_counts.get(item["region_hint"], 0) + 1
            # Half the long-distance sample began on the preceding day; one on day -2.
            offset = (1 if round_index % 2 == 0 else 0) if category in ("rajdhani", "express") else 0
            if category == "express" and round_index == 2:
                offset = 2
            item["start_date"] = (START - timedelta(days=offset)).date().isoformat()
            item["id"] = item["number"] + "@" + item["start_date"]
            item["complete"] = False
            selected.append(item)
    return selected


def valid_live(data, item):
    return (isinstance(data, dict) and str(data.get("trainNumber", "")) == item["number"] and data.get("startDate") == item["start_date"]
            and isinstance(data.get("route"), list) and all(isinstance(row, dict) for row in data["route"]))


def has_actual(data, now):
    return any(START <= t <= min(END, now) for row in data.get("route", [])
               if str(row.get("status", "")).lower() not in ("upcoming", "scheduled", "predicted", "expected") and row.get("isActual") is not False
               for field in ("actualArrival", "actualDeparture") if (t := timestamp(row.get(field))))


def complete_for_day(data, now=None):
    route = data.get("route", [])
    if str(data.get("status", "")).lower() in ("cancelled", "canceled"):
        return True
    # Do not refresh records only because the train is still running after our window.
    if len(route) < 2:
        return False
    if any(str(row.get("status", "")).lower() in ("upcoming", "scheduled", "predicted", "expected")
           or row.get("isActual") is False for row in route):
        return False
    if now and any(t > now for row in route for field in ("actualArrival", "actualDeparture")
                   if (t := timestamp(row.get(field)))):
        return False
    # A terminal status alone is not evidence that the intermediate records are complete.
    for index, row in enumerate(route):
        if index and timestamp(row.get("actualArrival")) is None:
            return False
        if (arrival := timestamp(row.get("actualArrival"))) and arrival >= END:
            return True
        if index < len(route)-1 and timestamp(row.get("actualDeparture")) is None:
            return False
        if (departure := timestamp(row.get("actualDeparture"))) and departure >= END:
            return True
    return str(data.get("status", "")).lower() in ("completed", "arrived", "terminated")


def run_collection(store, phase, remaining=None, now=None, client_factory=Client):
    now = now or datetime.now(IST)
    if (store.root / "prepared.json").exists() or store.manifest.get("frozen_sha256"):
        raise CollectionStopped("Dataset is frozen; collection will not alter it")
    if phase == "initial" and not START <= now < END:
        raise CollectionStopped("Initial collection is restricted to 10 October IST; use completion after the cutoff")
    if phase == "completion" and now < COMPLETION:
        raise CollectionStopped("Completion is not due until 11 October 2026 00:30 IST")
    client = client_factory(store, phase, os.environ.get("RAILRADAR_API_KEY", ""), remaining)
    state = store.manifest
    if state["passes"].get(phase) == "finished":
        return
    if state["gate"] == "failed":
        raise CollectionStopped("History feasibility failed. Inspect saved probe responses; no further automatic requests")
    if not state["selection"]:
        payload = client.get("directory", "trains", "/lookup/trains")
        if payload is None or not isinstance(payload["data"], dict):
            raise CollectionStopped("Train directory unavailable; no sample invented")
        state["selection"] = select_sample(payload["data"])
        store.save()
    if not state["selection"]:
        raise CollectionStopped("No classifiable passenger journeys found in the directory")
    # Probe up to three candidates, prioritizing overnight journeys likely to have observations.
    probes = sorted(state["selection"], key=lambda j: (j["start_date"], j["number"]))[:3]
    order = probes + [j for j in state["selection"] if j not in probes]
    for index, item in enumerate(order):
        if index == len(probes) and state["gate"] != "passed":
            state["gate"] = "failed"
            store.save()
            raise CollectionStopped("No valid actual timings found in three dated probes; stopped before broad collection")
        if item["complete"]:
            continue
        payload = client.get("live", item["id"], f'/trains/{item["number"]}/live',
                             {"date": item["start_date"], "includeCoordinates": "true", "haltsOnly": "true"}, refresh=phase == "completion")
        if payload is None:
            continue
        data = payload["data"]
        if not isinstance(data, dict) or not valid_live(data, item):
            item["issue"] = "wrong_journey_or_schema"
            store.save()
            continue
        if has_actual(data, now):
            state["gate"] = "passed"
        item["complete"] = complete_for_day(data, now)
        item["status"] = "complete" if item["complete"] else "pending"
        store.save()
    if state["gate"] != "passed":
        state["gate"] = "failed"
        store.save()
        raise CollectionStopped("No actual observations for the target day")
    for item in state["selection"]:
        records = store.successful("live", item["id"])
        if not records:
            continue
        if not any(valid_live(data := store.response(r)["data"], item) and has_actual(data, now) for r in records):
            continue
        client.get("geometry", item["number"], f'/trains/{item["number"]}/route', {"format": "geojson", "stops": "true"})
    state["passes"][phase] = "finished"
    store.save()


def collect_pass(store, phase, remaining=None, **kwargs):
    """A budget-limited pass is terminal, with missing records retained as gaps."""
    try:
        run_collection(store, phase, remaining, **kwargs)
    except BudgetReached:
        if store.manifest["gate"] != "passed":
            raise
        store.manifest["passes"][phase] = "finished"
        store.manifest.setdefault("pass_stop_reason", {})[phase] = "budget exhausted; gaps retained"
        store.save()
