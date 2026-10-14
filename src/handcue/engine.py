"""The capture thread: camera -> detectors -> bindings/actions -> preview."""
import copy
import math
import os
import threading
import time
from datetime import datetime

import cv2
import numpy as np
from mediapipe.tasks.python import vision
from PySide6.QtCore import QPointF, QRectF, Qt, QThread, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen

from . import virtual_camera
from .camera import has_framing, read_framing, write_framing
from .catalog import INTERNAL_ACTIONS, RECOGNIZED_PREFIX, gesture
from .config import photo_folder
from .desktop_input import BTN_LEFT, BTN_RIGHT
from .detection import Detectors, Result, dist, model_path
from .effects import Effects
from .i18n import _
from .triggers import TriggerState

HAND_CONNECTIONS = [(c.start, c.end) for c in vision.HandLandmarksConnections.HAND_CONNECTIONS]
POSE_CONNECTIONS = [(c.start, c.end) for c in vision.PoseLandmarksConnections.POSE_LANDMARKS]
SIDE_COLORS = {"left": (255, 170, 60), "right": (60, 120, 255)}  # BGR
MAX_AUTO_ZOOM = 2.5        # digital zoom loses quality, so auto framing stops here
TARGET_FACE_HEIGHT = 0.36  # fraction of the frame height the face should fill


