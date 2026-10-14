"""Multiplayer Fruit Ninja with a webcam: slice the fruit with your index fingertip.

The screen is split into vertical lanes, one per player (P1 on the left, P2 on
the right...). A slice scores for the player whose lane the finger is in. Hitting
a bomb costs 10 points. Whoever has the most points when time runs out wins.

Usage:  python examples/fruit_ninja.py [players]   (2 by default, up to 4)
Keys:   space = start / restart, f = fullscreen, q = quit
"""
import math
import random
import sys
import time
from collections import deque

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import BaseOptions, vision

from handcue import models

GAME_SECONDS = 60
INDEX_TIP = 8  # MediaPipe hand landmark
AA = cv2.LINE_AA
FONT = cv2.FONT_HERSHEY_DUPLEX

# name, radius (for a 540 px tall image), skin BGR, flesh BGR
FRUITS = [
    ("watermelon", 46, (40, 140, 40), (70, 70, 235)),
    ("orange", 32, (0, 140, 255), (80, 200, 255)),
    ("apple", 30, (40, 40, 200), (170, 230, 240)),
    ("lemon", 28, (40, 225, 240), (160, 250, 250)),
    ("kiwi", 28, (40, 90, 120), (60, 200, 120)),
]
WATERMELON = FRUITS[0]
PLAYER_COLORS = [(255, 160, 40), (60, 60, 255), (60, 220, 60), (40, 220, 240)]


def point_segment_distance(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    l2 = dx * dx + dy * dy
    t = 0.0 if l2 == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / l2))
    return math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy))


def draw_text(img, text, pos, scale, color, thickness=2, centered=False):
    if centered:
        (tw, th), _baseline = cv2.getTextSize(text, FONT, scale, thickness)
        pos = (int(pos[0] - tw / 2), int(pos[1] + th / 2))
    cv2.putText(img, text, pos, FONT, scale, (0, 0, 0), thickness + 4, AA)
    cv2.putText(img, text, pos, FONT, scale, color, thickness, AA)


