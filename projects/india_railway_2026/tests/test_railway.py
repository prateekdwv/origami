"""Synthetic unit fixtures ONLY. No fixture is placed in the production dataset."""
import copy
from datetime import timedelta
import json
from pathlib import Path
import tempfile
import urllib.parse
import subprocess
import sys
import unittest
from unittest.mock import patch
import numpy as np

from acquire import Client, CollectionStopped, collect_pass, complete_for_day, run_collection, select_sample
from design import second_at
from geography import official_map, pixels, project
from model import active_counts, merge_observations, position, prepare, prepare_journey, station_measures
from settings import COMPLETION, END, START, timestamp
from store import Store, write_json

def fixture():
    item = {"id": "12345@2026-10-09", "number": "12345", "start_date": "2026-10-09", "name": "Test Express"}
    data = {"trainNumber": "12345", "startDate": "2026-10-09", "trainName": "Test Express", "status": "completed", "route": [
        {"sequence": 1, "stationCode": "A", "lng": 77., "lat": 25., "distance": 0,
         "actualDeparture": "2026-10-09T23:30:00+05:30"},
        {"sequence": 2, "stationCode": "B", "lng": 77.1, "lat": 25.1, "distance": 15,
         "actualArrival": "2026-10-10T00:30:00+05:30", "actualDeparture": "2026-10-10T00:45:00+05:30"},
        {"sequence": 3, "stationCode": "C", "lng": 77.2, "lat": 25.2, "distance": 30,
         "actualArrival": "2026-10-10T01:30:00+05:30"}]}
    wrapper = {"retrieved_at": "2026-10-11T00:30:00+05:30", "payload": {"success": True, "data": data}}
    geometry = {"data": {"trainNumber": "12345", "geojson": {"type": "Feature", "geometry": {
        "type": "LineString", "coordinates": [[77, 25], [77.05, 25.08], [77.1, 25.1], [77.16, 25.12], [77.2, 25.2]]}}}}
    return item, wrapper, geometry

class CacheTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(Path(self.tmp.name))
        self.now, self.calls = [START.timestamp()+3600], []
        def send(url, key):
            self.calls.append((url, self.now[0]))
            return 200, {}, json.dumps({"success": True, "data": {"value": len(self.calls)}}).encode()
        self.send = send
    def client(self, phase="initial", remaining=None, send=None):
        return Client(self.store, phase, "test-secret", remaining, send=send or self.send,
                      clock=lambda: self.now[0], sleep=lambda n: self.now.__setitem__(0, self.now[0]+n))
    def test_cached_success_and_seven_second_spacing(self):
        c = self.client()
        first = c.get("live", "a", "/one")
        self.assertEqual(first, c.get("live", "a", "/one"))
        c.get("geometry", "a", "/two")
        self.assertEqual(len(self.calls), 2)
        self.assertGreaterEqual(self.calls[1][1]-self.calls[0][1], 7)
    def test_completion_preserves_versions(self):
        self.client().get("live", "a", "/one")
        c = self.client("completion")
        c.get("live", "a", "/one", refresh=True)
        c.get("live", "a", "/one", refresh=True)
        records = self.store.successful("live", "a")
        self.assertEqual(len(records), 2)
        self.assertEqual(self.store.response(records[0])["data"]["value"], 1)
    def test_phase_and_combined_budgets(self):
        for phase, count in (("initial", 40), ("completion", 50)):
            c = self.client(phase)
            for i in range(count):
                c.get("live", f"{phase}{i}", "/one")
            with self.assertRaises(CollectionStopped):
                c.get("live", "overflow", "/one")
        self.assertEqual(len(self.calls), 90)
    def test_lower_quota_reserves_ten(self):
        c = self.client(remaining=11)
        c.get("live", "a", "/one")
        with self.assertRaises(CollectionStopped):
            c.get("live", "b", "/two")
    def test_auth_and_quota_failures_count_and_halt(self):
        for status in (401, 403, 429):
            self.store.manifest.pop("halt", None)
            c = self.client(send=lambda *a: (status, {}, b""))
            with self.assertRaises(CollectionStopped):
                c.get("live", str(status), "/one")
            with self.assertRaises(CollectionStopped):
                self.client()
        self.assertEqual(len(self.store.manifest["requests"]), 3)
    def test_no_key_no_attempt(self):
        with self.assertRaises(CollectionStopped):
            Client(self.store, "initial", "")
        self.assertEqual(self.store.manifest["requests"], [])
    def test_crash_after_response_recovers(self):
        self.client().get("live", "a", "/one")
        self.store.manifest["requests"][0]["status"] = "inflight"
        self.store.save()
        with self.store.locked():
            self.client().get("live", "a", "/one")
        self.assertEqual(len(self.calls), 1)
    def test_failure_not_retried_in_same_pass(self):
        c = self.client(send=lambda *a: (503, {}, b""))
        c.get("live", "a", "/one")
        c.get("live", "a", "/one")
        self.assertEqual(len(self.store.manifest["requests"]), 1)
        self.client("completion").get("live", "a", "/one", refresh=True)
        self.assertEqual(len(self.store.manifest["requests"]), 2)
    def test_secret_redacted(self):
        c = self.client(send=lambda *a: (200, {}, b'{"success":true,"data":{"echo":"test-secret"}}'))
        c.get("live", "a", "/one")
        self.assertNotIn("test-secret", (self.store.root / "raw/001.json").read_text())
    def test_directory_diagnostic_preserves_failure_and_caches_success(self):
        failed = self.client("completion", send=lambda *a: (400, {}, b'{"error":{"code":"BAD_REQUEST","message":"Invalid request"}}'))
        failed.get("directory", "trains", "/lookup/trains")
        original = copy.deepcopy(self.store.manifest["requests"][0])
        client = self.client("completion")
        self.assertIsNone(client.get("directory", "trains", "/lookup/trains"))
        payload = client.get("directory", "trains", "/lookup/trains", retry_directory=True)
        self.assertIsNotNone(payload)
        self.assertEqual(len(self.store.manifest["requests"]), 2)
        self.assertEqual(self.store.manifest["requests"][0], original)
        self.assertEqual(payload, client.get("directory", "trains", "/lookup/trains"))
        self.assertEqual(len(self.store.manifest["requests"]), 2)

    def test_error_diagnostic_redacts_secrets_and_ignores_other_fields(self):
        body = json.dumps({"error": {"code": "BAD_REQUEST", "message": "test-secret rr_live_otherSecret Bearer another-secret",
                                    "headers": {"Authorization": "sensitive-header"}},
                           "debug": "sensitive-debug"}).encode()
        self.client(send=lambda *a: (400, {}, body)).get("directory", "trains", "/lookup/trains")
        saved = self.store.path.read_text(encoding="utf-8")
        for secret in ("test-secret", "rr_live_otherSecret", "another-secret", "sensitive-header", "sensitive-debug"):
            self.assertNotIn(secret, saved)
        self.assertEqual(self.store.manifest["requests"][0]["error"]["code"], "BAD_REQUEST")
        self.assertFalse((self.store.root / "raw/001.json").exists())

    def test_diagnostic_retry_honors_quota_and_rejects_other_requests(self):
        self.client("completion", send=lambda *a: (400, {}, b"")).get("directory", "trains", "/lookup/trains")
        with self.assertRaises(CollectionStopped):
            self.client("completion", remaining=10).get("directory", "trains", "/lookup/trains", retry_directory=True)
        self.assertEqual(len(self.store.manifest["requests"]), 1)
        with self.assertRaises(CollectionStopped):
            self.client("completion").get("live", "a", "/one", retry_directory=True)

    def test_bad_key_format_stops_before_any_request(self):
        for key in (" token", "token ", "Bearer token", '"token"', "token\n", "\u00e9token"):
            with self.subTest(key_format="invalid"), self.assertRaises(CollectionStopped):
                Client(self.store, "completion", key, send=self.send)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.store.manifest["requests"], [])

    def test_empty_and_unexpected_errors_are_explicit(self):
        from acquire import error_details
        self.assertIn("Empty", error_details(b"", "secret")["message"])
        self.assertIn("no recognized", error_details(b'{}', "secret")["message"])
        self.assertIn("Unexpected", error_details(b'[]', "secret")["message"])
        self.assertEqual(error_details(b'{"detail":"secret rejected"}', "secret")["detail"], "[REDACTED] rejected")

    def test_transport_sends_only_selected_auth_header(self):
        from acquire import transport, NoRedirect
        from unittest.mock import MagicMock
        for mode in ("bearer", "api-key"):
            response = MagicMock()
            response.__enter__.return_value = response
            response.status, response.headers = 200, {}
            response.read.return_value = b"{}"
            opener = MagicMock()
            opener.open.return_value = response
            with patch.dict("os.environ", {"RAILRADAR_AUTH_MODE": mode}), patch("acquire.urllib.request.build_opener", return_value=opener) as build:
                self.assertEqual(transport("https://api.railradar.in/v1/lookup/trains", "test-secret")[0], 200)
                build.assert_called_once_with(NoRedirect)
                request = opener.open.call_args.args[0]
                headers = {k.lower(): v for k, v in request.header_items()}
                if mode == "api-key":
                    self.assertEqual(headers["x-api-key"], "test-secret")
                    self.assertNotIn("authorization", headers)
                else:
                    self.assertEqual(headers["authorization"], "Bearer test-secret")
                    self.assertNotIn("x-api-key", headers)

    def test_invalid_auth_mode_uses_no_quota(self):
        with patch.dict("os.environ", {"RAILRADAR_AUTH_MODE": "invalid"}), self.assertRaises(CollectionStopped):
            self.client()
        self.assertEqual(self.store.manifest["requests"], [])

    def test_completion_cutoff(self):
        with self.assertRaisesRegex(CollectionStopped, "not due"):
            run_collection(self.store, "completion", now=END)

