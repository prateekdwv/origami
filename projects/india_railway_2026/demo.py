"""Deterministic illustrative traffic, NEVER actual railway observations.

City-to-city corridors are hand-authored design geometry, not verified tracks.
This module is imported only by the opt-in preview/test workflow.
"""
import numpy as np
from geography import boundary_hash, pixels, project
from model import active_counts
from settings import DAY

# Approximate geographical anchors; all connecting lines are illustrative.
NODES = {
    "Srinagar": (74.80, 34.08), "Jammu": (74.87, 32.73), "Amritsar": (74.87, 31.63),
    "Ludhiana": (75.86, 30.90), "Delhi": (77.21, 28.61), "Jaipur": (75.79, 26.91),
    "Ajmer": (74.64, 26.45), "Ahmedabad": (72.58, 23.02), "Vadodara": (73.18, 22.31),
    "Surat": (72.83, 21.17), "Mumbai": (72.88, 19.08), "Pune": (73.86, 18.52),
    "Kota": (75.86, 25.18), "Agra": (78.01, 27.18), "Gwalior": (78.18, 26.22),
    "Jhansi": (78.57, 25.45), "Bhopal": (77.41, 23.26), "Itarsi": (77.76, 22.61),
    "Nagpur": (79.09, 21.15), "Wardha": (78.60, 20.74), "Bhusaval": (75.77, 21.05),
    "Nashik": (73.79, 20.00), "Kanpur": (80.33, 26.45), "Lucknow": (80.95, 26.85),
    "Varanasi": (82.97, 25.32), "Patna": (85.14, 25.61), "Asansol": (86.98, 23.68),
    "Kolkata": (88.36, 22.57), "Ranchi": (85.31, 23.34), "Raipur": (81.63, 21.25),
    "Bilaspur": (82.15, 22.08), "Rourkela": (84.85, 22.26), "Kharagpur": (87.32, 22.35),
    "Bhubaneswar": (85.82, 20.30), "Vizag": (83.22, 17.69), "Vijayawada": (80.65, 16.51),
    "Warangal": (79.59, 17.97), "Hyderabad": (78.49, 17.39), "Solapur": (75.91, 17.66),
    "Guntakal": (77.37, 15.17), "Bengaluru": (77.59, 12.97), "Chennai": (80.27, 13.08),
    "Salem": (78.15, 11.66), "Coimbatore": (76.96, 11.02), "Kochi": (76.27, 9.97),
    "Thiruvananthapuram": (76.95, 8.52), "Madurai": (78.12, 9.93),
    "Mangaluru": (74.85, 12.91), "Goa": (73.94, 15.30), "Ratnagiri": (73.30, 16.99),
    "Katihar": (87.58, 25.54), "Siliguri": (88.43, 26.72), "NewAlipurduar": (89.54, 26.49),
    "Guwahati": (91.74, 26.14), "Lumding": (93.17, 25.75), "Silchar": (92.79, 24.83),
    "Agartala": (91.29, 23.83), "Dimapur": (93.73, 25.91), "Dibrugarh": (94.91, 27.47),
    "Thane": (72.98, 19.20), "Kalyan": (73.13, 19.24), "Virar": (72.81, 19.46),
    "Tambaram": (80.12, 12.92), "Chengalpattu": (79.98, 12.68),
    "Bardhaman": (87.85, 23.23), "Kalyani": (88.43, 22.98),
}

# An interconnected illustrative network. Shared corridors stay aligned.
CORRIDORS = [
    ("rajdhani", "Delhi Agra Gwalior Jhansi Bhopal Itarsi Nagpur Warangal Hyderabad"),
    ("rajdhani", "Delhi Kanpur Varanasi Patna Katihar Siliguri NewAlipurduar Guwahati"),
    ("rajdhani", "Delhi Kota Vadodara Surat Mumbai"),
    ("rajdhani", "Delhi Kanpur Varanasi Asansol Kolkata"),
    ("vande", "Delhi Agra Gwalior Jhansi Bhopal"),
    ("vande", "Ahmedabad Vadodara Surat Mumbai"),
    ("vande", "Chennai Bengaluru"),
    ("vande", "Hyderabad Warangal Vijayawada Vizag"),
    ("vande", "Kolkata Kharagpur Bhubaneswar"),
    ("shatabdi", "Delhi Ludhiana Amritsar"),
    ("shatabdi", "Delhi Jaipur Ajmer"),
    ("shatabdi", "Chennai Bengaluru Salem Coimbatore"),
    ("shatabdi", "Kolkata Asansol Ranchi"),
    ("regional", "Srinagar Jammu Ludhiana Delhi"),
    ("regional", "Guwahati Lumding Dimapur Dibrugarh"),
    ("regional", "Guwahati Lumding Silchar Agartala"),
    ("regional", "Nagpur Raipur Bilaspur Rourkela Kharagpur Kolkata"),
    ("regional", "Bhopal Itarsi Bhusaval Nashik Mumbai Pune"),
    ("regional", "Lucknow Kanpur Varanasi Patna"),
    ("regional", "Bengaluru Guntakal Solapur Pune"),
    ("express", "Mumbai Ratnagiri Goa Mangaluru Kochi Thiruvananthapuram"),
    ("express", "Kolkata Kharagpur Bhubaneswar Vizag Vijayawada Chennai Madurai Thiruvananthapuram"),
    ("express", "Mumbai Pune Solapur Hyderabad Warangal Vijayawada Chennai"),
    ("express", "Delhi Agra Gwalior Jhansi Bhopal Itarsi Nagpur Wardha Guntakal Bengaluru"),
    ("express", "Ahmedabad Ajmer Jaipur Delhi Ludhiana Jammu"),
    ("express", "Bengaluru Salem Coimbatore Kochi Thiruvananthapuram"),
    ("local", "Mumbai Thane Kalyan"), ("local", "Mumbai Virar"),
    ("local", "Chennai Tambaram Chengalpattu"),
    ("local", "Kolkata Bardhaman"), ("local", "Kolkata Kalyani"),
]


