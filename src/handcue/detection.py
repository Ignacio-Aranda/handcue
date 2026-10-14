"""Hand, face and body gesture detection with MediaPipe Tasks.

Each frame produces a Result with:
  signals  gestures active right now, {gesture_id: {sides}}; the side is "left" or
           "right" for hands and "*" for everything else
  events   one-off things that just happened, [(gesture_id, side)]
  and the landmarks needed to draw the overlay.
"""
import math
from collections import deque
from dataclasses import dataclass, field

import mediapipe as mp
from mediapipe.tasks.python import BaseOptions, vision

from . import models

MODEL_GESTURES = {
    "Closed_Fist": "hand:fist",
    "Open_Palm": "hand:open_palm",
    "Pointing_Up": "hand:pointing_up",
    "Thumb_Down": "hand:thumb_down",
    "Thumb_Up": "hand:thumb_up",
    "Victory": "hand:victory",
    "ILoveYou": "hand:i_love_you",
}
FINGERS = {"index": (8, 6), "middle": (12, 10), "ring": (16, 14), "little": (20, 18)}
MODEL_FILES = {"hands": "gesture_recognizer.task", "face": "face_landmarker.task",
               "body": "pose_landmarker_lite.task", "segmentation": "selfie_segmenter.tflite"}


@dataclass
class Result:
    signals: dict = field(default_factory=dict)
    events: list = field(default_factory=list)
    hands: list = field(default_factory=list)   # {points, side, gesture}
    faces: list = field(default_factory=list)   # {points, gestures}
    bodies: list = field(default_factory=list)  # {points, visible, gestures}

    def activate(self, gesture, side="*"):
        self.signals.setdefault(gesture, set()).add(side)


def model_path(kind, log=print):
    return models.path(MODEL_FILES[kind], log)


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


# --- hands

def extended_fingers(p):
    # Distances to the wrist rather than "tip above knuckle", so a rotated hand works too.
    size = dist(p[0], p[9]) or 1.0
    ext = {f: dist(p[0], p[tip]) > dist(p[0], p[pip]) * 1.15 for f, (tip, pip) in FINGERS.items()}
    ext["thumb"] = dist(p[4], p[9]) > 0.6 * size and dist(p[4], p[5]) > 0.35 * size
    return ext


def classify_hand(p, model_gesture, score, threshold):
    """p: the 21 hand landmarks in pixels. The model knows seven gestures; OK, pinch,
    rock, call me and three are recognized here with simple rules."""
    size = dist(p[0], p[9]) or 1.0
    e = extended_fingers(p)
    model = MODEL_GESTURES.get(model_gesture) if score >= threshold else None

    # Fingertips together but the index not fully curled: a fist with the thumb
    # resting on the index also has the tips together.
    if dist(p[4], p[8]) < 0.3 * size and dist(p[0], p[8]) > 0.9 * size and model != "hand:fist":
        return "hand:ok" if e["middle"] and e["ring"] and e["little"] else "hand:pinch"
    if model:
        return model
    if e["index"] and e["little"] and not e["middle"] and not e["ring"]:
        return "hand:i_love_you" if e["thumb"] else "hand:rock"
    if e["thumb"] and e["little"] and not (e["index"] or e["middle"] or e["ring"]):
        return "hand:call_me"
    if e["index"] and e["middle"] and e["ring"] and not e["little"]:
        return "hand:three"
    return None


class SwipeDetector:
    """Fast movements of an open hand, tracked separately for each hand."""

    WINDOW = 0.4  # seconds

    def __init__(self):
        self.history = {}
        self.blocked_until = {}

    def update(self, side, center, is_open, now, threshold):
        h = self.history.setdefault(side, deque())
        if not is_open or now < self.blocked_until.get(side, 0):
            h.clear()
            return None
        h.append((now, center[0], center[1]))
        while h and now - h[0][0] > self.WINDOW:
            h.popleft()
        _t, x0, y0 = h[0]
        dx, dy = center[0] - x0, center[1] - y0
        event = None
        if abs(dx) > threshold and abs(dx) > 1.5 * abs(dy):
            event = "hand:swipe_right" if dx > 0 else "hand:swipe_left"
        elif abs(dy) > threshold and abs(dy) > 1.5 * abs(dx):
            event = "hand:swipe_down" if dy > 0 else "hand:swipe_up"
        if event:
            h.clear()
            self.blocked_until[side] = now + 0.7
        return event

    def forget_missing(self, seen):
        for side in list(self.history):
            if side not in seen:
                self.history[side].clear()


