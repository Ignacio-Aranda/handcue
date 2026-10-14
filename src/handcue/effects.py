"""Particle effects drawn on the hands in the preview (fire, laser, shield...)."""
import math
import random

import cv2
import numpy as np

AA = cv2.LINE_AA
MAX_PARTICLES = 1500

COLORS = {  # BGR; fire is computed separately
    "spark": (255, 255, 150),
    "star": (80, 215, 255),
    "portal": (40, 160, 255),
    "orb": (255, 120, 220),
    "laser": (80, 80, 255),
    "bolt": (255, 170, 230),
}


class Particle:
    __slots__ = ("x", "y", "vx", "vy", "life", "max_life", "radius", "kind", "gravity")

    def __init__(self, x, y, vx, vy, life, radius, kind, gravity):
        self.x, self.y, self.vx, self.vy = x, y, vx, vy
        self.life = self.max_life = life
        self.radius, self.kind, self.gravity = radius, kind, gravity


def palm_center(pts):
    idx = (0, 5, 9, 13, 17)
    return (sum(pts[i][0] for i in idx) // 5, sum(pts[i][1] for i in idx) // 5)


def midpoint(a, b):
    return ((a[0] + b[0]) // 2, (a[1] + b[1]) // 2)


def direction(start, end):
    dx, dy = end[0] - start[0], end[1] - start[1]
    n = math.hypot(dx, dy) or 1.0
    return dx / n, dy / n


def fire_color(f):
    """f is the remaining life (1 just born, 0 dead): white-yellow, orange, red."""
    if f > 0.7:
        c = (120, 240, 255)
    elif f > 0.4:
        c = (0, 150, 255)
    else:
        c = (0, 40, 220)
    k = min(1.0, f * 1.5)
    return tuple(int(v * k) for v in c)


def bolt(layer, p1, p2, color, jitter, thickness, segments=10):
    """Zigzag line between two points with a white core."""
    points = [p1]
    for i in range(1, segments):
        t = i / segments
        points.append((int(p1[0] + (p2[0] - p1[0]) * t + random.gauss(0, jitter)),
                       int(p1[1] + (p2[1] - p1[1]) * t + random.gauss(0, jitter))))
    points.append(p2)
    arr = np.array(points, np.int32)
    cv2.polylines(layer, [arr], False, color, thickness, AA)
    cv2.polylines(layer, [arr], False, (255, 255, 255), max(1, thickness // 3), AA)


def draw_star(layer, c, r, color):
    x, y = c
    cv2.line(layer, (x - r, y), (x + r, y), color, 2, AA)
    cv2.line(layer, (x, y - r), (x, y + r), color, 2, AA)
    d = r // 2
    cv2.line(layer, (x - d, y - d), (x + d, y + d), color, 1, AA)
    cv2.line(layer, (x - d, y + d), (x + d, y - d), color, 1, AA)


class Effects:
    def __init__(self):
        self.particles = []
        self.by_gesture = {
            "hand:open_palm": self.shield,
            "hand:fist": self.fire,
            "hand:pointing_up": self.laser,
            "hand:victory": self.bolts,
            "hand:thumb_up": self.stars,
            "hand:pinch": self.orb,
            "hand:ok": self.portal,
        }

    def emit(self, x, y, vx, vy, life, radius, kind, gravity=0.0):
        if len(self.particles) < MAX_PARTICLES:
            self.particles.append(Particle(x, y, vx, vy, life, radius, kind, gravity))

    def apply(self, gesture, pts, s, layer, t):
        """pts: 21 hand landmarks in pixels; s: hand size in pixels."""
        effect = self.by_gesture.get(gesture)
        if effect:
            effect(pts, s, layer, t)

    def shield(self, pts, s, layer, t):
        c = palm_center(pts)
        for i in range(3):
            r = int(s * (1.2 + 0.35 * i + 0.08 * math.sin(t * 6 + i)))
            cv2.circle(layer, c, r, (255, 200 - i * 50, 60), 2, AA)
        hexagon = [(c[0] + int(s * 1.9 * math.cos(t * 1.5 + k * math.pi / 3)),
                    c[1] + int(s * 1.9 * math.sin(t * 1.5 + k * math.pi / 3))) for k in range(6)]
        cv2.polylines(layer, [np.array(hexagon, np.int32)], True, (255, 255, 120), 2, AA)
        for _i in range(3):
            a = random.uniform(0, 2 * math.pi)
            self.emit(c[0] + math.cos(a) * s * 1.9, c[1] + math.sin(a) * s * 1.9,
                      math.cos(a) * 2, math.sin(a) * 2, 20, 3, "spark")

    def fire(self, pts, s, layer, t):
        c = palm_center(pts)
        for _i in range(8):
            self.emit(c[0] + random.gauss(0, s * 0.4), c[1] + random.gauss(0, s * 0.3),
                      random.gauss(0, 0.8), -random.uniform(2, 5), random.randint(15, 30),
                      random.uniform(s * 0.08, s * 0.18), "fire", gravity=-0.15)

    def laser(self, pts, s, layer, t):
        tip = pts[8]
        dx, dy = direction(pts[5], tip)
        end = (int(tip[0] + dx * 3000), int(tip[1] + dy * 3000))
        width = max(3, int(s * 0.12 + 2 * math.sin(t * 40)))  # flicker
        cv2.line(layer, tip, end, (40, 40, 255), width * 2, AA)
        cv2.line(layer, tip, end, (220, 220, 255), max(2, width // 2), AA)
        cv2.circle(layer, tip, int(s * 0.25), (120, 120, 255), -1, AA)
        for _i in range(3):
            self.emit(tip[0], tip[1], random.gauss(0, 3), random.gauss(0, 3), 12, 3, "laser")

    def bolts(self, pts, s, layer, t):
        color = COLORS["bolt"]
        for base, tip in ((5, 8), (9, 12)):
            dx, dy = direction(pts[base], pts[tip])
            for _i in range(2):
                a = math.atan2(dy, dx) + random.gauss(0, 0.35)
                end = (int(pts[tip][0] + math.cos(a) * s * 2.5), int(pts[tip][1] + math.sin(a) * s * 2.5))
                bolt(layer, pts[tip], end, color, s * 0.12, 3)
        bolt(layer, pts[8], pts[12], color, s * 0.08, 2, segments=5)

    def stars(self, pts, s, layer, t):
        p = pts[4]
        cv2.circle(layer, p, int(s * 0.3), (60, 180, 255), 2, AA)
        for _i in range(2):
            self.emit(p[0], p[1], random.gauss(0, 3), -random.uniform(3, 7), 40, max(4, s * 0.08), "star",
                      gravity=0.3)

    def orb(self, pts, s, layer, t):
        c = midpoint(pts[4], pts[8])
        r = int(s * 0.25 * (1 + 0.15 * math.sin(t * 10)))
        cv2.circle(layer, c, r, (255, 100, 220), -1, AA)
        cv2.circle(layer, c, max(2, r // 2), (255, 255, 255), -1, AA)
        for _i in range(3):  # particles pulled into the center
            a = random.uniform(0, 2 * math.pi)
            x, y = c[0] + math.cos(a) * s * 1.2, c[1] + math.sin(a) * s * 1.2
            self.emit(x, y, (c[0] - x) / 15, (c[1] - y) / 15, 15, 3, "orb")

    def portal(self, pts, s, layer, t):
        c = midpoint(pts[4], pts[8])
        r = int(s * 1.3)
        angle = t * 200
        cv2.ellipse(layer, c, (r, r), angle, 0, 300, (40, 160, 255), 3, AA)
        cv2.ellipse(layer, c, (int(r * 0.85), int(r * 0.85)), -angle, 0, 280, (60, 200, 255), 2, AA)
        star = [(c[0] + int(r * 0.75 * math.cos(math.radians(-angle * 0.5) + k * 3 * math.pi / 8)),
                 c[1] + int(r * 0.75 * math.sin(math.radians(-angle * 0.5) + k * 3 * math.pi / 8)))
                for k in range(16)]
        cv2.polylines(layer, [np.array(star, np.int32)], True, (30, 120, 230), 1, AA)
        for _i in range(6):
            a = random.uniform(0, 2 * math.pi)
            self.emit(c[0] + math.cos(a) * r, c[1] + math.sin(a) * r,
                      -math.sin(a) * 4 + math.cos(a), math.cos(a) * 4 + math.sin(a), 20, 3, "portal")

    def update(self, layer):
        alive = []
        for p in self.particles:
            p.life -= 1
            if p.life <= 0:
                continue
            p.vx *= 0.98
            p.vy = p.vy * 0.98 + p.gravity
            p.x += p.vx
            p.y += p.vy
            f = p.life / p.max_life
            pos = (int(p.x), int(p.y))
            r = max(1, int(p.radius * (0.4 + 0.6 * f)))
            if p.kind == "fire":
                cv2.circle(layer, pos, r, fire_color(f), -1, AA)
            else:
                color = tuple(int(v * f) for v in COLORS[p.kind])
                if p.kind == "star":
                    draw_star(layer, pos, r * 2, color)
                else:
                    cv2.circle(layer, pos, r, color, -1, AA)
            alive.append(p)
        self.particles = alive

    @staticmethod
    def compose(frame, layer):
        """Adds the effects layer to the frame with a blurred glow."""
        h, w = frame.shape[:2]
        # Blurring at quarter resolution is far cheaper and looks just as smooth.
        small = cv2.resize(layer, (w // 4, h // 4), interpolation=cv2.INTER_AREA)
        glow = cv2.resize(cv2.GaussianBlur(small, (0, 0), 4), (w, h), interpolation=cv2.INTER_LINEAR)
        return cv2.add(cv2.add(frame, layer), cv2.convertScaleAbs(glow, alpha=1.8))