def build_demo():
    journeys, routes = [], []
    speeds = {"vande": 110, "rajdhani": 90, "shatabdi": 95, "regional": 65, "local": 42, "express": 75}
    for route_index, (category, names) in enumerate(CORRIDORS):
        nodes = project([NODES[name] for name in names.split()])
        # Densify without pretending these hand-authored corridors are surveyed track.
        line = np.concatenate([np.linspace(a, b, 10, endpoint=False) for a, b in zip(nodes, nodes[1:])] + [nodes[-1:]])
        screen = pixels(line)
        distances = np.r_[0., np.cumsum(np.linalg.norm(np.diff(line, axis=0), axis=1))]
        stops = np.r_[0., np.cumsum(np.linalg.norm(np.diff(nodes, axis=0), axis=1))]
        routes.append({"id": f"illustrative-{route_index}", "points": screen.tolist()})
        travel_time = distances[-1] / (speeds[category]/3.6)
        dwell = 240 if category != "local" else 90
        duration = travel_time + dwell*(len(nodes)-2)
        interval = 2.5*3600 if category == "local" else (4*3600 if category in ("vande", "regional", "shatabdi") else 7*3600)
        for direction in (0, 1):
            route_points = screen if direction == 0 else screen[::-1]
            route_distances = distances if direction == 0 else distances[-1]-distances[::-1]
            station_distances = stops if direction == 0 else stops[-1]-stops[::-1]
            phase = ((route_index*977 + direction*1871) % int(interval))
            for run in range(-int(np.ceil(duration/interval))-1, 25):
                departure = phase+run*interval
                if departure >= 86400 or departure+duration <= 0:
                    continue
                # Fewer invented regional/local services at night, giving a visible daily rhythm.
                hour = (departure/3600) % 24
                if category in ("local", "regional", "shatabdi", "vande") and not 4.5 <= hour <= 22.5:
                    continue
                segments, cursor = [], departure
                def add(start, end, left, right, kind):
                    a, b = max(0, start), min(86400, end)
                    if b > a:
                        segments.append({"start": a, "end": b,
                                         "from": left+(right-left)*(a-start)/(end-start),
                                         "to": left+(right-left)*(b-start)/(end-start), "kind": kind})
                for i, (a, b) in enumerate(zip(station_distances, station_distances[1:])):
                    arrival = cursor+(b-a)/(speeds[category]/3.6)
                    add(cursor, arrival, a, b, "travel")
                    cursor = arrival
                    if i < len(station_distances)-2:
                        add(cursor, cursor+dwell, b, b, "dwell")
                        cursor += dwell
                journeys.append({"id": f"DEMO-{route_index:02d}-{direction}-{run:+03d}",
                                 "name": f"Illustrative {names.split()[0]}–{names.split()[-1]}",
                                 "category": category, "route_pixels": route_points.tolist(),
                                 "distances": route_distances.tolist(), "segments": segments})
    return {"version": 1, "date": DAY, "timezone": "Asia/Kolkata", "synthetic_test_only": True,
            "basis": "Entirely invented journeys, timings and illustrative corridors; not real railway data",
            "boundary_sha256": boundary_hash(), "journeys": journeys, "display_routes": routes,
            "coverage": {"selected": len(journeys), "included": len(journeys), "records": [],
                         "warning": "Visual stress test, NOT an estimate of final sample coverage or traffic"},
            "activity": [sum(active_counts(journeys, t).values()) for t in range(0, 86401, 300)]}
