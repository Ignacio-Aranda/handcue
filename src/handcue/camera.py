"""Camera controls over V4L2, using ioctl directly.

Settings are written to the camera itself, so they also apply in OBS, Meet,
Discord and any other app that opens it.
"""
import fcntl
import os
import re
import struct
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from .i18n import _


def _iowr(nr, size):
    return (3 << 30) | (size << 16) | (ord("V") << 8) | nr


def _ior(nr, size):
    return (2 << 30) | (size << 16) | (ord("V") << 8) | nr


VIDIOC_QUERYCAP = _ior(0, 104)
VIDIOC_ENUM_FMT = _iowr(2, 64)
VIDIOC_G_CTRL = _iowr(27, 8)
VIDIOC_S_CTRL = _iowr(28, 8)
VIDIOC_QUERYCTRL = _iowr(36, 68)
VIDIOC_QUERYMENU = _iowr(37, 44)
VIDIOC_ENUM_FRAMESIZES = _iowr(74, 44)
VIDIOC_ENUM_FRAMEINTERVALS = _iowr(75, 52)

QUERYCTRL_FMT = "<II32s4iI2I"
QUERYMENU_FMT = "<II32sI"
FLAG_NEXT_CTRL = 0x80000000
FLAG_DISABLED, FLAG_READ_ONLY, FLAG_INACTIVE = 0x1, 0x4, 0x10
TYPE_INT, TYPE_BOOL, TYPE_MENU, TYPE_CLASS = 1, 2, 3, 6
CAP_VIDEO_CAPTURE = 0x1
MJPG = struct.unpack("<I", b"MJPG")[0]
AUTO_MODES = ("auto_exposure", "white_balance_automatic", "focus_automatic_continuous")
NUDGE = ("focus_absolute",)  # mechanical controls that need a push when reapplied


@dataclass
class Control:
    id: int
    name: str    # v4l2-ctl style: white_balance_temperature
    title: str   # as reported by the driver: "White Balance Temperature"
    type: int
    minimum: int
    maximum: int
    step: int
    default: int
    flags: int
    menu: dict = field(default_factory=dict)

    @property
    def inactive(self):
        return bool(self.flags & FLAG_INACTIVE)


def _v4l2_name(title):
    return re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")


def list_cameras():
    """[(index, name)] of the /dev/videoN nodes that capture video (not metadata)."""
    cameras = []
    for d in sorted(Path("/sys/class/video4linux").glob("video*"), key=lambda p: int(p.name[5:])):
        try:
            fd = os.open(f"/dev/{d.name}", os.O_RDWR | os.O_NONBLOCK)
        except OSError:
            continue
        try:
            buf = bytearray(104)
            fcntl.ioctl(fd, VIDIOC_QUERYCAP, buf, True)
            caps = struct.unpack_from("<I", buf, 88)[0]  # device_caps
            if caps & CAP_VIDEO_CAPTURE:
                cameras.append((int(d.name[5:]), buf[16:48].split(b"\0")[0].decode(errors="replace")))
        except OSError:
            pass
        finally:
            os.close(fd)
    return cameras