class CoverDetector:
    """Notices the physical privacy shutter (or a hand over the lens).

    Many webcams do not report the shutter in software; the image just becomes a
    flat surface. Measured on a Facecam Neo: standard deviation around 3 and no
    edges, against tens and a few percent of edge pixels for a real scene. With
    hysteresis so it does not flicker: 1 s covered to pause, 0.5 s of clear detail
    to resume."""

    ENTER, LEAVE = 1.0, 0.5

    def __init__(self):
        self.covered = False
        self._since = None

    @staticmethod
    def measure(frame):
        g = cv2.cvtColor(cv2.resize(frame, (320, 180), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
        return float(g.mean()), float(g.std()), float((cv2.Canny(g, 40, 120) > 0).mean() * 100)

    def update(self, frame, now):
        mean, std, edges = self.measure(frame)
        if self.covered:
            change = mean > 18 and (std > 12 or edges > 1.0)
        else:
            change = mean < 12 or (std < 8 and edges < 0.3)  # flat, or almost black
        if not change:
            self._since = None
        elif self._since is None:
            self._since = now
        elif now - self._since >= (self.LEAVE if self.covered else self.ENTER):
            self.covered, self._since = not self.covered, None
        return self.covered


def gesture_name(g):
    return gesture(g).name if g else ""


def binding_name(b):
    return b.get("name") or gesture_name(b["gesture"])


class Engine(QThread):
    frame_ready = Signal(QImage)
    status = Signal(dict)
    message = Signal(str, bool)            # text, is_error
    failed = Signal(str)                   # the loop stopped
    effects_toggled = Signal(bool)
    camera_opened = Signal(int, int, int)  # width, height, fps
    cover_changed = Signal(bool)
    virtual_status = Signal(str)
    framing_changed = Signal(float, float, float)  # zoom, center x, center y (sensor)

    def __init__(self, cfg, input_, executor):
        super().__init__()
        self._cfg = copy.deepcopy(cfg)
        self._lock = threading.Lock()
        self.input = input_
        self.executor = executor
        self.camera = None        # camera.Camera, owned by the window
        self.face_store = None    # faces.FaceStore, set by the window
        self.running = True
        self.paused = False
        self.mouse = False
        self.effects_on = cfg["view"]["effects"]
        self.photo_at = None
        self.flash = 0.0
        self.covered = False
        self.preview_visible = True  # no point drawing the preview while the window is hidden
        self.recognizer = None
        self.recognized = []         # last identified faces
        self.last_raw = None         # last unmirrored frame, for registering samples
        self._cover = CoverDetector()
        self._mouse_pos = None
        self._mouse_down = False
        self._right_click = False
        self._mouse_rest = [0.0, 0.0]
        self._framing = None
        self._last_face = 0.0
        self._framing_time = 0.0
        self._zebra = None
        self._virtual = None
        self._background = None
        self._virtual_retry = 0.0
        self._virtual_text = ""

    # --- called from the UI thread

    def set_config(self, cfg):
        with self._lock:
            if cfg["auto_framing"] and not self._cfg["auto_framing"]:
                self._framing = None  # read the current position again
            self._cfg = copy.deepcopy(cfg)
            self.effects_on = cfg["view"]["effects"]

    def cfg(self):
        with self._lock:
            return self._cfg

    def stop(self):
        self.running = False

    def log(self, text, error=False):
        self.message.emit(text, error)

    def take_photo(self, seconds=0.0):
        self.photo_at = time.monotonic() + seconds

    def fire(self, b):
        action, value = b["action"], b.get("value", "")
        name = binding_name(b)
        if action not in ("pause", "mouse"):  # those report their own message
            self.log(name)
        if action not in INTERNAL_ACTIONS:
            self.executor.run(action, value, name)
        elif action == "photo":
            try:
                self.take_photo(max(0.0, float(value or 3)))
            except ValueError:
                self.take_photo(3)
        elif action == "pause":
            self.paused = not self.paused
            self.log(_("Gestures paused") if self.paused else _("Gestures resumed"))
        elif action == "effects":
            self.effects_on = not self.effects_on
            self.effects_toggled.emit(self.effects_on)
        elif action == "mouse":
            if self.mouse:
                self._stop_mouse()
                self.log(_("Virtual mouse off"))
            elif self.input.connected:
                self.mouse = True
                self.log(_("Virtual mouse on"))
            else:
                self.log(_("Connecting the virtual mouse (accept the desktop permission)…"))

                def connect():
                    if self.input.connect():
                        self.mouse = True
                        self.log(_("Virtual mouse on"))
                self.executor.pool.submit(connect)

    def reload_gallery(self):
        if self.recognizer:
            self.recognizer.reload_gallery()

    # --- loop

    def run(self):
        cap, cap_signature = None, None
        detectors = Detectors(log=self.log)
        triggers = TriggerState()
        effects = Effects()
        t0 = previous = time.monotonic()
        ts_prev, fps, n = -1, 0.0, 0
        try:
            while self.running:
                cfg = self.cfg()
                cam = cfg["camera"]
                signature = (cam["index"], cam["width"], cam["height"], cam["fps"])
                if signature != cap_signature:
                    if cap:
                        cap.release()
                    cap = self._open_camera(cam)
                    cap_signature = signature
                    if cap is None:
                        self.failed.emit(_("Cannot open camera /dev/video{index}. Is another program "
                                           "using it?").format(index=cam["index"]))
                        return

                enabled = cfg["gestures_enabled"]
                wanted = cfg["detectors"]
                det_cfg = dict(cfg, detectors={
                    "hands": enabled and wanted["hands"],
                    "face": (enabled and wanted["face"]) or cfg["auto_framing"],
                    "body": enabled and wanted["body"],
                })
                try:
                    detectors.configure(det_cfg)
                except Exception as e:  # noqa: BLE001 - e.g. a model download failed
                    self.failed.emit(_("Could not load the models: {error}").format(error=e))
                    return

                ok, frame = cap.read()
                if not ok:
                    self.failed.emit(_("The camera stopped sending images (unplugged?)"))
                    return
                now = time.monotonic()
                fps = 0.9 * fps + 0.1 / max(now - previous, 1e-3)
                previous = now

                # Detection works on the mirrored image, which is what the models assume
                # for left and right. Face recognition uses the raw frame, like the
                # samples it was registered with.
                raw = self.last_raw = frame
                frame = cv2.flip(frame, 1)
                clean = frame.copy()
                covered = cfg["pause_when_covered"] and self._cover.update(frame, now)
                if covered != self.covered:
                    self.covered = covered
                    triggers.reset()  # nothing half-held should fire when uncovered
                    if covered:
                        self._stop_mouse()
                    self.cover_changed.emit(covered)
                if covered or not any(det_cfg["detectors"].values()):
                    res = Result()
                else:
                    ts_prev = max(ts_prev + 1, int((now - t0) * 1000))
                    res = detectors.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB), ts_prev, now, det_cfg)
                if not (enabled and wanted["face"]):  # face only ran for auto framing
                    res.signals = {g: s for g, s in res.signals.items() if not g.startswith("face:")}
                    for f in res.faces:
                        f["gestures"] = []

                rec = cfg["recognition"]
                if rec["enabled"] and not covered:
                    # Every frame in "instant" mode, one in three otherwise.
                    if rec["confirmations"] <= 1 or n % 3 == 0:
                        self._recognize(raw, now, rec["threshold"], rec["confirmations"])
                    if self.recognizer:
                        res.signals.update(self.recognizer.signals(self.recognized))
                elif self.recognized:
                    self.recognized = []
                    if self.recognizer:
                        self.recognizer.tracks = []

                progress = {}
                # With "known people only", gestures count only while recognition sees
                # a registered person. If recognition is off they never count.
                authorized = (not cfg["security"]["known_people_only"]
                              or (rec["enabled"] and "recognized:known" in res.signals))
                gestures_ok = enabled and authorized
                # Face recognition bindings work even when gesture control is off.
                bindings = (cfg["bindings"] if gestures_ok
                            else [b for b in cfg["bindings"] if b["gesture"].startswith(RECOGNIZED_PREFIX)])
                if bindings and not covered:
                    to_fire, progress = triggers.evaluate(bindings, res, now, self.paused, self.mouse)
                    for b in to_fire:
                        self.fire(b)
                    if self.mouse and gestures_ok:
                        self._move_mouse(res, cfg)
                if self.mouse and not (gestures_ok and not covered):
                    self._stop_mouse()

                if cfg["auto_framing"] and not covered:
                    self._follow_face(res, frame.shape, now)

                # The virtual camera gets the clean image (no overlay) with the chosen
                # background, and the preview shows the same thing.
                vc = cfg["virtual_camera"]
                if vc["enabled"]:
                    out = self._apply_background(raw, vc)
                    self._send_virtual(cv2.flip(out, 1) if vc["mirror"] else out, now)
                    if out is not raw:
                        frame = cv2.flip(out, 1)
                        clean = frame.copy()
                else:
                    self._close_virtual("")

                mirror = cfg["view"]["mirror"]
                if self.photo_at is not None and now >= self.photo_at:
                    self.photo_at = None
                    self._save_photo(clean if mirror else cv2.flip(clean, 1), cfg)

                if self.preview_visible:
                    self._draw_cv(frame, clean, res, cfg, effects, now)
                    if not mirror:
                        frame = cv2.flip(frame, 1)
                    img = self._to_qimage(frame)
                    self._draw_qt(img, clean, res, cfg, progress, now)
                    self.frame_ready.emit(img)

                n += 1
                if n % 3 == 0 or res.events:
                    self.status.emit({
                        "fps": fps, "signals": {g: sorted(s) for g, s in res.signals.items()},
                        "events": [g for g, _side in res.events], "progress": progress,
                        "paused": self.paused, "mouse": self.mouse, "hands": len(res.hands),
                        "faces": len(res.faces), "bodies": len(res.bodies), "covered": covered,
                        "recognized": [f["name"] for f in self.recognized if f["name"]],
                        "unauthorized": enabled and not authorized,
                        "recognition_off": cfg["security"]["known_people_only"] and not rec["enabled"],
                    })
        finally:
            self._stop_mouse()
            self._close_virtual("")
            if self._background:
                self._background.close()
                self._background = None
            detectors.close()
            if cap:
                cap.release()

    # --- virtual camera

    def _report_virtual(self, text):
        if text != self._virtual_text:
            self._virtual_text = text
            self.virtual_status.emit(text)

    def _apply_background(self, raw, vc):
        if vc["background"] == "none":
            return raw
        if self._background is None:
            try:
                self._background = virtual_camera.Background(model_path("segmentation", self.log))
            except Exception as e:  # noqa: BLE001
                self.log(_("Could not load the background effect: {error}").format(error=e), True)
                return raw
        return self._background.apply(raw, vc)

    def _send_virtual(self, img, now):
        height = int(self.cfg()["virtual_camera"]["resolution"])
        if self._virtual and self._virtual.requested[1] != height:
            self._close_virtual("")  # resolution changed: reopen
        if self._virtual is None:
            if now < self._virtual_retry:
                return
            self._virtual_retry = now + 3.0  # do not scan devices on every frame
            if not virtual_camera.module_loaded():
                self._report_virtual("not_installed")
                return
            device = virtual_camera.find_device()
            if device is None:
                self._report_virtual("no_device")
                return
            index, self._virtual_label = device
            try:
                self._virtual = virtual_camera.VirtualOutput(index, height * 16 // 9, height)
            except OSError as e:
                self._report_virtual(f"error:{e.strerror}")
                return
        try:
            self._virtual.write(img, now)
            self._report_virtual(f"streaming:{self._virtual_label}|{self._virtual.path}")
        except OSError as e:
            self._close_virtual(f"error:{e.strerror}")

    def _close_virtual(self, state):
        if self._virtual:
            self._virtual.close()
            self._virtual = None
        self._virtual_retry = 0.0
        self._report_virtual(state)

    # --- recognition and capture

    def _recognize(self, raw, now, threshold, confirmations):
        if self.recognizer is None:
            if self.face_store is None:
                return
            try:
                from .recognition import Recognizer
                self.recognizer = Recognizer(self.face_store, self.log)
            except Exception as e:  # noqa: BLE001 - e.g. offline, model not downloaded yet
                self.log(_("Could not start face recognition: {error}").format(error=e), True)
                self.face_store = None
                return
        self.recognized = self.recognizer.process(raw, now, threshold, confirmations)

    def _open_camera(self, cam):
        cap = cv2.VideoCapture(cam["index"], cv2.CAP_V4L2)
        if not cap.isOpened():
            return None
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, cam["width"])
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cam["height"])
        cap.set(cv2.CAP_PROP_FPS, cam["fps"])
        ok, frame = cap.read()
        if not ok:
            cap.release()
            return None
        h, w = frame.shape[:2]
        self.camera_opened.emit(w, h, int(round(cap.get(cv2.CAP_PROP_FPS))))
        return cap

    def _save_photo(self, frame, cfg):
        folder = photo_folder(cfg)
        try:
            folder.mkdir(parents=True, exist_ok=True, mode=0o700)
            path = folder / f"photo_{datetime.now():%Y%m%d_%H%M%S}.jpg"
            if not cv2.imwrite(str(path), frame, [cv2.IMWRITE_JPEG_QUALITY, 95]):
                raise OSError(_("the file could not be written"))
            os.chmod(path, 0o600)  # photos of people: readable by the user only
            self.flash = time.monotonic() + 0.25
            self.log(_("Photo saved to {path}").format(path=path))
        except OSError as e:
            self.log(_("Could not save the photo: {error}").format(error=e), True)

    # --- auto framing: follows the face with the camera's digital zoom/pan/tilt

    def _follow_face(self, res, shape, now):
        cam = self.camera
        if not has_framing(cam) or now - self._framing_time < 0.1:
            return
        self._framing_time = now
        try:
            if self._framing is None:
                self._framing = read_framing(cam)
            z, cx, cy = self._framing
            h, w = shape[:2]
            if res.faces:
                pts = res.faces[0]["points"]
                xs, ys = [p[0] for p in pts], [p[1] for p in pts]
                fx = 1 - (min(xs) + max(xs)) / 2 / w   # the processed image is mirrored
                fy = (min(ys) + max(ys)) / 2 / h
                fh = (max(ys) - min(ys)) / h
                # From image coordinates (already cropped) to sensor coordinates
                sx, sy, sh = cx + (fx - 0.5) / z, cy + (fy - 0.5) / z, fh / z
                zmax = min(MAX_AUTO_ZOOM, cam.controls["zoom_absolute"].maximum / 100)
                zt = max(1.0, min(zmax, TARGET_FACE_HEIGHT / max(sh, 1e-3)))
                cxt, cyt = sx, sy + 0.07 / zt  # face slightly above center
                self._last_face = now
            elif now - self._last_face > 3.0:
                zt, cxt, cyt = 1.0, 0.5, 0.5  # nobody: back to the wide shot
            else:
                return
            m = 0.5 / zt
            cxt, cyt = min(1 - m, max(m, cxt)), min(1 - m, max(m, cyt))
            if abs(zt - z) < 0.04 and abs(cxt - cx) < 0.015 and abs(cyt - cy) < 0.015:
                return  # dead zone, keeps it from shaking
            k = 0.18
            nz, ncx, ncy = z + k * (zt - z), cx + k * (cxt - cx), cy + k * (cyt - cy)
            m = 0.5 / nz
            ncx, ncy = min(1 - m, max(m, ncx)), min(1 - m, max(m, ncy))
            nz = write_framing(cam, nz, ncx, ncy)
            self._framing = (nz, ncx, ncy)
            self.framing_changed.emit(nz, ncx, ncy)
        except (OSError, KeyError) as e:
            self.log(_("Auto framing stopped: {error}").format(error=e), True)
            self._framing = None
            self._framing_time = now + 5

    # --- virtual mouse

    def _move_mouse(self, res, cfg):
        mc = cfg["mouse"]
        hands = [h for h in res.hands if mc["hand"] == "any" or h["side"] == mc["hand"]]
        if not hands:
            self._release_buttons()
            self._mouse_pos = None
            return
        p = hands[0]["points"]
        size = dist(p[0], p[9]) or 1.0
        # The knuckles rather than the fingertip, so the pointer does not jump on a pinch.
        pos = ((p[5][0] + p[9][0]) / 2, (p[5][1] + p[9][1]) / 2)
        try:
            if self._mouse_pos is None:
                self._mouse_pos = pos
            else:
                a = min(0.9, max(0.0, mc["smoothing"]))
                nx = self._mouse_pos[0] + (1 - a) * (pos[0] - self._mouse_pos[0])
                ny = self._mouse_pos[1] + (1 - a) * (pos[1] - self._mouse_pos[1])
                k = mc["speed"] * 2.0
                self._mouse_rest[0] += (nx - self._mouse_pos[0]) * k
                self._mouse_rest[1] += (ny - self._mouse_pos[1]) * k
                self._mouse_pos = (nx, ny)
                dx, dy = int(self._mouse_rest[0]), int(self._mouse_rest[1])
                if dx or dy:
                    self._mouse_rest = [self._mouse_rest[0] - dx, self._mouse_rest[1] - dy]
                    self.input.move(dx, dy)
            index_gap = dist(p[4], p[8]) / size
            if not self._mouse_down and index_gap < 0.25:
                self.input.button(BTN_LEFT, True)
                self._mouse_down = True
            elif self._mouse_down and index_gap > 0.35:
                self.input.button(BTN_LEFT, False)
                self._mouse_down = False
            middle_gap = dist(p[4], p[12]) / size
            if not self._right_click and middle_gap < 0.25 and not self._mouse_down:
                self.input.button(BTN_RIGHT, True)
                self.input.button(BTN_RIGHT, False)
                self._right_click = True
            elif self._right_click and middle_gap > 0.35:
                self._right_click = False
        except Exception as e:  # noqa: BLE001
            self.log(_("Virtual mouse turned off: {error}").format(error=e), True)
            self.mouse = False

    def _release_buttons(self):
        if self._mouse_down:
            try:
                self.input.button(BTN_LEFT, False)
            except Exception:  # noqa: BLE001
                pass
            self._mouse_down = False

    def _stop_mouse(self):
        self._release_buttons()
        self.mouse = False
        self._mouse_pos = None

    # --- drawing

    def _draw_cv(self, frame, clean, res, cfg, effects, now):
        view = cfg["view"]
        h, w = frame.shape[:2]
        if view["zebra"]:
            # Diagonal stripes over blown-out areas, like on video cameras.
            if self._zebra is None or self._zebra.shape != (h, w):
                yy, xx = np.mgrid[0:h, 0:w]
                self._zebra = ((xx + yy) // 8) % 2 == 0
            gray = cv2.cvtColor(clean, cv2.COLOR_BGR2GRAY)
            frame[(gray > 240) & self._zebra] = (0, 0, 0)
        if view["overlay"] and cfg["gestures_enabled"]:
            for body in res.bodies:
                pts, vis = body["points"], body["visible"]
                for a, b in POSE_CONNECTIONS:
                    if a > 10 and b > 10 and vis[a] and vis[b]:
                        cv2.line(frame, _px(pts[a]), _px(pts[b]), (80, 220, 80), 3, cv2.LINE_AA)
            for hand in res.hands:
                color = SIDE_COLORS[hand["side"]]
                for a, b in HAND_CONNECTIONS:
                    cv2.line(frame, _px(hand["points"][a]), _px(hand["points"][b]), color, 2, cv2.LINE_AA)
                for q in hand["points"]:
                    cv2.circle(frame, _px(q), 3, (255, 255, 255), -1, cv2.LINE_AA)

        if self.effects_on:
            layer = np.zeros_like(frame)
            for hand in res.hands:
                if hand["gesture"]:
                    pts = [_px(q) for q in hand["points"]]
                    effects.apply(hand["gesture"], pts, max(20.0, dist(pts[0], pts[9])), layer, now)
            effects.update(layer)
            frame[:] = effects.compose(frame, layer)

        if view["grid"]:
            for k in (1, 2):
                cv2.line(frame, (w * k // 3, 0), (w * k // 3, h), (255, 255, 255), 1, cv2.LINE_AA)
                cv2.line(frame, (0, h * k // 3), (w, h * k // 3), (255, 255, 255), 1, cv2.LINE_AA)

        if self.flash > now:
            frame[:] = cv2.addWeighted(frame, 0.3, np.full_like(frame, 255), 0.7, 0)

    @staticmethod
    def _to_qimage(frame):
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w = rgb.shape[:2]
        return QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy()

    def _draw_qt(self, img, clean, res, cfg, progress, now):
        w, h = img.width(), img.height()
        scale = h / 720
        mirror = cfg["view"]["mirror"]

        def X(x):  # noqa: N802 - processed (mirrored) coordinates to displayed ones
            return x if mirror else w - x

        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        font = QFont("Inter")
        font.setPixelSize(int(20 * scale))
        font.setWeight(QFont.Weight.DemiBold)
        p.setFont(font)

        def pill(x, y, text, bg=None, fg=None):
            bg, fg = bg or QColor(18, 19, 22, 200), fg or QColor(236, 236, 239)
            r = p.fontMetrics().boundingRect(text)
            box = QRectF(x - r.width() / 2 - 12 * scale, y - r.height() / 2 - 7 * scale,
                         r.width() + 24 * scale, r.height() + 14 * scale)
            box.moveLeft(max(4, min(w - box.width() - 4, box.left())))
            box.moveTop(max(4, min(h - box.height() - 4, box.top())))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(bg)
            p.drawRoundedRect(box, 8 * scale, 8 * scale)
            p.setPen(fg)
            p.drawText(box, Qt.AlignmentFlag.AlignCenter, text)

        if cfg["view"]["overlay"] and cfg["gestures_enabled"]:
            for hand in res.hands:
                if hand["gesture"]:
                    x, y = hand["points"][0]
                    pill(X(x), y + 50 * scale, gesture_name(hand["gesture"]))
            for face in res.faces:
                if face["gestures"]:
                    x, y = face["points"][10]
                    pill(X(x), y - 30 * scale, " · ".join(gesture_name(g) for g in face["gestures"]))
            for body in res.bodies:
                if body["gestures"]:
                    x, y = body["points"][0]
                    pill(X(x), y - 90 * scale, " · ".join(gesture_name(g) for g in body["gestures"]))

        if self.recognized and cfg["view"]["overlay"]:
            self._draw_faces(p, pill, w, mirror)

        # A held gesture charging up: progress ring at the bottom center.
        if progress:
            bid, value = max(progress.items(), key=lambda kv: kv[1])
            b = next((b for b in cfg["bindings"] if b["id"] == bid), None)
            if b:
                r = 26 * scale
                cx, cy = w / 2, h - 70 * scale
                p.setPen(QPen(QColor(255, 255, 255, 50), 4 * scale))
                p.drawEllipse(QPointF(cx, cy), r, r)
                pen = QPen(QColor(76, 141, 255), 4 * scale)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                p.setPen(pen)
                p.drawArc(QRectF(cx - r, cy - r, 2 * r, 2 * r), 90 * 16, int(-value * 360 * 16))
                pill(cx, cy - r - 26 * scale, binding_name(b))

        if self.paused and cfg["gestures_enabled"]:
            pill(w / 2, 36 * scale, _("Gestures paused"), QColor(229, 165, 10, 230), QColor(20, 20, 20))

        if cfg["view"]["histogram"]:
            self._histogram(p, clean, w, h, scale)

        if self.covered:
            p.fillRect(QRectF(0, 0, w, h), QColor(0, 0, 0, 140))
            pill(w / 2, h / 2, _("Camera covered · detection paused"))

        if self.photo_at is not None:
            font.setPixelSize(int(160 * scale))
            font.setWeight(QFont.Weight.Bold)
            p.setFont(font)
            p.setPen(QColor("white"))
            p.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter,
                       str(max(1, math.ceil(self.photo_at - now))))
        p.end()

    def _draw_faces(self, p, pill, w, mirror):
        from .recognition import UNKNOWN
        for f in self.recognized:
            x, y, bw, bh = f["box"]
            if mirror:  # boxes come from the unmirrored frame
                x = w - x - bw
            if f["person"] is None:
                color, text = QColor(255, 255, 255, 110), ""
            elif f["person"] == UNKNOWN:
                color, text = QColor(229, 165, 10), _("Unknown")
            else:
                g = self.face_store.group(f["group"]) if self.face_store and f["group"] else None
                color, text = QColor(g["color"] if g else "#ececef"), f["name"]
            p.setPen(QPen(color, max(2.0, bw / 90)))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(QRectF(x, y, bw, bh), bw * 0.08, bw * 0.08)
            if text:
                bg = QColor(color)
                bg.setAlpha(225)
                pill(x + bw / 2, y - 22, text, bg, QColor(18, 19, 22))

    @staticmethod
    def _histogram(p, clean, w, h, scale):
        gray = cv2.cvtColor(cv2.resize(clean, (160, 90)), cv2.COLOR_BGR2GRAY)
        hist = cv2.calcHist([gray], [0], None, [64], [0, 256]).ravel()
        hist = hist / (hist.max() or 1)
        width, height = 220 * scale, 80 * scale
        x0, y0 = w - width - 16 * scale, h - height - 16 * scale
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(15, 15, 18, 170))
        p.drawRoundedRect(QRectF(x0 - 6, y0 - 6, width + 12, height + 12), 8, 8)
        path = QPainterPath(QPointF(x0, y0 + height))
        for i, v in enumerate(hist):
            path.lineTo(x0 + width * i / (len(hist) - 1), y0 + height * (1 - v))
        path.lineTo(x0 + width, y0 + height)
        path.closeSubpath()
        p.setBrush(QColor(255, 255, 255, 170))
        p.drawPath(path)


def _px(q):
    return int(q[0]), int(q[1])
