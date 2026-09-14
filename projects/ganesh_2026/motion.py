"""Deterministic camera poses in original-composition pixel coordinates."""

import numpy as np

from artwork import WIDTH, HEIGHT

FPS = 30
OPENING = 0.5
DRAWING = 39.0
PULLBACK = 3.0
HOLD = 2.5
TOTAL = OPENING + DRAWING + PULLBACK + HOLD
ZOOM = 3.0
TRACK_HZ = 240
SAFE_BOX_HALF_SIZE = np.array([60.0, 110.0])
DEAD_ZONE_FOLLOW_TAU = 0.06
FULL_CENTER = np.array([WIDTH / 2, HEIGHT / 2])


def drawing_progress(time):
    return -1.0 if time < OPENING else float(np.clip((time - OPENING) / DRAWING, 0, 1))


class CameraMotion:
    def __init__(self, arc):
        self.times = np.linspace(0, DRAWING, round(DRAWING * TRACK_HZ) + 1)
        tips = arc.points(self.times / DRAWING)
        self.guides = np.empty_like(tips)
        self.centers = np.empty_like(tips)
        self.guides[0] = tips[0]
        self.centers[0] = tips[0]
        weight = 1 - np.exp(-1 / TRACK_HZ / DEAD_ZONE_FOLLOW_TAU)
        for i in range(1, len(tips)):
            # Curves inside the safe box cause no target movement. Once the tip
            # crosses an edge, move the guide only far enough to meet that edge.
            delta = tips[i] - self.guides[i - 1]
            correction = np.sign(delta) * np.maximum(
                np.abs(delta) - SAFE_BOX_HALF_SIZE, 0
            )
            self.guides[i] = self.guides[i - 1] + correction
            self.centers[i] = self.centers[i - 1] + weight * (
                self.guides[i] - self.centers[i - 1]
            )
        self.exit_velocity = (self.centers[-1] - self.centers[-2]) * TRACK_HZ

    def pose(self, time):
        """Return (center_xy, viewport_width); aspect ratio always stays 9:16."""
        elapsed = max(0, time - OPENING)
        if elapsed <= DRAWING:
            center = np.array([np.interp(elapsed, self.times, self.centers[:, axis]) for axis in (0, 1)])
            return center, WIDTH / ZOOM
        if elapsed >= DRAWING + PULLBACK:
            return FULL_CENTER.copy(), float(WIDTH)
        u = (elapsed - DRAWING) / PULLBACK
        # Hermite: match the final tracking velocity, arrive at the full view at rest.
        center = ((2*u**3 - 3*u**2 + 1) * self.centers[-1]
                  + (u**3 - 2*u**2 + u) * PULLBACK * self.exit_velocity
                  + (-2*u**3 + 3*u**2) * FULL_CENTER)
        ease = 6*u**5 - 15*u**4 + 10*u**3
        width = WIDTH / ZOOM + (WIDTH - WIDTH / ZOOM) * ease
        return center, width
