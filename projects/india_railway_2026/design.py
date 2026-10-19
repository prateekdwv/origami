"""Offline composition; a single deterministic frame function drives Manim and audits."""
from functools import lru_cache
from datetime import date
import cairo
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from geography import official_map, pixels, project
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


# One display transform applies to boundary, tracks, labels and prepared routes.
# Canonical stored coordinates and metre distances remain unchanged.
MAP_SCALE = 1000 / 944
CHART_LEFT, CHART_RIGHT, CHART_TOP, CHART_BOTTOM = 100, 1024, 1696, 1798


def display_points(points):
    return (np.asarray(points)-[540, 840])*MAP_SCALE+[540, 770]


def right_text(draw, xy, value, size=24, fill=INK, bold=False):
    value = str(value)
    text(draw, (xy[0]-draw.textlength(value, font=font(size, bold)), xy[1]), value, size, fill, bold)


def legend_position(index, categories):
    return 56+(index % 2)*500, 1410+(index//2)*46


def traffic_series(journeys):
    """Exact half-open interval counts, grouping simultaneous starts and ends."""
    events = [(0, 0), (86400, 0)]
    for journey in journeys:
        for segment in journey["segments"]:
            events.extend(((segment["start"], 1), (segment["end"], -1)))
    events = np.asarray(events)
    times, inverse = np.unique(events[:, 0], return_inverse=True)
    counts = np.cumsum(np.bincount(inverse, weights=events[:, 1])).astype(int)
    return times, counts


def chart_point(second, count, ceiling):
    return (CHART_LEFT+(CHART_RIGHT-CHART_LEFT)*second/86400,
            CHART_BOTTOM-(CHART_BOTTOM-CHART_TOP)*count/ceiling)


def chart_ceiling(peak):
    step = 500 if peak >= 500 else 100 if peak >= 100 else 20
    return max(step, int(np.ceil(peak/step))*step)


@lru_cache(maxsize=1)
def city_label_layer():
    """Fixed names on a transparent foreground; only glyphs and thin outlines."""
    layer = Image.new("RGBA", (WIDTH, HEIGHT))
    draw = ImageDraw.Draw(layer)
    anchors = display_points(pixels(project([[lon, lat] for _, lon, lat, _, _ in CITIES])))
    for (name, _, _, dx, dy), (x, y) in zip(CITIES, anchors):
        draw.text((x+dx, y+dy), name, font=font(26), fill=INK,
                  stroke_width=2, stroke_fill=BACKGROUND)
    return layer


def base_image(dataset=None, *, show_city_labels=True, series=None):
    """Rasterize every unsimplified official ring, including offshore islands."""
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, WIDTH, HEIGHT)
    context = cairo.Context(surface)
    context.set_source_rgb(*rgb(BACKGROUND))
    context.paint()
    context.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
    for ring in official_map()[2]:
        points = display_points(pixels(ring))
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
    categories = (dataset or {}).get("categories", CATEGORIES)
    if (dataset or {}).get("display_routes"):
        routes = [display_points(r["points"]) for r in dataset["display_routes"]]
    else:
        routes = [display_points(j["route_pixels"]) for j in (dataset or {}).get("journeys", [])]
    mapped = bool((dataset or {}).get('track_source'))
    scheduled = bool((dataset or {}).get("scheduled_preview"))
    if mapped:
        _, provenance = load_tracks()
        if dataset['railway_geometry_sha256'] != provenance['geometry_sha256']:
            raise ValueError('Preview railway asset has changed')
        # Thin, subdued national network; active demonstration paths stay legible.
        for route in network_pixels():
            draw.line([tuple(p) for p in display_points(route)], fill='#BEC9BF', width=1)
        if not scheduled:
            for route in routes:
                draw.line([tuple(p) for p in route], fill='#7B9488', width=3, joint='curve')
    else:
        for route in routes:
            draw.line([tuple(p) for p in route], fill=BACKGROUND, width=7, joint='curve')
        for route in routes:
            draw.line([tuple(p) for p in route], fill=TRACK, width=3, joint='curve')
    for name, lon, lat, dx, dy in CITIES:
        x, y = display_points(pixels(project([[lon, lat]])))[0]
        draw.ellipse((x-2, y-2, x+2, y+2), fill=MUTED)
    synthetic = bool((dataset or {}).get("synthetic_test_only"))
    day = date.fromisoformat((dataset or {}).get("date", "2026-10-10"))
    text(draw, (56, 44), "India’s railways" + (" · simulation" if synthetic else ""), 40, bold=True)
    right_text(draw, (1024, 52), f"{day.day:02d} {day.strftime('%b')} {day.year} · IST", 24, MUTED)
    if dataset is not None:
        total = f"{len(dataset['journeys']):,}"
        text(draw, (56, 100), total, 40, bold=True)
        offset = draw.textlength(total, font=font(40, True))+72
        text(draw, (offset, 114), "journeys in 24 hours", 25, MUTED)
    else:
        text(draw, (56, 114), "Awaiting observations", 25, MUTED)
    draw.line((56, 173, 1024, 173), fill="#CCD4CA", width=1)
    for i, (category, (label, color)) in enumerate(categories.items()):
        x, y = legend_position(i, categories)
        draw.ellipse((x, y+9, x+12, y+21), fill=color)
        text(draw, (x+24, y), "Unknown" if category == "unknown" else label, 24)
    times, counts = traffic_series((dataset or {}).get("journeys", [])) if series is None else series
    peak_index = int(np.argmax(counts))
    peak, peak_second = int(counts[peak_index]), float(times[peak_index])
    ceiling = chart_ceiling(peak)
    if dataset is not None:
        # Step geometry uses the same exact interval counts as the live counter.
        points = [chart_point(t, n, ceiling) for t, n in zip(np.repeat(times, 2)[1:], np.repeat(counts, 2)[:-1])]
        draw.polygon([(CHART_LEFT, CHART_BOTTOM), *points, (CHART_RIGHT, CHART_BOTTOM)], fill="#D4E0D6")
        draw.line(points, fill="#658775", width=2)
    draw.line((CHART_LEFT, CHART_TOP, CHART_LEFT, CHART_BOTTOM), fill="#A4B2A8", width=1)
    draw.line((CHART_LEFT, CHART_BOTTOM, CHART_RIGHT, CHART_BOTTOM), fill="#A4B2A8", width=1)
    right_text(draw, (CHART_LEFT-12, CHART_TOP-12), f"{ceiling:,}", 18, MUTED)
    right_text(draw, (CHART_LEFT-12, CHART_BOTTOM-12), "0", 18, MUTED)
    for hour in (0, 6, 12, 18, 24):
        x, _ = chart_point(hour*3600, 0, ceiling)
        value = f"{hour:02d}:00"
        left = min(CHART_RIGHT-draw.textlength(value, font=font(18)), x-22)
        text(draw, (left, 1810), value, 18, MUTED)
    footer = ("Scheduled traffic · Interpolated positions · Provisional coverage" if scheduled else
              "Simulated traffic · Invented journeys and timings" if synthetic else
              "Recorded timings · Interpolated positions" if dataset else "Design proof · Awaiting observations")
    text(draw, (56, 1847), footer, 19, MUTED)
    text(draw, (56, 1876), "Boundary: Survey of India · Noncommercial use only", 17, MUTED)
    if mapped:
        text(draw, (56, 1898), "Tracks: © OpenStreetMap contributors · ODbL", 16, MUTED)
    if show_city_labels:
        image.paste(city_label_layer(), (0, 0), city_label_layer())
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


