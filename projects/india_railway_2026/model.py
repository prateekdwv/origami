"""Timetable positions and half-open interval counts shared by rendering and audits."""
import numpy as np
from settings import CATEGORIES, REPLAY


def position(journey, second, arrays=None):
    for segment in journey["segments"]:
        if segment["start"] <= second < segment["end"]:
            alpha = (second-segment["start"])/(segment["end"]-segment["start"])
            distance = segment["from"] + alpha*(segment["to"]-segment["from"])
            points, distances = arrays if arrays is not None else (np.asarray(journey["route_pixels"]), np.asarray(journey["distances"]))
            return np.array([np.interp(distance, distances, points[:, axis]) for axis in (0, 1)])
    return None


def active_counts(journeys, second, categories=CATEGORIES):
    counts = dict.fromkeys(categories, 0)
    for journey in journeys:
        if any(s["start"] <= second < s["end"] for s in journey["segments"]):
            counts[journey["category"]] += 1
    return counts


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
