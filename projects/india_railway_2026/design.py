"""Scheduled-video artwork using native Matplotlib collections, text and axes."""
from datetime import date
import numpy as np
from PIL import Image
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.collections import LineCollection
from matplotlib.colors import to_rgba
from matplotlib.figure import Figure
from matplotlib.font_manager import FontProperties
from matplotlib.path import Path
from matplotlib.patches import PathPatch
import matplotlib.patheffects as effects
from settings import BACKGROUND, LAND, OUTLINE, INK, MUTED, CITIES, MAP_SCALE
from model import traffic_series, motion_sample
from geography import official_map, pixels, project
from tracks import network_pixels
from settings import ROOT, WIDTH, HEIGHT, INTRO, REPLAY


def display_points(points):
    return (np.asarray(points)-[540, 840])*MAP_SCALE+[540, 770]


def legend_position(index, categories=None):
    return 56+(index % 2)*500, 1410+(index//2)*46


def chart_ceiling(peak):
    step = 500 if peak >= 500 else 100 if peak >= 100 else 20
    return max(step, int(np.ceil(peak/step))*step)


def second_at(video_time):
    return min(86400, max(0, (video_time-INTRO)/REPLAY*86400))


class FrameRenderer:
    def __init__(self, dataset):
        self.dataset = dataset
        self.categories = dataset['categories']
        self.series = traffic_series(dataset['journeys'])
        self.figure = Figure(figsize=(10.8, 19.2), dpi=100, facecolor=BACKGROUND)
        self.canvas = FigureCanvasAgg(self.figure)
        self.ax = self.figure.add_axes((0, 0, 1, 1), xlim=(0, WIDTH), ylim=(HEIGHT, 0))
        self.ax.set_axis_off()
        rings = []
        for ring in official_map()[2]:
            points = display_points(pixels(ring))
            codes = np.full(len(points), Path.LINETO, dtype=np.uint8)
            codes[0], codes[-1] = Path.MOVETO, Path.CLOSEPOLY
            rings.append(Path(points, codes))
        self.ax.add_patch(PathPatch(Path.make_compound_path(*rings), facecolor=LAND,
                                   edgecolor=OUTLINE, linewidth=.792))
        self.ax.add_collection(LineCollection([display_points(p) for p in network_pixels()],
                                             colors='#BEC9BF', linewidths=.72))
        anchors = display_points(pixels(project([[lon, lat] for _, lon, lat, _, _ in CITIES])))
        self.ax.scatter(anchors[:, 0], anchors[:, 1], s=(4*.72)**2, color=MUTED)
        day = date.fromisoformat(dataset['date'])
        self.text(56, 44, 'India\u2019s railways', 40, bold=True)
        self.text(1024, 52, f'{day.day:02d} {day:%b} {day.year} \u00b7 IST', 24, MUTED, right=True)
        total = f"{len(dataset['journeys']):,}"
        self.text(56, 100, total, 40, bold=True)
        # Lato metrics keep the subtitle aligned with the approved header.
        self.text(self.canvas.get_renderer().get_text_width_height_descent(total, self.face(40, True), False)[0]+72, 114, 'journeys in 24 hours', 25, MUTED)
        self.ax.plot([56, 1024], [173, 173], color='#CCD4CA', linewidth=.72)
        self.count_labels = []
        for i, (key, (label, color)) in enumerate(self.categories.items()):
            x, y = legend_position(i)
            self.ax.scatter([x+6], [y+15], s=(12*.72)**2, color=color)
            self.text(x+24, y, 'Unknown' if key == 'unknown' else label, 24)
            self.count_labels.append(self.text(x+468, y, '', 24, color, True, True, True))
        self.text(56, 1847, 'Scheduled traffic \u00b7 Interpolated positions \u00b7 Provisional coverage', 19, MUTED)
        self.text(56, 1876, 'Boundary: Survey of India \u00b7 Noncommercial use only', 17, MUTED)
        self.text(56, 1898, 'Tracks: \u00a9 OpenStreetMap contributors \u00b7 ODbL', 16, MUTED)
        self.chart = self.figure.add_axes((100/WIDTH, (HEIGHT-1798)/HEIGHT, 924/WIDTH, 102/HEIGHT))
        ceiling = chart_ceiling(max(self.series[1]))
        times, counts = self.series
        self.chart.fill_between(times, counts, step='post', color='#D4E0D6', linewidth=0)
        self.chart.step(times, counts, where='post', color='#658775', linewidth=1.44)
        self.chart.set(xlim=(0, 86400), ylim=(0, ceiling), facecolor=BACKGROUND)
        self.chart.spines[['top', 'right']].set_visible(False)
        for side in ('left', 'bottom'):
            self.chart.spines[side].set_color('#A4B2A8')
            self.chart.spines[side].set_linewidth(.72)
        self.chart.set_xticks([0, 21600, 43200, 64800, 86400], ['00:00', '06:00', '12:00', '18:00', '24:00'])
        self.chart.set_yticks([0, ceiling], ['0', f'{ceiling:,}'])
        self.chart.tick_params(axis='both', length=0, pad=9, colors=MUTED)
        for label in self.chart.get_xticklabels()+self.chart.get_yticklabels():
            label.set_fontproperties(self.face(18))
        self.chart.get_xticklabels()[-1].set_horizontalalignment('right')
        self.clock = self.text(1024, 89, '', 60, bold=True, right=True, animated=True)
        self.heading = self.text(56, 1610, '', 24, bold=True, animated=True)
        self.cursor = self.chart.axvline(0, ymax=1.12, color='#D77916', linewidth=2.16, clip_on=False, animated=True)
        self.cursor_dot, = self.chart.plot([], [], 'o', color='#D77916', markersize=5.76, clip_on=False, animated=True)
        self.trails = LineCollection([], linewidths=2.88, capstyle='round', joinstyle='round', animated=True)
        self.ax.add_collection(self.trails)
        self.halos = self.ax.scatter([], [], s=(15*.72)**2, edgecolors='none', animated=True)
        self.dots = self.ax.scatter([], [], s=(11*.72)**2, linewidths=.72, animated=True)
        self.labels = []
        for (name, _, _, dx, dy), (x, y) in zip(CITIES, anchors):
            label = self.text(x+dx, y+dy, name, 26, animated=True)
            label.set_path_effects([effects.withStroke(linewidth=2.88, foreground=BACKGROUND)])
            self.labels.append(label)
        self.prepare_routes(dataset['journeys'])
        self.canvas.draw()
        self.background = self.canvas.copy_from_bbox(self.figure.bbox)

    @staticmethod
    def face(size, bold=False):
        return FontProperties(fname=str(ROOT/'assets'/'fonts'/('Lato-Bold.ttf' if bold else 'Lato-Regular.ttf')), size=size*.72)

    def text(self, x, y, value, size, color=INK, bold=False, right=False, animated=False):
        return self.ax.text(x, y, value, color=color, fontproperties=self.face(size, bold),
                            ha='right' if right else 'left', va='top', animated=animated)

    def prepare_routes(self, journeys):
        self.intervals, starts, ends, self.routes = [], [], [], []
        for original in journeys:
            journey = dict(original)
            points, distances = display_points(journey['route_pixels']), np.asarray(journey['distances'])
            segments = journey['segments']
            bounds, first = [], 0
            for i, segment in enumerate(segments):
                self.intervals.append((journey, points, distances, i))
                starts.append(segment['start'])
                ends.append(segment['end'])
                if i+1 == len(segments) or abs(segment['end']-segments[i+1]['start']) >= 1e-6 or abs(segment['to']-segments[i+1]['from']) >= 1e-5:
                    bounds.extend([(first, i)]*(i-first+1))
                    first = i+1
            journey['_motion'] = bounds, np.array([s['start'] for s in segments])
            self.routes.append((journey, points, distances))
        self.starts, self.ends, self.holds = np.array(starts), np.array(ends), {}

    def __call__(self, video_time=0):
        hold = 0 if video_time < INTRO else INTRO+REPLAY if video_time >= INTRO+REPLAY else None
        if hold is None:
            return self.draw(video_time)
        if hold not in self.holds:
            self.holds[hold] = self.draw(hold)
        return self.holds[hold]

    def draw(self, video_time):
        second = second_at(video_time)
        active = [self.intervals[i] for i in np.flatnonzero((self.starts <= second) & (second < self.ends))]
        counts = dict.fromkeys(self.categories, 0)
        positions, trails, colors, halos, whites = [], [], [], [], []
        for journey, points, distances, index in active:
            counts[journey['category']] += 1
            if not INTRO <= video_time < INTRO+REPLAY:
                continue
            a, b, opacity = motion_sample(journey['segments'], index, second, journey['_motion'])
            endpoints = np.array([np.interp([a, b], distances, points[:, axis]) for axis in (0, 1)]).T
            inside = points[np.searchsorted(distances, a, side='right'):np.searchsorted(distances, b)]
            trails.append(np.vstack((endpoints[0], inside, endpoints[1])))
            positions.append(endpoints[1])
            rgba = to_rgba(self.categories[journey['category']][1], opacity)
            colors.append(rgba)
            halos.append((*[v*.18+background*.82 for v, background in zip(rgba[:3], to_rgba(BACKGROUND)[:3])], opacity))
            whites.append((1, 1, 1, opacity))
        self.canvas.restore_region(self.background)
        self.trails.set_segments(trails)
        self.trails.set_colors(colors)
        for artist, faces in ((self.halos, halos), (self.dots, colors)):
            artist.set_offsets(np.asarray(positions).reshape(-1, 2))
            artist.set_facecolors(faces)
        self.dots.set_edgecolors(whites)
        minute = min(1440, int(second//60))
        self.clock.set_text(f'{minute//60:02d}:{minute%60:02d}')
        self.heading.set_text(f'{sum(counts.values()):,} trains underway now')
        for label, count in zip(self.count_labels, counts.values()):
            label.set_text(f'{count:,}')
        self.cursor.set_xdata([second, second])
        self.cursor_dot.set_data([second], [sum(counts.values())])
        for artist in (self.trails, self.halos, self.dots, self.clock, self.heading, *self.count_labels, *self.labels):
            self.ax.draw_artist(artist)
        self.chart.draw_artist(self.cursor)
        self.chart.draw_artist(self.cursor_dot)
        return Image.fromarray(np.asarray(self.canvas.buffer_rgba())[:, :, :3].copy())
