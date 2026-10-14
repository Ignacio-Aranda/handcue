"""Face recognition with OpenCV's pretrained models; nothing is trained locally.

YuNet finds faces and five landmarks, SFace turns each aligned face into a
128-float embedding. Two embeddings of the same person have a high cosine
similarity, so registering someone just means storing a few of their embeddings.
"""
import threading
from collections import Counter, deque

import cv2
import numpy as np

from . import models
from .i18n import _

DETECTOR_MODEL = "face_detection_yunet_2023mar.onnx"
RECOGNIZER_MODEL = "face_recognition_sface_2021dec.onnx"
PROCESS_WIDTH = 640    # detection runs at this width: fast and good enough
MIN_FACE_SIZE = 56     # smaller faces (px at PROCESS_WIDTH) are not identified
VOTES = 7              # recent identifications kept per tracked face
FORGET_AFTER = 1.5     # seconds without seeing a face before dropping its track
UNKNOWN = "?"          # decided: not anyone in the gallery


class Models:
    """YuNet + SFace. Not thread-safe: each thread creates its own."""

    def __init__(self, log=print):
        self.detector = cv2.FaceDetectorYN.create(models.path(DETECTOR_MODEL, log), "", (320, 320), 0.8, 0.3, 20)
        self.sface = cv2.FaceRecognizerSF.create(models.path(RECOGNIZER_MODEL, log), "")
        self._size = None

    def detect(self, img):
        """Faces in a BGR image, as YuNet rows in the image's coordinates."""
        h, w = img.shape[:2]
        k = min(1.0, PROCESS_WIDTH / w)
        small = cv2.resize(img, (int(w * k), int(h * k))) if k < 1 else img
        if self._size != small.shape[:2]:
            self.detector.setInputSize((small.shape[1], small.shape[0]))
            self._size = small.shape[:2]
        faces = self.detector.detect(small)[1]
        if faces is None:
            return [], k
        faces = faces.copy()
        faces[:, :14] /= k
        return list(faces), k

    def embed(self, img, face):
        """(normalized 128-float embedding, aligned 112x112 crop)."""
        crop = self.sface.alignCrop(img, face)
        f = self.sface.feature(crop).ravel().astype(np.float32)
        return f / (np.linalg.norm(f) or 1), crop

    def largest_face(self, img):
        faces = self.detect(img)[0]
        if not faces:
            return None
        return max(faces, key=lambda f: f[2] * f[3])


def _iou(a, b):
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[0] + a[2], b[0] + b[2]), min(a[1] + a[3], b[1] + b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    union = a[2] * a[3] + b[2] * b[3] - inter
    return inter / union if union else 0.0


class Recognizer:
    """Tracks faces across frames and decides who each one is by voting."""

    def __init__(self, store, log=print):
        self.store = store
        self.models = Models(log)
        self.tracks = []  # [{box, votes: deque, seen, similarity}]
        self._gallery = (np.zeros((0, 128), np.float32), [])
        self._lock = threading.Lock()
        self.reload_gallery()

    def reload_gallery(self):
        g = self.store.gallery()
        with self._lock:
            self._gallery = g

    def _identify(self, embedding, threshold):
        with self._lock:
            matrix, ids = self._gallery
        if not ids:
            return UNKNOWN, 0.0
        best = {}
        for pid, s in zip(ids, matrix @ embedding, strict=True):
            best[pid] = max(best.get(pid, -1.0), float(s))
        pid, s = max(best.items(), key=lambda kv: kv[1])
        return (pid if s >= threshold else UNKNOWN), s

    def process(self, img, now, threshold, confirmations=3):
        """img is the unmirrored frame. Returns [{box, person, name, group, similarity}]
        where person is an id, UNKNOWN, or None while still undecided. confirmations is
        how many matching votes are needed to decide (1 = immediately)."""
        faces, k = self.models.detect(img)
        used = set()
        for face in faces:
            box = tuple(float(v) for v in face[:4])
            track = max((t for i, t in enumerate(self.tracks) if i not in used),
                        key=lambda t: _iou(t["box"], box), default=None)
            if track is None or _iou(track["box"], box) < 0.25:
                track = {"votes": deque(maxlen=VOTES), "similarity": 0.0}
                self.tracks.append(track)
            used.add(self.tracks.index(track))
            track["box"], track["seen"] = box, now
            # Only large, confident detections vote: a distant or blurry face must not
            # turn someone known into "unknown".
            if face[2] * k >= MIN_FACE_SIZE and face[14] >= 0.85:
                embedding = self.models.embed(img, face)[0]
                vote, track["similarity"] = self._identify(embedding, threshold)
                track["votes"].append(vote)
        self.tracks = [t for t in self.tracks if now - t["seen"] < FORGET_AFTER]
        return [self._describe(t, confirmations) for t in self.tracks if now - t["seen"] < 0.4]

    def _describe(self, track, confirmations):
        person = None
        if track["votes"]:
            vote, n = Counter(track["votes"]).most_common(1)[0]
            if n >= confirmations:
                person = vote
        p = self.store.person(person) if person not in (None, UNKNOWN) else None
        return {"box": track["box"], "person": person, "similarity": track["similarity"],
                "name": p["name"] if p else (_("Unknown") if person == UNKNOWN else ""),
                "group": p["group"] if p else None}

    @staticmethod
    def signals(faces):
        """Gesture signals for the binding evaluator."""
        s = {}
        for f in faces:
            if f["person"] == UNKNOWN:
                s["recognized:unknown"] = {"*"}
            elif f["person"]:
                s[f"recognized:person:{f['person']}"] = {"*"}
                s["recognized:known"] = {"*"}
                if f["group"]:
                    s[f"recognized:group:{f['group']}"] = {"*"}
        return s