class Camera:
    """Access to the controls of /dev/videoN. Thread-safe."""

    def __init__(self, index):
        self.index = index
        self.path = f"/dev/video{index}"
        self.lock = threading.Lock()
        self.fd = os.open(self.path, os.O_RDWR | os.O_NONBLOCK)
        self.controls = {c.name: c for c in self._enumerate()}

    def close(self):
        with self.lock:
            if self.fd is not None:
                os.close(self.fd)
                self.fd = None

    def _enumerate(self):
        found, cid = [], FLAG_NEXT_CTRL
        while True:
            buf = bytearray(struct.pack(QUERYCTRL_FMT, cid, 0, b"", 0, 0, 0, 0, 0, 0, 0))
            try:
                fcntl.ioctl(self.fd, VIDIOC_QUERYCTRL, buf, True)
            except OSError:
                break
            i, kind, title, lo, hi, step, default, flags, _r1, _r2 = struct.unpack(QUERYCTRL_FMT, buf)
            cid = i | FLAG_NEXT_CTRL
            if kind == TYPE_CLASS or flags & FLAG_DISABLED:
                continue
            title = title.split(b"\0")[0].decode(errors="replace")
            c = Control(i, _v4l2_name(title), title, kind, lo, hi, step, default, flags)
            if kind == TYPE_MENU:
                for k in range(lo, hi + 1):
                    m = bytearray(struct.pack(QUERYMENU_FMT, i, k, b"", 0))
                    try:
                        fcntl.ioctl(self.fd, VIDIOC_QUERYMENU, m, True)
                        c.menu[k] = struct.unpack(QUERYMENU_FMT, m)[2].split(b"\0")[0].decode(errors="replace")
                    except OSError:
                        pass
            found.append(c)
        return found

    def has(self, name):
        return name in self.controls

    def refresh_flags(self):
        """Flags such as "inactive" change when an auto mode is switched on or off."""
        with self.lock:
            for c in self.controls.values():
                buf = bytearray(struct.pack(QUERYCTRL_FMT, c.id, 0, b"", 0, 0, 0, 0, 0, 0, 0))
                try:
                    fcntl.ioctl(self.fd, VIDIOC_QUERYCTRL, buf, True)
                    c.flags = struct.unpack(QUERYCTRL_FMT, buf)[7]
                except OSError:
                    pass

    def get(self, name):
        c = self.controls[name]
        with self.lock:
            if self.fd is None:
                raise OSError("camera closed")
            buf = bytearray(struct.pack("<Ii", c.id, 0))
            fcntl.ioctl(self.fd, VIDIOC_G_CTRL, buf, True)
            return struct.unpack("<Ii", buf)[1]

    def set(self, name, value):
        c = self.controls[name]
        value = int(round(value))
        if c.type == TYPE_INT and c.step > 1:
            value = c.minimum + round((value - c.minimum) / c.step) * c.step
        value = max(c.minimum, min(c.maximum, value))
        with self.lock:
            if self.fd is None:
                raise OSError("camera closed")
            fcntl.ioctl(self.fd, VIDIOC_S_CTRL, bytearray(struct.pack("<Ii", c.id, value)), True)
        return value

    def get_all(self):
        values = {}
        for n in self.controls:
            try:
                values[n] = self.get(n)
            except OSError:
                pass
        return values

    def apply(self, settings, nudge=False):
        """Writes {control: value}. Auto modes go first: while they are on, the camera
        ignores the matching manual values.

        nudge=True moves the lens one step before setting it. On the Elgato Facecam
        Neo a focus value written right after streaming starts is silently dropped:
        the driver reports it as set but the image stays blurry."""
        errors = []
        for n in list(AUTO_MODES) + [n for n in settings if n not in AUTO_MODES]:
            if n not in settings or n not in self.controls:
                continue
            if n not in AUTO_MODES and self.controls[n].inactive:
                continue  # e.g. temperature while auto white balance is on: the camera rejects it
            try:
                if nudge and n in NUDGE:
                    c = self.controls[n]
                    other = settings[n] + c.step if settings[n] + c.step <= c.maximum else settings[n] - c.step
                    self.set(n, other)
                    time.sleep(0.12)
                self.set(n, settings[n])
            except OSError as e:
                errors.append(f"{n}: {e.strerror}")
            if n in AUTO_MODES:
                self.refresh_flags()
        return errors

    def factory_defaults(self):
        return {n: c.default for n, c in self.controls.items()
                if not c.flags & FLAG_READ_ONLY and c.name != "privacy"}

    def formats(self):
        """[(width, height, [fps...])] for MJPG, or for the first format if there is no MJPG."""
        pixfmt = None
        for i in range(32):
            buf = bytearray(64)
            struct.pack_into("<II", buf, 0, i, 1)  # index, type=VIDEO_CAPTURE
            try:
                fcntl.ioctl(self.fd, VIDIOC_ENUM_FMT, buf, True)
            except OSError:
                break
            pf = struct.unpack_from("<I", buf, 44)[0]
            if pixfmt is None or pf == MJPG:
                pixfmt = pf
        if pixfmt is None:
            return []
        result = []
        for i in range(64):
            buf = bytearray(44)
            struct.pack_into("<II", buf, 0, i, pixfmt)
            try:
                fcntl.ioctl(self.fd, VIDIOC_ENUM_FRAMESIZES, buf, True)
            except OSError:
                break
            kind, w, h = struct.unpack_from("<III", buf, 8)
            if kind != 1:  # discrete sizes only
                continue
            rates = []
            for j in range(16):
                b2 = bytearray(52)
                struct.pack_into("<IIII", b2, 0, j, pixfmt, w, h)
                try:
                    fcntl.ioctl(self.fd, VIDIOC_ENUM_FRAMEINTERVALS, b2, True)
                except OSError:
                    break
                t, num, den = struct.unpack_from("<III", b2, 16)
                if t == 1 and num:
                    rates.append(round(den / num))
            result.append((w, h, sorted(set(rates), reverse=True)))
        return result


