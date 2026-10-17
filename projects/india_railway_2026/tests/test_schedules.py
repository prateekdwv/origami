"""Offline timetable validation; no network, API key, or renderer."""
from datetime import date
import unittest
from collect_schedules import clock, day_journeys, issues, record


class TimetableTests(unittest.TestCase):
    def train(self, departure=22*3600, arrival=26*3600, days=None, **extra):
        return record("01234", "Example passenger", "Passenger", "test", days or ["wed"],
            [{"station":"A", "arrival":departure, "departure":departure},
             {"station":"B", "arrival":arrival, "departure":arrival}], **extra)

    def test_overnight_origin_and_clipped_day(self):
        journeys = list(day_journeys(self.train(), date(2026, 10, 15)))
        self.assertEqual(len(journeys), 1)
        self.assertEqual(journeys[0]["id"], "01234@2026-10-14")
        self.assertEqual((journeys[0]["window_start"], journeys[0]["window_end"]), (0, 7200))
        self.assertFalse(journeys[0]["date_certified"])

    def test_weekdays_and_calendar_limits_are_honored(self):
        self.assertEqual(list(day_journeys(self.train(days=["fri"]), date(2026, 10, 15))), [])
        train = self.train(valid_from="2026-09-01", valid_until="2026-09-30")
        self.assertEqual(list(day_journeys(train, date(2026, 10, 15))), [])

    def test_midnight_end_does_not_overlap_next_day(self):
        self.assertEqual(list(day_journeys(self.train(arrival=86400), date(2026, 10, 15))), [])

    def test_multiday_lookback_uses_origin_weekday(self):
        journeys = list(day_journeys(self.train(arrival=80*3600, days=["mon"]), date(2026, 10, 15)))
        self.assertEqual(journeys[0]["origin_date"], "2026-10-12")
        self.assertEqual(journeys[0]["window_end"], 8*3600)

    def test_extended_clock_and_invalid_source_records(self):
        self.assertEqual(clock("49:30:00"), 49*3600+1800)
        with self.assertRaises(ValueError):
            clock("12:61:00")
        self.assertIsNone(issues(self.train()))
        self.assertIsNotNone(issues(self.train(arrival=20*3600)))
        self.assertIsNotNone(issues(self.train(arrival=14*86400)))
