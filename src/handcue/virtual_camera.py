"""Virtual camera: writes the processed image to a v4l2loopback device so Meet,
Zoom, Discord or OBS can use it like any other webcam.

v4l2loopback is a kernel module; resources/install-virtual-camera.sh sets it up
once (it asks for the administrator password).
"""
import fcntl
import os
import platform
import shlex
import struct
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import BaseOptions, vision

from .camera import VIDIOC_QUERYCAP, _iowr

# Card labels we create (the second one by versions before 0.1.0, as control-gestos).
DEVICE_LABELS = ("HandCue", "Control por gestos")
INSTALL_SCRIPT = Path(__file__).resolve().parent / "resources" / "install-virtual-camera.sh"
INSTALL_COMMAND = f"bash {shlex.quote(str(INSTALL_SCRIPT))}"

VIDIOC_G_FMT = _iowr(4, 208)
VIDIOC_S_FMT = _iowr(5, 208)  # struct v4l2_format: type, padding, 200-byte union
BUF_TYPE_VIDEO_OUTPUT = 2
YUYV = struct.unpack("<I", b"YUYV")[0]
FIELD_NONE = 1
COLORSPACE_SRGB = 8


def module_loaded():
    return Path("/sys/module/v4l2loopback").exists()


def module_installed():
    if module_loaded():
        return True
    root = Path("/lib/modules") / platform.release()
    return root.exists() and any(root.rglob("v4l2loopback.ko*"))


def find_device():
    """(index, card label) of the v4l2loopback device to use, preferring ours."""
    candidates = []
    for d in Path("/sys/class/video4linux").glob("video*"):
        try:
            fd = os.open(f"/dev/{d.name}", os.O_RDWR | os.O_NONBLOCK)
        except OSError:
            continue
        try:
            buf = bytearray(104)
            fcntl.ioctl(fd, VIDIOC_QUERYCAP, buf, True)
            driver = buf[:16].split(b"\0")[0].decode(errors="replace")
            label = buf[16:48].split(b"\0")[0].decode(errors="replace")
            if "loopback" in driver:
                candidates.append((label not in DEVICE_LABELS, int(d.name[5:]), label))
        except OSError:
            pass
        finally:
            os.close(fd)
    if not candidates:
        return None
    _theirs, index, label = min(candidates)
    return index, label


class VirtualOutput:
    """Writes BGR frames to the device as YUYV, which every consumer accepts.

    The size is fixed when the device is opened. If an app is already reading
    from it the format cannot change, so the existing one is adopted and frames
    are scaled to fit."""

    def __init__(self, index, width, height, fps=30):
        self.path = f"/dev/video{index}"
        self.fd = os.open(self.path, os.O_RDWR)
        self.requested = (width, height)
        self.interval = 1.0 / fps
        self.last = 0.0
        try:
            self.size = self._set_format(width, height)
        except OSError:
            self.size = self._current_format() or (width, height)

    def _set_format(self, w, h):
        buf = bytearray(208)
        # v4l2_format.type, then v4l2_pix_format from byte 8
        struct.pack_into("<I", buf, 0, BUF_TYPE_VIDEO_OUTPUT)
        struct.pack_into("<IIIIIIII", buf, 8, w, h, YUYV, FIELD_NONE, w * 2, w * h * 2, COLORSPACE_SRGB, 0)
        fcntl.ioctl(self.fd, VIDIOC_S_FMT, buf, True)
        return struct.unpack_from("<II", buf, 8)

    def _current_format(self):
        buf = bytearray(208)
        struct.pack_into("<I", buf, 0, BUF_TYPE_VIDEO_OUTPUT)
        try:
            fcntl.ioctl(self.fd, VIDIOC_G_FMT, buf, True)
        except OSError:
            return None
        w, h = struct.unpack_from("<II", buf, 8)
        return (w, h) if w and h else None

    def write(self, bgr, now):
        """Writes at most `fps` frames per second, the rate the device advertises."""
        if now - self.last < self.interval * 0.9:
            return
        self.last = now
        w, h = self.size
        if bgr.shape[1] != w or bgr.shape[0] != h:
            bgr = cv2.resize(bgr, (w, h), interpolation=cv2.INTER_AREA)
        os.write(self.fd, cv2.cvtColor(bgr, cv2.COLOR_BGR2YUV_YUYV).tobytes())

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None


class Background:
    """Separates the person from the background (MediaPipe selfie segmenter) and
    replaces it."""

    SIZE = 256  # the model's input size

    def __init__(self, model_path):
        self.segmenter = vision.ImageSegmenter.create_from_options(vision.ImageSegmenterOptions(
            base_options=BaseOptions(model_asset_path=model_path), running_mode=vision.RunningMode.VIDEO,
            output_confidence_masks=True, output_category_mask=False))
        self.mask = None
        self.ts = 0
        self._image = (None, None, None)  # (path, size, scaled image)

    def close(self):
        self.segmenter.close()

    def _mask(self, bgr):
        h, w = bgr.shape[:2]
        small = cv2.cvtColor(cv2.resize(bgr, (self.SIZE, self.SIZE), interpolation=cv2.INTER_AREA),
                             cv2.COLOR_BGR2RGB)
        self.ts += 33
        r = self.segmenter.segment_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=small), self.ts)
        m = r.confidence_masks[0].numpy_view().reshape(self.SIZE, self.SIZE)
        # Smoothing over time stops the edge from flickering; blurring gives it a soft edge.
        m = cv2.GaussianBlur(m, (7, 7), 0)
        self.mask = m if self.mask is None or self.mask.shape != m.shape else 0.55 * self.mask + 0.45 * m
        return cv2.resize(self.mask, (w, h), interpolation=cv2.INTER_LINEAR)

    def _background_image(self, path, w, h):
        if self._image[0] == path and self._image[1] == (w, h):
            return self._image[2]
        img = cv2.imread(path) if path else None
        if img is not None:
            # Fill without distortion, like CSS object-fit: cover.
            k = max(w / img.shape[1], h / img.shape[0])
            img = cv2.resize(img, (int(img.shape[1] * k + 1), int(img.shape[0] * k + 1)))
            y0, x0 = (img.shape[0] - h) // 2, (img.shape[1] - w) // 2
            img = img[y0:y0 + h, x0:x0 + w]
        self._image = (path, (w, h), img)
        return img

    def apply(self, bgr, cfg):
        """cfg: {"background": none|blur|color|image, "blur", "color", "image"}"""
        mode = cfg["background"]
        if mode == "none":
            self.mask = None
            return bgr
        h, w = bgr.shape[:2]
        m = self._mask(bgr)
        if mode == "blur":
            # Blurring at quarter resolution is much faster and looks the same.
            k = max(1, int(cfg["blur"]))
            small = cv2.resize(bgr, (w // 4, h // 4), interpolation=cv2.INTER_AREA)
            back = cv2.resize(cv2.GaussianBlur(small, (0, 0), k / 4), (w, h), interpolation=cv2.INTER_LINEAR)
        elif mode == "image" and self._background_image(cfg["image"], w, h) is not None:
            back = self._background_image(cfg["image"], w, h)
        else:
            c = cfg["color"].lstrip("#")
            back = np.empty_like(bgr)
            back[:] = (int(c[4:6], 16), int(c[2:4], 16), int(c[0:2], 16))
        return cv2.blendLinear(bgr, back, m, 1.0 - m)