def builtin_profiles(cam):
    """Starting points like the presets in vendor apps. Values are fractions of each
    control's range so they work on any camera."""
    defaults = cam.factory_defaults()

    def rel(name, fraction):
        c = cam.controls.get(name)
        return {name: round(c.minimum + (c.maximum - c.minimum) * fraction)} if c else {}

    def profile(*parts):
        d = dict(defaults)
        for p in parts:
            d.update({k: v for k, v in p.items() if k in cam.controls})
        return d

    return {
        _("Factory defaults"): dict(defaults),
        _("Natural"): profile(rel("contrast", 0.6), rel("saturation", 0.47), rel("sharpness", 0.45)),
        _("Vivid"): profile(rel("contrast", 0.9), rel("saturation", 0.72), rel("sharpness", 0.6)),
        _("Low light"): profile({"auto_exposure": 3, "exposure_dynamic_framerate": 1},
                                rel("brightness", 0.65), rel("sharpness", 0.35), rel("saturation", 0.45)),
        _("Warm"): profile({"white_balance_automatic": 0, "white_balance_temperature": 4300},
                           rel("saturation", 0.55)),
        _("Cool"): profile({"white_balance_automatic": 0, "white_balance_temperature": 6200}),
        _("Backlight"): profile({"backlight_compensation": 1}, rel("brightness", 0.62)),
        _("Black and white"): profile({"saturation": 0}, rel("contrast", 0.9)),
    }


# Digital framing. Measured on the Facecam Neo: at zoom z, pan = +/-max moves the
# crop to the right/left edge of the sensor and tilt = +max to the top edge.
# Positions are the crop center in sensor coordinates (0..1, not mirrored).

def has_framing(cam):
    return cam is not None and cam.has("zoom_absolute")


def read_framing(cam):
    z = max(1.0, cam.get("zoom_absolute") / 100 if cam.has("zoom_absolute") else 1.0)
    margin = (1 - 1 / z) / 2
    cx = cy = 0.5
    if cam.has("pan_absolute"):
        cx = 0.5 + cam.get("pan_absolute") / cam.controls["pan_absolute"].maximum * margin
    if cam.has("tilt_absolute"):
        cy = 0.5 - cam.get("tilt_absolute") / cam.controls["tilt_absolute"].maximum * margin
    return z, cx, cy


def write_framing(cam, z, cx, cy):
    zc = cam.controls["zoom_absolute"]
    z = max(zc.minimum / 100, min(zc.maximum / 100, z))
    cam.set("zoom_absolute", z * 100)
    margin = (1 - 1 / z) / 2
    pan = (cx - 0.5) / margin if margin > 0 else 0.0
    tilt = -(cy - 0.5) / margin if margin > 0 else 0.0
    if cam.has("pan_absolute"):
        cam.set("pan_absolute", max(-1.0, min(1.0, pan)) * cam.controls["pan_absolute"].maximum)
    if cam.has("tilt_absolute"):
        cam.set("tilt_absolute", max(-1.0, min(1.0, tilt)) * cam.controls["tilt_absolute"].maximum)
    return z
