"""Small timetable fixture for model/export tests; never a runnable demo workflow."""
from model import active_counts
from settings import SCHEDULE_CATEGORIES
from tracks import load_tracks


def timetable():
    journey = {"id": "12345@2026-10-15", "name": "Example Express", "category": "express",
               "route_pixels": [[500, 500], [600, 600]], "distances": [0, 10000],
               "segments": [{"start": 0, "end": 3600, "from": 0, "to": 5000, "kind": "travel"},
                            {"start": 3600, "end": 7200, "from": 5000, "to": 5000, "kind": "dwell"},
                            {"start": 7200, "end": 86400, "from": 5000, "to": 10000, "kind": "travel"}]}
    return {"date": "2026-10-15", "scheduled_preview": True, "categories": SCHEDULE_CATEGORIES,
            "journeys": [journey], "track_source": "OpenStreetMap",
            "railway_geometry_sha256": load_tracks()[1]["geometry_sha256"], "coverage": {},
            "activity": [sum(active_counts([journey], second).values()) for second in range(0, 86401, 300)]}
