"""Timetable preview preserves stop times, midnight clipping and geometry gaps."""
import unittest
import numpy as np

from design import FrameRenderer, motion_sample
from schedule_render import category, movement_segments, prepare_route


class ScheduledPreviewTests(unittest.TestCase):
    def setUp(self):
        self.train = {"number": "12345", "name": "Example", "service_type": "Suburban", "stops": [
            {"station": "A", "arrival": 85800, "departure": 85800},
            {"station": "B", "arrival": 87000, "departure": 87300},
            {"station": "C", "arrival": 88500, "departure": 88500}]}
        self.instance = {"origin_date": "2026-10-14", "target_date": "2026-10-15"}

    def test_overnight_travel_is_clipped_and_station_dwell_preserved(self):
        segments, rejected = movement_segments(self.train, self.instance, [0, 12000, 24000], {0, 1})
        self.assertEqual(rejected, 0)
        self.assertEqual(segments, [
            {"start": 0, "end": 600, "from": 6000, "to": 12000, "kind": "travel"},
            {"start": 600, "end": 900, "from": 12000, "to": 12000, "kind": "dwell"},
            {"start": 900, "end": 2100, "from": 12000, "to": 24000, "kind": "travel"}])

    def test_missing_geometry_is_never_bridged(self):
        segments, _ = movement_segments(self.train, self.instance, [0, 12000, None], {0})
        self.assertEqual([s["kind"] for s in segments], ["travel", "dwell"])
        self.assertEqual(segments[-1]["end"], 900)

    def test_implausibly_fast_travel_is_omitted(self):
        segments, rejected = movement_segments(self.train, self.instance, [0, 1200000, 2400000], {0, 1})
        self.assertEqual(rejected, 2)
        self.assertEqual([s["kind"] for s in segments], ["dwell"])

    def test_cached_leg_reverses_for_reverse_service(self):
        train = {"stops": [{"station": "B"}, {"station": "A"}]}
        points, distances, measures, valid = prepare_route(train, {("A", "B"): (np.array([[0, 0], [1, 0], [3, 0]]), np.array([0, 10, 30]))})
        self.assertEqual(points, [[3, 0], [1, 0], [0, 0]])
        self.assertEqual(distances, [0, 20, 30])
        self.assertEqual(measures, [0, 30])
        self.assertEqual(valid, {0})

    def test_abbreviations_and_unknown_types_remain_visible(self):
        for kind, expected in (("Suburban", "local"), ("EMU", "local"), ("Raj", "rajdhani"), ("Pass", "regional"), ("unclassified", "unknown")):
            self.assertEqual(category(dict(self.train, service_type=kind)), expected)

    def test_prepared_motion_matches_uncached_motion_across_a_gap(self):
        # Exercise prepared continuity bounds without rasterizing a map.
        segments = [{"start": 0, "end": 1000, "from": 0, "to": 100, "kind": "travel"},
                    {"start": 1000, "end": 1200, "from": 100, "to": 100, "kind": "dwell"},
                    {"start": 1500, "end": 2500, "from": 200, "to": 300, "kind": "travel"}]
        journey = {"id": "test", "category": "local", "segments": segments,
                   "route_pixels": [[0, 0], [300, 0]], "distances": [0, 300]}
        renderer = FrameRenderer.__new__(FrameRenderer)
        renderer.prepare_routes([journey])
        prepared = renderer.routes[0][0]["_motion"]
        for index, time in ((0, 1), (0, 999), (1, 1000), (1, 1199), (2, 1500), (2, 2000)):
            self.assertEqual(motion_sample(segments, index, time), motion_sample(segments, index, time, prepared))
        for time, count in ((999, 1), (1000, 1), (1200, 0), (1499, 0), (1500, 1), (2500, 0)):
            self.assertEqual(int(np.sum((renderer.starts <= time) & (time < renderer.ends))), count)

    def test_cache_ignores_presentation_but_rejects_input_or_preparation_changes(self):
        from unittest.mock import patch
        import schedule_render as scheduled
        inputs = {"trains.json.gz": "source-hash"}
        data = {"date": "2026-10-15", "source_hashes": inputs, "boundary_sha256": "boundary",
                "preparation_version": scheduled.PREPARATION_VERSION}
        with patch.object(scheduled, "input_hashes", return_value=inputs), \
             patch.object(scheduled, "boundary_hash", return_value="boundary"):
            self.assertTrue(scheduled.cache_matches(dict(data, categories={"new": "palette"}), "2026-10-15"))
            self.assertFalse(scheduled.cache_matches(dict(data, preparation_version=-1), "2026-10-15"))
            self.assertFalse(scheduled.cache_matches(dict(data, source_hashes={}), "2026-10-15"))
            self.assertFalse(scheduled.cache_matches(dict(data, boundary_sha256="changed"), "2026-10-15"))
            self.assertFalse(scheduled.cache_matches(data, "2026-10-16"))

    def test_cached_categories_refresh_without_touching_movement_data(self):
        from unittest.mock import patch
        from schedule_render import update_categories
        journey = {"id": "12345@2026-10-15", "category": "unknown", "segments": [],
                   "route_pixels": [[1, 2], [3, 4]], "distances": [0, 10]}
        data = {"journeys": [journey], "coverage": {}}
        route, intervals = journey["route_pixels"], journey["segments"]
        with patch("schedule_render.read_gzip", return_value=[self.train]):
            update_categories(data)
        self.assertEqual(journey["category"], "local")
        self.assertEqual(data["coverage"]["category_journeys"], {"local": 1})
        self.assertIs(journey["route_pixels"], route)
        self.assertIs(journey["segments"], intervals)