class ModelTests(unittest.TestCase):
    def setUp(self):
        self.item, self.wrapper, self.geometry = fixture()
    def prepared(self, wrapper=None):
        j, _ = merge_observations([wrapper or self.wrapper], self.item)
        return prepare_journey(j, self.geometry)[0]
    def test_midnight_clipping_and_stationary_dwell(self):
        j = self.prepared()
        self.assertEqual(j["segments"][0]["start"], 0)
        self.assertGreater(j["segments"][0]["from"], 0)
        np.testing.assert_allclose(position(j, 1900), position(j, 2600))
        self.assertEqual(sum(active_counts([j], 1900).values()), 1)
        self.assertIsNone(position(j, 5400))
    def test_end_midnight_clips_without_extrapolation(self):
        data = self.wrapper["payload"]["data"]
        data["route"][0]["actualDeparture"] = "2026-10-10T23:30:00+05:30"
        data["route"][1]["actualArrival"] = "2026-10-11T00:30:00+05:30"
        data["route"][1]["actualDeparture"] = None
        data["route"][2]["actualArrival"] = None
        j = self.prepared()
        self.assertEqual(j["segments"][0]["end"], 86400)
        self.assertIsNotNone(position(j, 86399))
        self.assertIsNone(position(j, 86400))
    def test_unresolved_last_segment_omitted(self):
        self.wrapper["payload"]["data"]["route"][2]["actualArrival"] = None
        j = self.prepared()
        self.assertIsNone(position(j, 3000))
    def test_schedule_and_prediction_never_substitute(self):
        row = self.wrapper["payload"]["data"]["route"][2]
        row["scheduledArrival"] = row.pop("actualArrival")
        row["expectedArrival"] = row["scheduledArrival"]
        self.assertIsNone(position(self.prepared(), 3000))
        row["actualArrival"], row["status"] = row["scheduledArrival"], "predicted"
        self.assertIsNone(position(self.prepared(), 3000))
    def test_null_update_preserves_earlier_actual(self):
        later = copy.deepcopy(self.wrapper)
        later["payload"]["data"]["route"][1]["actualArrival"] = None
        j, _ = merge_observations([self.wrapper, later], self.item)
        self.assertIsNotNone(j["stops"][1]["actualArrival"])
    def test_wrong_origin_date_is_not_observation_date(self):
        self.wrapper["payload"]["data"]["startDate"] = "2026-10-10"
        self.assertIsNone(merge_observations([self.wrapper], self.item)[0])
    def test_cached_station_metadata_supplies_missing_coordinates(self):
        rows = self.wrapper["payload"]["data"]["route"]
        self.geometry["data"]["stops"] = [{"code": r["stationCode"], "sequence": r["sequence"],
                                             "lat": r["lat"], "lng": r["lng"]} for r in rows]
        for row in rows:
            row.pop("lat")
            row.pop("lng")
        self.assertIsNotNone(self.prepared())
    def test_future_undated_naive_events_rejected(self):
        self.assertIsNone(timestamp("01:30"))
        self.assertIsNone(timestamp("2026-10-10T01:30"))
        self.wrapper["retrieved_at"] = "2026-10-10T00:40:00+05:30"
        j = self.prepared()
        self.assertIsNone(position(j, 3000))
    def test_diversion_and_wrong_geometry_rejected(self):
        self.wrapper["payload"]["data"]["exceptions"] = [{"type": "DIVERTED"}]
        self.assertIsNone(merge_observations([self.wrapper], self.item)[0])
        self.wrapper["payload"]["data"]["exceptions"] = []
        self.geometry["data"]["trainNumber"] = "99999"
        self.assertIsNone(self.prepared())
    def test_completed_status_with_missing_events_stays_pending(self):
        self.assertTrue(complete_for_day(self.wrapper["payload"]["data"]))
        self.wrapper["payload"]["data"]["route"][1]["actualDeparture"] = None
        self.assertFalse(complete_for_day(self.wrapper["payload"]["data"]))
    def test_return_to_same_station_uses_later_route_measure(self):
        line = project([[77, 25], [77.1, 25.1], [77, 25]])
        rows = [{"lng": 77, "lat": 25, "distance": 0},
                {"lng": 77.1, "lat": 25.1, "distance": 15},
                {"lng": 77, "lat": 25, "distance": 30}]
        measures, total = station_measures(line, rows)
        self.assertGreater(measures[-1], measures[1])
        self.assertAlmostEqual(measures[-1], total[-1])
    def test_uniform_clock(self):
        self.assertEqual([second_at(t) for t in (0, 3, 16.5, 30, 43.5, 57, 60)],
                         [0, 0, 21600, 43200, 64800, 86400, 86400])
    def test_render_network_guard(self):
        result = subprocess.run([sys.executable, "-c",
                                 "from offline import deny_network; import socket; deny_network(); socket.create_connection(('example.com',443))"],
                                cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("network access is disabled", result.stderr)
    def test_full_official_rings_and_projection(self):
        crs, bbox, rings = official_map()
        self.assertEqual(len(rings), 1151)
        self.assertEqual(sum(len(r) for r in rings), 629724)
        p = pixels(np.concatenate(rings))
        self.assertTrue(((p[:, 0] > 0) & (p[:, 0] < 1080) & (p[:, 1] > 266) & (p[:, 1] < 1400)).all())
    def test_selection_balances_categories_and_includes_overnight(self):
        names = ["Delhi Vande Bharat", "Guwahati Rajdhani", "Chennai Shatabdi", "Bhopal Intercity", "Mumbai Local", "Kolkata Express"]
        directory = {str(10000+i): names[i % 6] for i in range(24)}
        sample = select_sample(directory)
        self.assertEqual(len(sample), 24)
        self.assertEqual(len({j["category"] for j in sample}), 6)
        self.assertTrue(any(j["start_date"] < "2026-10-10" for j in sample))

class PassIntegrationTests(unittest.TestCase):
    setUp = CacheTests.setUp
    def directory(self):
        names = ["Delhi Vande Bharat", "Guwahati Rajdhani", "Chennai Shatabdi", "Bhopal Intercity", "Mumbai Local", "Kolkata Express"]
        return {str(10000+i): names[i % 6] for i in range(24)}
    def provider(self, url, key):
        self.calls.append((url, self.now[0]))
        parsed = urllib.parse.urlparse(url)
        item, wrapper, geometry = fixture()
        if parsed.path.endswith("/lookup/trains"):
            data = self.directory()
        elif parsed.path.endswith("/live"):
            number = parsed.path.split("/")[-2]
            data = wrapper["payload"]["data"]
            data.update(trainNumber=number, trainName=self.directory()[number],
                        startDate=urllib.parse.parse_qs(parsed.query)["date"][0])
            if number == "10001" and self.now[0] < COMPLETION.timestamp():
                data["status"] = "running"
                data["route"][-1]["actualArrival"] = None
        else:
            data = geometry["data"]
            data["trainNumber"] = parsed.path.split("/")[-2]
        return 200, {}, json.dumps({"success": True, "data": data}).encode()
    def factory(self, store, phase, key, remaining):
        return Client(store, phase, key, remaining, send=self.provider,
                      clock=lambda: self.now[0], sleep=lambda n: self.now.__setitem__(0, self.now[0]+n))
    def test_two_complete_passes_freeze_and_reuse(self):
        with patch.dict("os.environ", {"RAILRADAR_API_KEY": "fake-key"}):
            self.now[0] = (START+timedelta(hours=12)).timestamp()
            collect_pass(self.store, "initial", 100, now=START+timedelta(hours=12), client_factory=self.factory)
            self.assertEqual(len(self.calls), 40)
            collect_pass(self.store, "initial", 60, now=START+timedelta(hours=13), client_factory=self.factory)
            self.assertEqual(len(self.calls), 40)
            self.now[0] = COMPLETION.timestamp()
            collect_pass(self.store, "completion", 60, now=COMPLETION, client_factory=self.factory)
            before = len(self.calls)
            self.assertEqual(before, 50)  # 9 missing geometries + 1 incomplete live refresh.
            collect_pass(self.store, "completion", 50, now=COMPLETION, client_factory=self.factory)
            self.assertEqual(len(self.calls), before)
            self.assertEqual(len(self.store.successful("live", "10001@2026-10-09")), 2)
            data = prepare(self.store)
            self.assertEqual(len(data["journeys"]), 24)
            self.assertEqual(prepare(self.store), data)
            with self.assertRaisesRegex(CollectionStopped, "frozen"):
                collect_pass(self.store, "completion", 50, now=COMPLETION, client_factory=self.factory)
    def test_failed_feasibility_stops_after_three_probes(self):
        original = self.provider
        def no_actuals(url, key):
            status, headers, raw = original(url, key)
            payload = json.loads(raw)
            if "/live" in url:
                for row in payload["data"]["route"]:
                    row.pop("actualArrival", None)
                    row.pop("actualDeparture", None)
            return status, headers, json.dumps(payload).encode()
        self.provider = no_actuals
        with patch.dict("os.environ", {"RAILRADAR_API_KEY": "fake-key"}):
            with self.assertRaisesRegex(CollectionStopped, "three dated probes"):
                collect_pass(self.store, "initial", 100, now=START+timedelta(hours=12), client_factory=self.factory)
            self.assertEqual(len(self.calls), 4)
            with self.assertRaises(CollectionStopped):
                collect_pass(self.store, "completion", 96, now=COMPLETION, client_factory=self.factory)
            self.assertEqual(len(self.calls), 4)

if __name__ == "__main__":
    unittest.main()
