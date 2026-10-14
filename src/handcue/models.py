"""Downloads the ML models on first use and checks them against a known SHA-256.

The models are parsed by native code (MediaPipe, OpenCV), so a tampered file is a
real attack surface. URLs point at fixed versions, never "latest", and cached
files are re-checked every time the app starts.
"""
import hashlib
import os
import tempfile
import urllib.request

from .config import CACHE_DIR
from .i18n import _

MODELS_DIR = CACHE_DIR / "models"
_LEGACY_DIR = CACHE_DIR / "modelos"  # before 0.1.0

_MP = "https://storage.googleapis.com/mediapipe-models/"
_ZOO = "https://github.com/opencv/opencv_zoo/raw/"
MODELS = {
    "gesture_recognizer.task": (
        _MP + "gesture_recognizer/gesture_recognizer/float16/1/gesture_recognizer.task",
        "97952348cf6a6a4915c2ea1496b4b37ebabc50cbbf80571435643c455f2b0482"),
    "face_landmarker.task": (
        _MP + "face_landmarker/face_landmarker/float16/1/face_landmarker.task",
        "64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff"),
    "pose_landmarker_lite.task": (
        _MP + "pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task",
        "59929e1d1ee95287735ddd833b19cf4ac46d29bc7afddbbf6753c459690d574a"),
    "selfie_segmenter.tflite": (
        _MP + "image_segmenter/selfie_segmenter/float16/1/selfie_segmenter.tflite",
        "191ac9529ae506ee0beefa6b2c945a172dab9d07d1e802a290a4e4038226658b"),
    "hand_landmarker.task": (
        _MP + "hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task",
        "fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1"),
    "face_detection_yunet_2023mar.onnx": (
        _ZOO + "f12e12798e8314f7c074a6656816c048dcc95b7a/models/face_detection_yunet/"
               "face_detection_yunet_2023mar.onnx",
        "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"),
    "face_recognition_sface_2021dec.onnx": (
        _ZOO + "ba91a3b91d00d76e86540d4013f944bd6b514e39/models/face_recognition_sface/"
               "face_recognition_sface_2021dec.onnx",
        "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79"),
}
MAX_SIZE = 100 * 1024 * 1024  # the largest model is about 40 MB
_verified = set()


class ModelError(Exception):
    pass


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _download(url, dest):
    with urllib.request.urlopen(url, timeout=60) as r:  # noqa: S310 - fixed https URLs from MODELS
        total = 0
        with open(dest, "wb") as f:
            while block := r.read(1 << 20):
                total += len(block)
                if total > MAX_SIZE:
                    raise ModelError(f"download too large: {url}")
                f.write(block)


def path(name, log=print):
    """Local path of a model, downloading and verifying it if needed."""
    url, expected = MODELS[name]
    dest = MODELS_DIR / name
    if dest in _verified:
        return str(dest)
    if dest.exists() and _sha256(dest) != expected:
        log(_("Model {name} does not match the original, downloading it again").format(name=name))
        dest.unlink()
    if not dest.exists():
        CACHE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
        MODELS_DIR.mkdir(exist_ok=True, mode=0o700)
        legacy = _LEGACY_DIR / name
        if legacy.exists() and _sha256(legacy) == expected:
            os.replace(legacy, dest)
        else:
            log(_("Downloading model {name}…").format(name=name))
            fd, tmp = tempfile.mkstemp(prefix=".download-", dir=MODELS_DIR)
            os.close(fd)
            try:
                _download(url, tmp)
                if _sha256(tmp) != expected:
                    raise ModelError(f"{name}: download does not match the expected SHA-256")
                os.replace(tmp, dest)
            finally:
                if os.path.exists(tmp):
                    os.unlink(tmp)
    _verified.add(dest)
    return str(dest)
