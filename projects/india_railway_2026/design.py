"""Offline composition; a single deterministic frame function drives Manim and audits."""
from functools import lru_cache
import cairo
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from geography import official_map, pixels, project
from model import route_arrays
from tracks import load_tracks, network_pixels
from settings import CATEGORIES, HEIGHT, INTRO, REPLAY, ROOT, WIDTH

BACKGROUND, LAND, OUTLINE = "#F7F5EF", "#E6ECE3", "#829787"
INK, MUTED = "#243A3D", "#60716E"
TRACK = "#859692"
# Approximate city-centre label anchors only: never used as train observations.
CITIES = [
    ("Srinagar", 74.80, 34.08, 14, -28), ("Delhi", 77.21, 28.61, 14, -28),
    ("Jaipur", 75.79, 26.91, -96, 4), ("Ahmedabad", 72.58, 23.02, -152, -28),
    ("Mumbai", 72.88, 19.08, -106, 4), ("Pune", 73.86, 18.52, 14, 8),
    ("Bhopal", 77.41, 23.26, 12, -30), ("Lucknow", 80.95, 26.85, 12, -30),
    ("Patna", 85.14, 25.61, -42, -35), ("Kolkata", 88.36, 22.57, 14, 4),
    ("Guwahati", 91.74, 26.14, -35, -38), ("Agartala", 91.29, 23.83, 14, 10),
    ("Bhubaneswar", 85.82, 20.30, 14, 8), ("Nagpur", 79.09, 21.15, 12, -28),
    ("Hyderabad", 78.49, 17.39, 14, -28), ("Bengaluru", 77.59, 12.97, -135, -16),
    ("Chennai", 80.27, 13.08, 14, 4), ("Thiruvananthapuram", 76.95, 8.52, -165, 14),
]

@lru_cache(maxsize=32)
def font(size, bold=False):
    path = ROOT / "assets" / "fonts" / ("Lato-Bold.ttf" if bold else "Lato-Regular.ttf")
    return ImageFont.truetype(str(path), size)

def text(draw, xy, value, size=24, fill=INK, bold=False):
    draw.text(xy, str(value), font=font(size, bold), fill=fill)

def rgb(value):
    return tuple(int(value[i:i+2], 16)/255 for i in (1, 3, 5))