def paint_trains(image, active, second, categories=CATEGORIES, halo_radius=10):
    """Cairo preserves fractional pixel coverage; PIL's ellipse snaps to pixels."""
    data = bytearray(image.convert("RGBA").tobytes("raw", "BGRA"))
    surface = cairo.ImageSurface.create_for_data(data, cairo.FORMAT_ARGB32, *image.size)
    context = cairo.Context(surface)
    context.set_antialias(cairo.ANTIALIAS_BEST)
    context.set_line_cap(cairo.LINE_CAP_ROUND)
    context.set_line_join(cairo.LINE_JOIN_ROUND)
    for journey, points, distances, index in active:
        a, b, opacity = motion_sample(journey["segments"], index, second, journey.get("_motion"))
        color = rgb(categories[journey["category"]][1])
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
        for radius, fill in ((halo_radius, halo), (5.5, color)):
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
        self.series = traffic_series((dataset or {}).get("journeys", []))
        self.base = base_image(dataset, show_city_labels=False, series=self.series)
        self.dataset = dataset
        self.categories = (dataset or {}).get("categories", CATEGORIES)
        self.routes = [(j, display_points(j["route_pixels"]), np.asarray(j["distances"])) for j in (dataset or {}).get("journeys", [])]
        intervals, starts, ends = [], [], []
        prepared_routes = []
        for original, points, distances in self.routes:
            journey = dict(original)
            segments = journey["segments"]
            bounds, first = [], 0
            for i, segment in enumerate(segments):
                intervals.append((journey, points, distances, i))
                starts.append(segment["start"])
                ends.append(segment["end"])
                if i+1 == len(segments) or abs(segment["end"]-segments[i+1]["start"]) >= 1e-6 or abs(segment["to"]-segments[i+1]["from"]) >= 1e-5:
                    bounds.extend([(first, i)]*(i-first+1))
                    first = i+1
            journey["_motion"] = (bounds, np.array([s["start"] for s in segments]))
            prepared_routes.append((journey, points, distances))
        self.routes = prepared_routes
        self.intervals, self.starts, self.ends = intervals, np.array(starts), np.array(ends)
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
        second = second_at(video_time)
        active = [self.intervals[i] for i in np.flatnonzero((self.starts <= second) & (second < self.ends))]
        counts = dict.fromkeys(self.categories, 0)
        for journey, _, _, _ in active:
            counts[journey["category"]] += 1
        if self.dataset is not None and INTRO <= video_time < INTRO+REPLAY:
            image = paint_trains(image, active, second, self.categories,
                                 7.5 if self.dataset.get("scheduled_preview") else 10)
        draw = ImageDraw.Draw(image)
        minute = min(1440, int(second//60))
        right_text(draw, (1024, 89), f"{minute//60:02d}:{minute%60:02d}", 60, bold=True)
        if self.dataset is not None:
            for i, category in enumerate(self.categories):
                x, y = legend_position(i, self.categories)
                right_text(draw, (x+468, y), f"{counts[category]:,}", 24, self.categories[category][1], True)
        ceiling = chart_ceiling(int(max(self.series[1])))
        cursor, point_y = chart_point(second, sum(counts.values()), ceiling)
        draw.line((cursor, CHART_TOP-12, cursor, CHART_BOTTOM), fill="#D77916", width=3)
        if self.dataset is not None:
            draw.ellipse((cursor-4, point_y-4, cursor+4, point_y+4), fill="#D77916")
        label = f"{sum(counts.values()):,} trains underway now" if self.dataset is not None else "Awaiting data"
        text(draw, (56, 1610), label, 24, INK, True)
        image.paste(city_label_layer(), (0, 0), city_label_layer())
        return image