class Fruit:
    def __init__(self, x, y, vx, vy, kind, scale):
        """kind is an entry of FRUITS, or None for a bomb."""
        self.x, self.y, self.vx, self.vy = x, y, vx, vy
        self.bomb = kind is None
        if self.bomb:
            self.name, self.r, self.skin, self.flesh = "bomb", 32 * scale, (35, 35, 35), None
        else:
            self.name, r, self.skin, self.flesh = kind
            self.r = r * scale
        self.angle = random.uniform(0, 360)
        self.spin = random.uniform(-200, 200)

    def move(self, dt, g):
        self.vy += g * dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.angle += self.spin * dt

    def draw(self, img):
        c, r = (int(self.x), int(self.y)), int(self.r)
        if self.bomb:
            a = math.radians(self.angle)
            fuse_start = (int(self.x + math.cos(a) * r * 0.9), int(self.y + math.sin(a) * r * 0.9))
            fuse_end = (int(self.x + math.cos(a) * r * 1.35), int(self.y + math.sin(a) * r * 1.35))
            cv2.line(img, fuse_start, fuse_end, (60, 120, 170), 4, AA)
            cv2.circle(img, fuse_end, int(4 + 4 * random.random()), (80, 230, 255), -1, AA)
            cv2.circle(img, c, r, (35, 35, 35), -1, AA)
            cv2.circle(img, c, r, (0, 0, 220), 3, AA)
            d = int(r * 0.4)
            cv2.line(img, (c[0] - d, c[1] - d), (c[0] + d, c[1] + d), (0, 0, 220), 4, AA)
            cv2.line(img, (c[0] - d, c[1] + d), (c[0] + d, c[1] - d), (0, 0, 220), 4, AA)
            return
        cv2.circle(img, c, r, self.skin, -1, AA)
        dark = tuple(v // 2 for v in self.skin)
        if self.name == "watermelon":  # stripes
            for k in (-1, 0, 1):
                cv2.ellipse(img, c, (max(1, int(r * (0.25 + 0.3 * abs(k)))), r),
                            self.angle, -60 if k else 0, 60 if k else 360, dark, 3, AA)
        cv2.circle(img, c, r, dark, 2, AA)
        cv2.circle(img, (c[0] - r // 3, c[1] - r // 3), max(2, r // 5), (255, 255, 255), -1, AA)


class Half:
    def __init__(self, fruit, angle, vx, vy):
        self.x, self.y, self.vx, self.vy = fruit.x, fruit.y, vx, vy
        self.r, self.skin, self.flesh = fruit.r, fruit.skin, fruit.flesh
        self.angle, self.spin = angle, random.uniform(-250, 250)

    move = Fruit.move

    def draw(self, img):
        c, r = (int(self.x), int(self.y)), int(self.r)
        cv2.ellipse(img, c, (r, r), self.angle, 0, 180, self.skin, -1, AA)
        cv2.ellipse(img, c, (int(r * 0.85), int(r * 0.85)), self.angle, 0, 180, self.flesh, -1, AA)


class Blade:
    """Trail of one hand's index fingertip."""

    def __init__(self):
        self.trail = deque(maxlen=12)  # (x, y, t)
        self.streak, self.streak_time = 0, 0.0


class Game:
    def __init__(self, players, w, h):
        self.n, self.w, self.h = players, w, h
        self.scale = h / 540
        self.g = 900 * self.scale
        self.min_speed = 700 * self.scale  # px/s the finger needs to slice
        self.state = "menu"
        self.points = [0] * self.n
        self.result = None
        self.fruits, self.halves, self.particles, self.popups = [], [], [], []
        self.blades = {}
        self.next_id = 0
        self.flash = 0.0
        self.started = self.ended = self.next_wave = 0.0
        self.start_fruit = None
        self.place_start_fruit()

    def place_start_fruit(self):
        f = Fruit(self.w / 2, self.h * 0.58, 0, 0, WATERMELON, self.scale * 1.6)
        f.spin = 40
        self.start_fruit = f

    def start(self, now):
        self.state = "playing"
        self.points = [0] * self.n
        self.fruits.clear()
        self.started = now
        self.next_wave = now + 0.8
        self.start_fruit = None

    def finish(self, now):
        self.state = "over"
        self.ended = now
        best = max(self.points)
        winners = [i for i, p in enumerate(self.points) if p == best]
        if self.n == 1:
            self.result = f"{best} POINTS"
        elif len(winners) > 1:
            self.result = "DRAW!"
        else:
            self.result = f"P{winners[0] + 1} WINS!"
        self.fruits = [f for f in self.fruits if not f.bomb]

    def update_hands(self, tips, now):
        """Matches each fingertip with the closest blade from the previous frame."""
        max_jump = 0.3 * self.w  # a fast slash covers a lot between frames
        pairs = sorted((math.dist(p, b.trail[-1][:2]), i, bid)
                       for i, p in enumerate(tips) for bid, b in self.blades.items())
        assigned, used = {}, set()
        for d, i, bid in pairs:
            if d < max_jump and i not in assigned and bid not in used:
                assigned[i] = bid
                used.add(bid)
        blades = {}
        for i, p in enumerate(tips):
            bid = assigned.get(i)
            if bid is None:
                bid, self.next_id = self.next_id, self.next_id + 1
                blades[bid] = Blade()
            else:
                blades[bid] = self.blades[bid]
            blades[bid].trail.append((p[0], p[1], now))
        self.blades = blades

    def player_at(self, x):
        return min(self.n - 1, max(0, int(x * self.n / self.w)))

    def check_slices(self, now):
        for blade in self.blades.values():
            if len(blade.trail) < 2:
                continue
            (ax, ay, ta), (bx, by, tb) = blade.trail[-2], blade.trail[-1]
            if tb - ta <= 0 or math.hypot(bx - ax, by - ay) / (tb - ta) < self.min_speed:
                continue
            a, b = (ax, ay), (bx, by)
            angle = math.degrees(math.atan2(by - ay, bx - ax))
            player = self.player_at(bx)

            sf = self.start_fruit
            if sf and point_segment_distance((sf.x, sf.y), a, b) < sf.r * 1.1:
                self.split(sf, angle)
                self.start(now)
                return

            if self.state != "playing":
                continue
            for f in list(self.fruits):
                if point_segment_distance((f.x, f.y), a, b) < f.r * 1.15:
                    self.fruits.remove(f)
                    if f.bomb:
                        self.explode(f, player)
                    else:
                        self.split(f, angle)
                        self.score(blade, player, f, now)

    def score(self, blade, player, f, now):
        # Several fruits in the same slash make a combo.
        blade.streak = blade.streak + 1 if now - blade.streak_time < 0.35 else 1
        blade.streak_time = now
        self.points[player] += 1
        self.add_popup(f.x, f.y, "+1", PLAYER_COLORS[player % len(PLAYER_COLORS)])
        if blade.streak >= 3:
            self.points[player] += 1
            self.add_popup(f.x, f.y - 40 * self.scale, f"COMBO x{blade.streak}!", (0, 220, 255))

    def split(self, f, angle):
        # Both halves fly off perpendicular to the cut.
        nx, ny = math.cos(math.radians(angle + 90)), math.sin(math.radians(angle + 90))
        v = 160 * self.scale
        self.halves.append(Half(f, angle, f.vx + nx * v, f.vy + ny * v))
        self.halves.append(Half(f, angle + 180, f.vx - nx * v, f.vy - ny * v))
        for _i in range(18):
            a = random.uniform(0, 2 * math.pi)
            speed = random.uniform(100, 400) * self.scale
            self.particles.append([f.x, f.y, math.cos(a) * speed, math.sin(a) * speed,
                                   0.6, 0.6, f.flesh, random.uniform(2, 5) * self.scale])

    def explode(self, f, player):
        self.points[player] = max(0, self.points[player] - 10)
        self.add_popup(f.x, f.y, "-10", (0, 0, 255))
        self.flash = 0.25
        for _i in range(50):
            a = random.uniform(0, 2 * math.pi)
            speed = random.uniform(150, 700) * self.scale
            color = random.choice([(255, 255, 255), (80, 220, 255), (0, 120, 255), (60, 60, 60)])
            self.particles.append([f.x, f.y, math.cos(a) * speed, math.sin(a) * speed,
                                   0.8, 0.8, color, random.uniform(3, 8) * self.scale])

    def add_popup(self, x, y, text, color):
        self.popups.append([x, y, text, color, 0.9])

    def launch_wave(self, now):
        progress = (now - self.started) / GAME_SECONDS
        # The same amount of fruit in every lane keeps it fair.
        count = random.randint(1, 1 + int(progress * 2.5))
        lane = self.w / self.n
        for j in range(self.n):
            for _i in range(count):
                bomb = random.random() < 0.10 + 0.10 * progress
                x = random.uniform(j * lane + 0.15 * lane, (j + 1) * lane - 0.15 * lane)
                peak = random.uniform(0.55, 0.85) * self.h
                self.fruits.append(Fruit(x, self.h + 60 * self.scale, random.uniform(-0.15, 0.15) * lane,
                                         -math.sqrt(2 * self.g * peak),
                                         None if bomb else random.choice(FRUITS), self.scale))
        self.next_wave = now + 1.6 - 0.8 * progress

    def update(self, now, dt):
        if self.state == "playing":
            if now - self.started >= GAME_SECONDS:
                self.finish(now)
            elif now >= self.next_wave:
                self.launch_wave(now)
        elif self.state == "over" and now - self.ended > 2.5:
            self.state = "menu"
            self.place_start_fruit()

        if self.start_fruit:  # floats in the middle
            self.start_fruit.y = self.h * 0.58 + math.sin(now * 3) * 10 * self.scale
            self.start_fruit.angle += self.start_fruit.spin * dt

        self.check_slices(now)

        bottom = self.h + 120 * self.scale
        for f in self.fruits + self.halves:
            f.move(dt, self.g)
        self.fruits = [f for f in self.fruits if f.y < bottom or f.vy < 0]
        self.halves = [h for h in self.halves if h.y < bottom]

        for p in self.particles:
            p[3] += self.g * 0.6 * dt
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            p[4] -= dt
        self.particles = [p for p in self.particles if p[4] > 0]
        for p in self.popups:
            p[1] -= 60 * self.scale * dt
            p[4] -= dt
        self.popups = [p for p in self.popups if p[4] > 0]
        self.flash = max(0.0, self.flash - dt)

    def draw(self, img, now):
        w, h, n = self.w, self.h, self.n
        for j in range(1, n):
            x = int(j * w / n)
            cv2.line(img, (x, 0), (x, h), (200, 200, 200), 1, AA)

        for f in self.fruits:
            f.draw(img)
        for half in self.halves:
            half.draw(img)
        if self.start_fruit:
            self.start_fruit.draw(img)
        for x, y, _vx, _vy, life, max_life, color, r in self.particles:
            k = life / max_life
            cv2.circle(img, (int(x), int(y)), max(1, int(r * (0.5 + 0.5 * k))), color, -1, AA)

        for blade in self.blades.values():
            # Only the last 0.15 s of the trail, thicker towards the tip.
            pts = [(int(x), int(y)) for x, y, t in blade.trail if now - t < 0.15]
            x, y, _t = blade.trail[-1]
            color = PLAYER_COLORS[self.player_at(x) % len(PLAYER_COLORS)]
            for i in range(1, len(pts)):
                g = max(1, int(i * 10 * self.scale / len(pts)))
                cv2.line(img, pts[i - 1], pts[i], color, g + 4, AA)
                cv2.line(img, pts[i - 1], pts[i], (255, 255, 255), max(1, g // 2), AA)
            cv2.circle(img, (int(x), int(y)), int(7 * self.scale), color, -1, AA)
            cv2.circle(img, (int(x), int(y)), int(7 * self.scale), (255, 255, 255), 2, AA)

        for x, y, text, color, _life in self.popups:
            draw_text(img, text, (x, y), 1.0 * self.scale, color, 2, centered=True)

        for j in range(n):  # each score at the top of its lane
            color = PLAYER_COLORS[j % len(PLAYER_COLORS)]
            draw_text(img, f"P{j + 1}: {self.points[j]}", (int(j * w / n + 20), int(45 * self.scale)),
                      1.2 * self.scale, color)

        if self.state == "playing":
            remaining = max(0, GAME_SECONDS - (now - self.started))
            color = (0, 0, 255) if remaining <= 10 else (255, 255, 255)
            draw_text(img, f"{int(math.ceil(remaining))}", (w / 2, h - 40 * self.scale),
                      1.6 * self.scale, color, 3, centered=True)
        else:
            draw_text(img, "FRUIT NINJA", (w / 2, h * 0.2), 2.2 * self.scale, (40, 200, 255), 4, centered=True)
            if self.result:
                draw_text(img, self.result, (w / 2, h * 0.34), 1.6 * self.scale, (255, 255, 255), 3, centered=True)
            if self.start_fruit:
                msg = "Slice the watermelon to play" + (" again" if self.result else "")
                draw_text(img, msg, (w / 2, h * 0.82), 0.9 * self.scale, (255, 255, 255), 2, centered=True)

        if self.flash > 0:
            k = min(0.8, self.flash * 3)
            img[:] = cv2.addWeighted(img, 1 - k, np.full_like(img, 255), k, 0)


def main():
    players = max(1, min(4, int(sys.argv[1]) if len(sys.argv) > 1 else 2))

    cap = cv2.VideoCapture(0, cv2.CAP_V4L2)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    cap.set(cv2.CAP_PROP_FPS, 60)
    ok, frame = cap.read()
    if not ok:
        sys.exit("Cannot open the camera (is another program using it?)")

    hands = vision.HandLandmarker.create_from_options(vision.HandLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=models.path("hand_landmarker.task")),
        running_mode=vision.RunningMode.VIDEO,
        num_hands=2 * players,
        min_hand_detection_confidence=0.5,
        min_tracking_confidence=0.5,
    ))

    h, w = frame.shape[:2]
    game = Game(players, w, h)
    window = "Fruit Ninja (space: start, f: fullscreen, q: quit)"
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window, w, h)
    fullscreen = False

    t0 = previous = time.monotonic()
    ts_prev, fps = -1, 0.0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        now = time.monotonic()
        dt = min(now - previous, 0.05)
        previous = now
        fps = 0.9 * fps + 0.1 / max(dt, 1e-3)

        frame = cv2.flip(frame, 1)
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        ts_prev = max(ts_prev + 1, int((now - t0) * 1000))  # VIDEO mode needs increasing timestamps
        res = hands.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), ts_prev)

        tips = [(lms[INDEX_TIP].x * w, lms[INDEX_TIP].y * h) for lms in res.hand_landmarks]
        game.update_hands(tips, now)
        game.update(now, dt)

        img = cv2.convertScaleAbs(frame, alpha=0.55)  # dimmed camera image as the background
        game.draw(img, now)
        cv2.putText(img, f"{fps:.0f} fps", (10, h - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180, 180, 180), 1, AA)
        cv2.imshow(window, img)

        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            break
        if key == ord(" "):
            game.start(now)
        if key == ord("f"):
            fullscreen = not fullscreen
            cv2.setWindowProperty(window, cv2.WND_PROP_FULLSCREEN,
                                  cv2.WINDOW_FULLSCREEN if fullscreen else cv2.WINDOW_NORMAL)

    cap.release()
    cv2.destroyAllWindows()
    hands.close()


if __name__ == "__main__":
    main()