# --- detectors

class Detectors:
    def __init__(self, log=print):
        self.log = log
        self.hands = self.face = self.body = None
        self.signature = None
        self.swipes = SwipeDetector()
        self.tilt_baseline = None
        self.someone_there = False
        self.last_seen = 0.0
        self.frame_count = 0
        self.last_face = self.last_body = None  # (signals, data) from the last processed frame

    def configure(self, cfg):
        """(Re)creates the models when the enabled detectors or the limits change."""
        det = cfg["detectors"]
        signature = (det["hands"], det["face"], det["body"], cfg["max_hands"], cfg["max_people"])
        if signature == self.signature:
            return
        self.close()
        mode = vision.RunningMode.VIDEO
        if det["hands"]:
            self.hands = vision.GestureRecognizer.create_from_options(vision.GestureRecognizerOptions(
                base_options=BaseOptions(model_asset_path=model_path("hands", self.log)),
                running_mode=mode, num_hands=cfg["max_hands"],
                min_hand_detection_confidence=0.6, min_tracking_confidence=0.5))
        if det["face"]:
            self.face = vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(
                base_options=BaseOptions(model_asset_path=model_path("face", self.log)),
                running_mode=mode, num_faces=1, output_face_blendshapes=True))
        if det["body"]:
            self.body = vision.PoseLandmarker.create_from_options(vision.PoseLandmarkerOptions(
                base_options=BaseOptions(model_asset_path=model_path("body", self.log)),
                running_mode=mode, num_poses=cfg["max_people"],
                min_pose_detection_confidence=0.6))
        self.signature = signature

    def close(self):
        for m in (self.hands, self.face, self.body):
            if m:
                m.close()
        self.hands = self.face = self.body = None
        self.signature = None
        self.last_face = self.last_body = None

    def process(self, rgb, ts_ms, now, cfg):
        """rgb is already mirrored, as the user sees it."""
        h, w = rgb.shape[:2]
        img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        r = Result()
        t = cfg["thresholds"]
        if self.hands:
            self._hands(self.hands.recognize_for_video(img, ts_ms), r, w, h, now, t)
        # With both face and body enabled they take turns, reusing the other one's last
        # result. Almost doubles the frame rate, and faces and bodies move slowly anyway.
        self.frame_count += 1
        both = self.face and self.body
        if self.face:
            if not both or self.frame_count % 2 == 0:
                f = Result()
                self._face(self.face.detect_for_video(img, ts_ms), f, w, h, t)
                self.last_face = (f.signals, f.faces)
            self._merge(r, self.last_face, "faces")
        if self.body:
            if not both or self.frame_count % 2 == 1:
                b = Result()
                self._body(self.body.detect_for_video(img, ts_ms), b, w, h, now)
                self.last_body = (b.signals, b.bodies)
                r.events += b.events
            self._merge(r, self.last_body, "bodies")
        return r

    @staticmethod
    def _merge(r, last, attr):
        if last:
            signals, data = last
            for g, sides in signals.items():
                r.signals.setdefault(g, set()).update(sides)
            setattr(r, attr, data)

    def _hands(self, res, r, w, h, now, t):
        seen = set()
        for landmarks, gestures, handedness in zip(res.hand_landmarks, res.gestures, res.handedness,
                                                    strict=True):
            # The input is mirrored, which is what the model expects, so the label is right.
            side = "left" if handedness[0].category_name == "Left" else "right"
            seen.add(side)
            pts = [(lm.x * w, lm.y * h) for lm in landmarks]
            top = gestures[0] if gestures else None
            gesture = classify_hand(pts, top.category_name if top else "", top.score if top else 0.0,
                                    t["hand_confidence"])
            if gesture:
                r.activate(gesture, side)
            r.hands.append({"points": pts, "side": side, "gesture": gesture})

            center = (sum(landmarks[i].x for i in (0, 5, 9, 13, 17)) / 5,
                      sum(landmarks[i].y for i in (0, 5, 9, 13, 17)) / 5)
            is_open = gesture == "hand:open_palm" or sum(extended_fingers(pts).values()) >= 4
            event = self.swipes.update(side, center, is_open, now, t["swipe"])
            if event:
                r.events.append((event, side))
        self.swipes.forget_missing(seen)

    def _face(self, res, r, w, h, t):
        for landmarks, blendshapes in zip(res.face_landmarks, res.face_blendshapes, strict=True):
            b = {c.category_name: c.score for c in blendshapes}
            # Mirrored image: the model's "right eye" is the user's left eye.
            left, right = b.get("eyeBlinkRight", 0), b.get("eyeBlinkLeft", 0)
            wink = t["wink"]
            brows = max(b.get("browInnerUp", 0), (b.get("browOuterUpLeft", 0) + b.get("browOuterUpRight", 0)) / 2)
            checks = {
                "face:smile": (b.get("mouthSmileLeft", 0) + b.get("mouthSmileRight", 0)) / 2 > t["smile"],
                "face:mouth_open": b.get("jawOpen", 0) > t["mouth_open"],
                "face:wink_left": left > wink and right < wink * 0.6,
                "face:wink_right": right > wink and left < wink * 0.6,
                "face:eyes_closed": left > wink and right > wink,
                "face:brows_up": brows > t["brows"],
                "face:kiss": b.get("mouthPucker", 0) > t["kiss"],
                "face:puff_cheeks": b.get("cheekPuff", 0) > t["cheeks"],
            }

            # Turn: where the nose sits between both sides of the face (0.5 = facing forward).
            nose = landmarks[1]
            a, c = sorted((landmarks[234].x, landmarks[454].x))
            if c - a > 1e-3:
                turn = (nose.x - a) / (c - a) - 0.5
                checks["face:turn_left"] = turn < -t["head_turn"]
                checks["face:turn_right"] = turn > t["head_turn"]
            # Tilt: nose between eyes and chin, relative to the user's normal posture.
            eyes_y = (landmarks[33].y + landmarks[263].y) / 2
            if landmarks[152].y - eyes_y > 1e-3:
                tilt = (nose.y - eyes_y) / (landmarks[152].y - eyes_y)
                if self.tilt_baseline is None:
                    self.tilt_baseline = tilt
                d = tilt - self.tilt_baseline
                if abs(d) < t["head_tilt"]:  # only recalibrate while looking ahead
                    self.tilt_baseline += 0.02 * d
                checks["face:look_up"] = d < -t["head_tilt"]
                checks["face:look_down"] = d > t["head_tilt"]

            gestures = [g for g, on in checks.items() if on]
            for g in gestures:
                r.activate(g)
            r.faces.append({"points": [(lm.x * w, lm.y * h) for lm in landmarks], "gestures": gestures})

    def _body(self, res, r, w, h, now):
        for landmarks in res.pose_landmarks:
            pts = [(lm.x * w, lm.y * h) for lm in landmarks]
            vis = [(lm.visibility or 0) > 0.5 for lm in landmarks]
            nose, ls, rs, lw, rw = pts[0], pts[11], pts[12], pts[15], pts[16]
            shoulders = dist(ls, rs) or 1.0
            left_ok, right_ok = vis[15] and vis[11], vis[16] and vis[12]
            left_up = left_ok and vis[0] and lw[1] < nose[1]
            right_up = right_ok and vis[0] and rw[1] < nose[1]
            chest_top, chest_bottom = ls[1], ls[1] + 2.2 * shoulders
            checks = {
                "body:arms_up": left_up and right_up,
                "body:hand_raised": left_up or right_up,
                "body:t_pose": (left_ok and right_ok and abs(lw[1] - ls[1]) < 0.6 * shoulders
                                and abs(rw[1] - rs[1]) < 0.6 * shoulders and abs(lw[0] - rw[0]) > 2.8 * shoulders),
                "body:arms_crossed": (left_ok and right_ok and chest_top < lw[1] < chest_bottom
                                      and chest_top < rw[1] < chest_bottom
                                      and (lw[0] - rw[0]) * (ls[0] - rs[0]) < 0),
            }
            gestures = [g for g, on in checks.items() if on]
            for g in gestures:
                r.activate(g)
            r.bodies.append({"points": pts, "visible": vis, "gestures": gestures})

        n = len(r.bodies)
        if n:
            r.activate("body:present")
            self.last_seen = now
            if not self.someone_there:
                self.someone_there = True
                r.events.append(("body:arrives", "*"))
        elif self.someone_there and now - self.last_seen > 2.0:
            self.someone_there = False
            r.events.append(("body:leaves", "*"))
        if n >= 2:
            r.activate("body:several")