def base_image(dataset=None):
    """Rasterize every unsimplified official ring, including offshore islands."""
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, WIDTH, HEIGHT)
    context = cairo.Context(surface)
    context.set_source_rgb(*rgb(BACKGROUND))
    context.paint()
    context.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
    for ring in official_map()[2]:
        points = pixels(ring)
        context.move_to(*points[0])
        for point in points[1:]:
            context.line_to(*point)
        context.close_path()
    context.set_source_rgb(*rgb(LAND))
    context.fill_preserve()
    context.set_source_rgb(*rgb(OUTLINE))
    context.set_line_width(1.1)
    context.stroke()
    surface.flush()
    image = Image.frombuffer("RGBA", (WIDTH, HEIGHT), surface.get_data(), "raw", "BGRA", 0, 1).convert("RGB")
    draw = ImageDraw.Draw(image)
    if (dataset or {}).get("display_routes"):
        routes = [r["points"] for r in dataset["display_routes"]]
    else:
        routes = [j["route_pixels"] for j in (dataset or {}).get("journeys", [])]
    mapped = bool((dataset or {}).get('track_source'))
    if mapped:
        _, provenance = load_tracks()
        if dataset['railway_geometry_sha256'] != provenance['geometry_sha256']:
            raise ValueError('Preview railway asset has changed')
        # Thin, subdued national network; active demonstration paths stay legible.
        for route in network_pixels():
            draw.line([tuple(p) for p in route], fill='#B2BFB5', width=2)
        for route in routes:
            draw.line([tuple(p) for p in route], fill='#7B9488', width=3, joint='curve')
    else:
        for route in routes:
            draw.line([tuple(p) for p in route], fill=BACKGROUND, width=7, joint='curve')
        for route in routes:
            draw.line([tuple(p) for p in route], fill=TRACK, width=3, joint='curve')
    for name, lon, lat, dx, dy in CITIES:
        x, y = pixels(project([[lon, lat]]))[0]
        draw.ellipse((x-2, y-2, x+2, y+2), fill=MUTED)
        draw.text((x+dx, y+dy), name, font=font(26), fill=INK, stroke_width=2, stroke_fill=BACKGROUND)
    synthetic = bool((dataset or {}).get("synthetic_test_only"))
    text(draw, (64, 49), "INDIA / IN MOTION" if not synthetic else "INDIA / DESIGN PREVIEW", 22, MUTED, True)
    text(draw, (60, 85), "A day on the rails", 60, bold=True)
    text(draw, (64, 164), "10 OCTOBER 2026", 27, MUTED)
    draw.line((64, 266, 1016, 266), fill="#CCD4CA", width=2)
    draw.rounded_rectangle((44, 1388, 1036, 1620), radius=18, fill="#FFFFFF", outline="#E0E4DA", width=1)
    text(draw, (64, 1400), "SIMULATED SERVICES / SIX COLOUR FAMILIES" if synthetic else "PASSENGER JOURNEYS / SELECTED SAMPLE", 21, MUTED, True)
    represented = {j["category"] for j in (dataset or {}).get("journeys", [])}
    for i, (category, (label, color)) in enumerate(CATEGORIES.items()):
        x, y = 64+(i % 2)*490, 1450+(i//2)*58
        draw.ellipse((x, y+7, x+12, y+19), fill=color)
        text(draw, (x+24, y), label, 25)
        if dataset is None or category not in represented:
            text(draw, (x+24, y+27), "awaiting data" if dataset is None else "not represented", 17, MUTED)
    text(draw, (64, 1638), "SIMULATED ACTIVITY / 24 HOURS" if synthetic else "SAMPLE ACTIVITY / 24 HOURS", 19, MUTED, True)
    draw.line((64, 1766, 1016, 1766), fill="#CCD4CA", width=1)
    for hour in (0, 6, 12, 18, 24):
        text(draw, (min(64+952*hour/24, 963), 1775), f"{hour:02d}:00", 18, MUTED)
    text(draw, (64, 1832), "Simulated journeys & timings · Mapped railway tracks" if synthetic else
         "Representative sample · Recorded timings · Interpolated positions", 22)
    text(draw, (64, 1870), "Boundary: Survey of India · Noncommercial use only" + (" · Traffic simulated" if synthetic else " · Timings: RailRadar"), 19, MUTED)
    if mapped:
        text(draw, (64, 1897), "Tracks: © OpenStreetMap contributors · openstreetmap.org/copyright · ODbL", 17, MUTED)
    if synthetic:
        draw.rounded_rectangle((578, 304, 1016, 350), radius=12, fill="#F1E5C9")
        text(draw, (594, 315), "SIMULATED TRAFFIC / OSM TRACKS", 19, "#806019", True)
        draw.line((775, 375, 814, 375), fill=TRACK, width=3)
        text(draw, (825, 360), "Mapped railway", 21, MUTED)
    if dataset is not None:
        activity = dataset["activity"]
        points = [(64+i*952/(len(activity)-1), 1765-value/(max(activity) or 1)*76) for i, value in enumerate(activity)]
        draw.polygon([(64, 1765), *points, (1016, 1765)], fill="#CFDDD3")
        draw.line(points, fill="#658775", width=2)
        text(draw, (785, 1638), f"peak shown: {max(activity)}", 19, MUTED)
    return image

def second_at(video_time):
    return min(86400, max(0, (video_time-INTRO)/REPLAY*86400))

def motion_sample(segments, index, second, prepared=None):
    """Fade inside contiguous evidence and retain up to seven minutes of trail."""
    first = last = index
    def joined(a, b):
        return abs(a["end"]-b["start"]) < 1e-6 and abs(a["to"]-b["from"]) < 1e-5
    if prepared is not None:
        first, last = prepared[0][index]
    else:
        while first > 0 and joined(segments[first-1], segments[first]):
            first -= 1
        while last+1 < len(segments) and joined(segments[last], segments[last+1]):
            last += 1
    start, end = segments[first]["start"], segments[last]["end"]
    fade = min(.15*86400/REPLAY, (end-start)/2)
    opacity = float(np.clip(min(second-start, end-second)/fade, 0, 1))
    opacity = opacity*opacity*(3-2*opacity)
    tail_time = max(start, second-420)
    tail = (segments[int(np.searchsorted(prepared[1], tail_time, side="right"))-1] if prepared is not None else
            next(s for s in segments[first:index+1] if s["start"] <= tail_time < s["end"]))
    def distance(segment, time):
        return segment["from"]+(segment["to"]-segment["from"])*(time-segment["start"])/(segment["end"]-segment["start"])
    return distance(tail, tail_time), distance(segments[index], second), opacity


def paint_trains(image, active, second):
    """Cairo preserves fractional pixel coverage; PIL's ellipse snaps to pixels."""
    data = bytearray(image.convert("RGBA").tobytes("raw", "BGRA"))
    surface = cairo.ImageSurface.create_for_data(data, cairo.FORMAT_ARGB32, *image.size)
    context = cairo.Context(surface)
    context.set_antialias(cairo.ANTIALIAS_BEST)
    context.set_line_cap(cairo.LINE_CAP_ROUND)
    context.set_line_join(cairo.LINE_JOIN_ROUND)
    for journey, points, distances, index in active:
        a, b, opacity = motion_sample(journey["segments"], index, second, journey.get("_motion"))
        color = rgb(CATEGORIES[journey["category"]][1])
        start, point = np.array([np.interp([a, b], distances, points[:, axis]) for axis in (0, 1)]).T
        inside = points[np.searchsorted(distances, a, side="right"):np.searchsorted(distances, b)]
        context.set_source_rgba(*color, opacity)
        context.set_line_width(4)
        context.move_to(*start)
        for vertex in inside:
            context.line_to(*vertex)
        context.line_to(*point)
        context.stroke()
        halo = tuple(v*.18+background*.82 for v, background in zip(color, rgb(BACKGROUND)))
        for radius, fill in ((10, halo), (5.5, color)):
            context.set_source_rgba(*fill, opacity)
            context.arc(*point, radius, 0, 2*np.pi)
            context.fill()
        context.set_source_rgba(1, 1, 1, opacity)
        context.set_line_width(1)
        context.arc(*point, 5.5, 0, 2*np.pi)
        context.stroke()
    surface.flush()
    return Image.frombuffer("RGBA", image.size, data, "raw", "BGRA", 0, 1).convert("RGB")


class FrameRenderer:
    """One composition per export, with prepared routes and cached static holds."""
    def __init__(self, dataset=None):
        self.base, self.dataset = base_image(dataset), dataset
        self.routes = [(j, *route_arrays(j)) for j in (dataset or {}).get("journeys", [])]
        self.represented = {j["category"] for j, _, _ in self.routes}
        self.holds = {}

    def __call__(self, video_time=0):
        hold = 0 if video_time < INTRO else INTRO+REPLAY if video_time >= INTRO+REPLAY else None
        if hold is None:
            return self.draw(video_time)
        if hold not in self.holds:
            self.holds[hold] = self.draw(hold)
        return self.holds[hold]

    def draw(self, video_time):
        image = self.base.copy()
        dataset = self.dataset
        draw = ImageDraw.Draw(image)
        second = second_at(video_time)
        if dataset is None:
            text(draw, (64, 217), "DESIGN PROOF — AWAITING OBSERVATIONS", 23, "#806019")
            text(draw, (720, 180), "00:00", 50)
            return image
        journeys = dataset["journeys"]
        synthetic = dataset.get("synthetic_test_only", False)
        active = [(j, p, d, index) for j, p, d in self.routes
                  if (index := next((i for i, s in enumerate(j["segments"]) if s["start"] <= second < s["end"]), None)) is not None]
        counts = dict.fromkeys(CATEGORIES, 0)
        for journey, _, _, _ in active:
            counts[journey["category"]] += 1
        minute = min(1440, int(second//60))
        text(draw, (752, 177), f"{minute//60:02d}:{minute%60:02d}", 54, bold=True)
        text(draw, (960, 199), "IST", 21, MUTED)
        if video_time < INTRO:
            status = f"{len(journeys)} {'invented' if synthetic else 'sampled'} journeys · 00:00–24:00 IST"
        elif video_time < INTRO+REPLAY:
            status = (f"{sum(counts.values()):02d} simulated trains · mapped tracks" if synthetic else
                      f"{sum(counts.values()):02d} sample journeys underway · observed segments only")
        else:
            status = (f"Demo complete · {len(journeys)} invented journeys" if synthetic else
                      f"Day complete · {len(journeys)} usable / {dataset['coverage']['selected']} selected journeys")
        text(draw, (64, 219), status, 23, MUTED)
        if INTRO <= video_time < INTRO+REPLAY:
            image = paint_trains(image, active, second)
            draw = ImageDraw.Draw(image)
            for i, category in enumerate(CATEGORIES):
                if category in self.represented:
                    text(draw, (490+(i % 2)*490, 1450+(i//2)*58), f"{counts[category]:02d}", 24, CATEGORIES[category][1], True)
        cursor = 64+second/86400*952
        draw.line((cursor, 1681, cursor, 1766), fill="#B77909", width=3)
        return image
