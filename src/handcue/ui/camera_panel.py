"""Camera tab: exposure, color, framing, focus and format controls over V4L2."""
from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import QComboBox, QInputDialog, QMenu, QToolButton, QVBoxLayout, QWidget

from ..camera import FLAG_READ_ONLY, TYPE_BOOL, TYPE_INT, TYPE_MENU, builtin_profiles, read_framing, write_framing
from ..i18n import _
from .widgets import (
    FramingMap, Inspector, Section, Segmented, SettingRow, SliderRow, SwitchRow, TemperatureBar, button,
    icon_button, label, row,
)

CUSTOM = _("Custom")
KNOWN = {
    "auto_exposure", "exposure_time_absolute", "gain", "brightness", "exposure_dynamic_framerate",
    "backlight_compensation", "white_balance_automatic", "white_balance_temperature", "saturation",
    "contrast", "sharpness", "zoom_absolute", "pan_absolute", "tilt_absolute", "focus_absolute",
    "focus_automatic_continuous", "power_line_frequency", "privacy", "hue", "gamma",
}
AUTO_MODES = ("auto_exposure", "white_balance_automatic", "focus_automatic_continuous")
MENU_NAMES = {"Disabled": _("Off")}
TEMPERATURES = [(3200, _("Incandescent bulb")), (4000, _("Fluorescent")), (5600, _("Daylight")),
                (6500, _("Cloudy"))]


def _shutter(v):
    s = v / 10000  # exposure_time_absolute is in units of 100 µs
    return f"1/{round(1 / s)} s" if s < 0.4 else f"{s:.1f} s"


def _menu_button(icon, tooltip, entries):
    b = icon_button(icon, tooltip)
    m = QMenu(b)
    for entry in entries:
        if entry is None:
            m.addSeparator()
        else:
            m.addAction(*entry)
    b.setMenu(m)
    b.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
    return b


class CameraPanel(QWidget):
    controls_changed = Signal(dict)
    format_changed = Signal(int, int, int)
    auto_framing_changed = Signal(bool)
    profile_saved = Signal(str, dict)
    profile_deleted = Signal(str)
    message = Signal(str, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.inspector = Inspector()
        lay.addWidget(self.inspector)
        self.cam = None
        self.cfg = None
        self.w = {}
        self.save_timer = QTimer(self, singleShot=True, interval=400, timeout=self.emit_controls)

    def build(self, cam, cfg):
        self.inspector.clear()
        self.cam, self.cfg, self.w = cam, cfg, {}
        if cam is None:
            s = Section(_("Camera"))
            s.add(label(_("No camera connected."), level=2, wrap=True))
            self.inspector.add(s)
            self.inspector.finish()
            return
        c = cam.controls
        self._profiles()
        if {"auto_exposure", "exposure_time_absolute", "gain", "brightness"} & c.keys():
            self._exposure()
        if {"white_balance_temperature", "saturation", "hue"} & c.keys():
            self._color()
        if {"contrast", "sharpness", "gamma"} & c.keys():
            self._image()
        if "zoom_absolute" in c:
            self._framing()
        if {"focus_absolute", "focus_automatic_continuous"} & c.keys():
            self._focus()
        if "power_line_frequency" in c:
            self._flicker()
        self._format()
        others = [n for n in c if n not in KNOWN]
        if others or "privacy" in c:
            self._advanced(others)
        note = Section(_("About these settings"), expanded=False)
        note.add(label(_("They are stored in the camera itself, so they also apply in OBS, Meet or Discord. "
                         "The camera forgets them when unplugged; this app restores them when it starts."),
                       level=2, wrap=True))
        self.inspector.add(note)
        self.inspector.finish()
        self.refresh()

    def _profiles(self):
        more = _menu_button("dots-horizontal", _("Profile options"), [
            (_("Save as new profile…"), self._save_profile),
            (_("Delete this profile"), self._delete_profile),
            None,
            (_("Restore factory defaults"), lambda: self._apply_profile(_("Factory defaults"))),
        ])
        s = Section(_("Profile"), extra=more)
        self.profile_combo = QComboBox()
        self.profile_combo.activated.connect(lambda _i: self._apply_profile(self.profile_combo.currentText()))
        s.add(self.profile_combo)
        self.inspector.add(s)
        self._fill_profiles()

    def _fill_profiles(self, current=CUSTOM):
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        self.profile_combo.addItem(CUSTOM)
        self.profile_combo.insertSeparator(1)
        self.profile_combo.addItems(list(builtin_profiles(self.cam)))
        if self.cfg["camera_profiles"]:
            self.profile_combo.insertSeparator(self.profile_combo.count())
            self.profile_combo.addItems(sorted(self.cfg["camera_profiles"]))
        self.profile_combo.setCurrentText(current)
        self.profile_combo.blockSignals(False)

    def _exposure(self):
        c = self.cam.controls
        s = Section(_("Exposure"))
        if "auto_exposure" in c:
            self.w["auto_exposure"] = s.add(SwitchRow(_("Automatic")))
            self.w["auto_exposure"].toggled.connect(self._set_auto_exposure)
        self._slider(s, "exposure_time_absolute", _("Shutter"), _shutter)
        self._slider(s, "gain", _("ISO (gain)"))
        self._slider(s, "brightness", _("Compensation"), lambda v: f"{v:+d}")
        if "exposure_dynamic_framerate" in c:
            w = s.add(SwitchRow(_("Keep frame rate"), help_text=_("Holds the FPS even in low light")))
            w.toggled.connect(lambda on: self._write("exposure_dynamic_framerate", 0 if on else 1))
            self.w["exposure_dynamic_framerate"] = w
        self._switch(s, "backlight_compensation", _("Backlight compensation"),
                     _("Brightens your face when there is a window behind you"))
        self.inspector.add(s)

    def _color(self):
        c = self.cam.controls
        s = Section(_("Color"))
        self._switch(s, "white_balance_automatic", _("Automatic white balance"))
        if "white_balance_temperature" in c:
            slider = self._slider(s, "white_balance_temperature", _("Temperature"), lambda v: f"{v} K")
            slider.lay.addWidget(TemperatureBar())
            presets = _menu_button("white-balance-sunny", _("Presets"),
                                   [(f"{name}  ·  {k} K", lambda k=k: self._temperature(k))
                                    for k, name in TEMPERATURES])
            presets.setFixedSize(24, 24)
            presets.setStyleSheet("QToolButton { min-width: 24px; min-height: 24px; }")
            slider.lay.itemAt(0).layout().addWidget(presets)
        self._slider(s, "saturation", _("Saturation"), self._percent("saturation"))
        self._slider(s, "hue", _("Hue"))
        self.inspector.add(s)

    def _image(self):
        s = Section(_("Image"))
        self._slider(s, "contrast", _("Contrast"), self._percent("contrast"))
        self._slider(s, "sharpness", _("Sharpness"), self._percent("sharpness"))
        self._slider(s, "gamma", _("Gamma"))
        self.inspector.add(s)

    def _framing(self):
        c = self.cam.controls
        s = Section(_("Zoom and framing"))
        self.w["auto_framing"] = s.add(SwitchRow(
            _("Face tracking"), self.cfg["auto_framing"], _("Keeps your face framed using digital zoom")))
        self.w["auto_framing"].toggled.connect(self._set_auto_framing)
        z = c["zoom_absolute"]
        self.zoom = SliderRow(_("Zoom"), z.minimum, z.maximum, z.default, z.default, lambda v: f"{v / 100:.1f}×")
        self.zoom.changed.connect(self._zoom_changed)
        s.add(self.zoom)
        self.framing_map = FramingMap()
        self.framing_map.moved.connect(self._map_moved)
        if {"pan_absolute", "tilt_absolute"} & c.keys():
            s.add(self.framing_map)
        center = button(_("Center"), icon="image-filter-center-focus")
        center.clicked.connect(lambda: self._move_framing(None, 0.5, 0.5))
        reset = button(_("Reset"), icon="restore")
        reset.clicked.connect(lambda: self._move_framing(1.0, 0.5, 0.5))
        s.add(row(center, reset, None))
        self.inspector.add(s)

    def _focus(self):
        s = Section(_("Focus"))
        self._switch(s, "focus_automatic_continuous", _("Autofocus"))
        self._slider(s, "focus_absolute", _("Distance"))
        self.inspector.add(s)

    def _flicker(self):
        c = self.cam.controls["power_line_frequency"]
        s = Section(_("Anti-flicker"))
        seg = Segmented([(k, MENU_NAMES.get(v, v)) for k, v in c.menu.items()])
        seg.changed.connect(lambda v: self._write("power_line_frequency", v))
        self.w["power_line_frequency"] = seg
        s.add(seg)
        s.add(label(_("Match your mains frequency: 50 Hz in Europe, 60 Hz in the Americas."), level=2, wrap=True))
        self.inspector.add(s)

    def _format(self):
        s = Section(_("Format"), expanded=False)
        formats = self.cam.formats() or [(1280, 720, [30])]
        cam = self.cfg["camera"]
        self.resolution_combo = QComboBox()
        for w, h, rates in formats:
            self.resolution_combo.addItem(f"{h}p", (w, h, rates))
        i = next((i for i, (w, h, _r) in enumerate(formats) if (w, h) == (cam["width"], cam["height"])), 0)
        self.resolution_combo.setCurrentIndex(i)
        self.resolution_combo.setFixedWidth(112)
        self.resolution_combo.currentIndexChanged.connect(self._resolution_changed)
        s.add(SettingRow(_("Resolution"), self.resolution_combo))
        self.fps_combo = QComboBox()
        self.fps_combo.setFixedWidth(112)
        self._fill_fps(formats[i][2], cam["fps"])
        self.fps_combo.currentIndexChanged.connect(lambda _i: self._emit_format())
        s.add(SettingRow(_("Frame rate"), self.fps_combo))
        s.add(label(_("Higher resolution and frame rate use more CPU for gesture recognition."),
                    level=2, wrap=True))
        self.inspector.add(s)

    def _advanced(self, names):
        s = Section(_("Advanced"), expanded=False)
        self._switch(s, "privacy", _("Privacy mode"), _("Cuts the camera image"))
        for n in names:
            c = self.cam.controls[n]
            if c.type == TYPE_BOOL:
                self._switch(s, n, c.title)
            elif c.type == TYPE_INT:
                self._slider(s, n, c.title)
            elif c.type == TYPE_MENU:
                combo = QComboBox()
                for k, v in c.menu.items():
                    combo.addItem(v, k)
                combo.currentIndexChanged.connect(lambda _i, n=n, cb=combo: self._write(n, cb.currentData()))
                self.w[n] = combo
                s.add(SettingRow(c.title, combo))
        self.inspector.add(s)

    def _percent(self, name):
        c = self.cam.controls.get(name)
        if not c or c.maximum == c.minimum:
            return str
        return lambda v: f"{round((v - c.minimum) * 100 / (c.maximum - c.minimum))} %"

    def _slider(self, section, name, title, fmt=str):
        c = self.cam.controls.get(name)
        if not c:
            return None
        w = SliderRow(title, c.minimum, c.maximum, c.default, c.default, fmt, c.step)
        w.changed.connect(lambda v: self._write(name, v))
        self.w[name] = section.add(w)
        return w

    def _switch(self, section, name, title, help_text=""):
        if name not in self.cam.controls:
            return None
        w = SwitchRow(title, help_text=help_text)
        w.toggled.connect(lambda on: self._write(name, 1 if on else 0))
        self.w[name] = section.add(w)
        return w

    def _fill_fps(self, rates, current):
        self.fps_combo.blockSignals(True)
        self.fps_combo.clear()
        for f in rates or [30]:
            self.fps_combo.addItem(f"{f} fps", f)
        i = self.fps_combo.findData(current)
        self.fps_combo.setCurrentIndex(i if i >= 0 else self.fps_combo.count() - 1)
        self.fps_combo.blockSignals(False)

    def refresh(self):
        if not self.cam:
            return
        self.cam.refresh_flags()
        values = self.cam.get_all()
        for n, w in self.w.items():
            v = values.get(n)
            if n == "auto_framing" or v is None:
                continue
            if n == "auto_exposure":
                w.setChecked(v != 1)
            elif n == "exposure_dynamic_framerate":
                w.setChecked(not v)
            elif isinstance(w, SwitchRow):
                w.setChecked(bool(v))
            elif isinstance(w, SliderRow):
                w.setValue(v)
            elif isinstance(w, Segmented):
                w.set(v)
            elif isinstance(w, QComboBox):
                w.blockSignals(True)
                w.setCurrentIndex(max(0, w.findData(v)))
                w.blockSignals(False)
        auto_exposure = values.get("auto_exposure", 1) != 1
        for n, c in self.cam.controls.items():
            if n in self.w and isinstance(self.w[n], SliderRow) and n != "zoom_absolute":
                self.w[n].setEnabled(not c.inactive and not (auto_exposure and n in ("exposure_time_absolute", "gain")))
        self._refresh_framing()
        self._sync_profile(values)

    def _matching_profile(self, values):
        """Profile that matches what the camera has now. Inactive controls (such as the
        temperature while auto white balance is on) make no difference and are ignored."""
        candidates = list(self.cfg["camera_profiles"].items()) + list(builtin_profiles(self.cam).items())
        for name, profile in candidates:
            relevant = {k: v for k, v in profile.items()
                        if k in self.cam.controls and k != "privacy" and not self.cam.controls[k].inactive}
            if relevant and all(values.get(k) == v for k, v in relevant.items()):
                return name
        return CUSTOM

    def _sync_profile(self, values=None):
        name = self._matching_profile(values if values is not None else self.cam.get_all())
        if self.profile_combo.currentText() != name:
            self.profile_combo.blockSignals(True)
            self.profile_combo.setCurrentText(name)
            self.profile_combo.blockSignals(False)

    def _refresh_framing(self):
        if "zoom_absolute" not in self.cam.controls:
            return
        try:
            z, cx, cy = read_framing(self.cam)
        except OSError:
            return
        self.show_framing(z, cx, cy)
        auto = self.cfg["auto_framing"]
        self.zoom.setEnabled(not auto)
        self.framing_map.setEnabled(not auto)

    def show_framing(self, z, cx, cy):
        if not hasattr(self, "zoom"):
            return
        self.zoom.setValue(round(z * 100))
        self.framing_map.set(z, 1 - cx if self.cfg["view"]["mirror"] else cx, cy)

    def _write(self, name, value):
        try:
            self.cam.set(name, value)
        except OSError as e:
            self.message.emit(_("The camera rejected the setting ({error})").format(error=e.strerror), True)
        if name in AUTO_MODES:
            self.refresh()
        else:
            self._sync_profile()
        self.save_timer.start()

    def emit_controls(self):
        if self.cam:
            read_only = {n for n, c in self.cam.controls.items() if c.flags & FLAG_READ_ONLY}
            self.controls_changed.emit({n: v for n, v in self.cam.get_all().items() if n not in read_only})

    def _set_auto_exposure(self, on):
        c = self.cam.controls["auto_exposure"]
        self._write("auto_exposure", next((k for k in c.menu if k != 1), 3) if on else 1)

    def _temperature(self, kelvin):
        if "white_balance_automatic" in self.cam.controls:
            self._write("white_balance_automatic", 0)
        self._write("white_balance_temperature", kelvin)
        self.refresh()

    def _zoom_changed(self, v):
        _z, cx, cy = read_framing(self.cam)
        self._move_framing(v / 100, cx, cy)

    def _map_moved(self, x, y):
        self._move_framing(None, 1 - x if self.cfg["view"]["mirror"] else x, y)

    def _move_framing(self, z, cx, cy):
        if self.cfg["auto_framing"]:
            return
        try:
            if z is None:
                z = read_framing(self.cam)[0]
            write_framing(self.cam, z, cx, cy)
        except OSError as e:
            self.message.emit(_("Could not move the framing ({error})").format(error=e.strerror), True)
        self._refresh_framing()
        self._sync_profile()
        self.save_timer.start()

    def _set_auto_framing(self, on):
        self.cfg["auto_framing"] = on
        self.auto_framing_changed.emit(on)
        self._refresh_framing()

    def _resolution_changed(self, i):
        rates = self.resolution_combo.itemData(i)[2]
        self._fill_fps(rates, self.fps_combo.currentData())
        self._emit_format()

    def _emit_format(self):
        w, h, _rates = self.resolution_combo.currentData()
        self.format_changed.emit(w, h, self.fps_combo.currentData() or 30)

    def _apply_profile(self, name):
        profiles = {**builtin_profiles(self.cam), **self.cfg["camera_profiles"]}
        if name not in profiles:
            return
        errors = self.cam.apply(profiles[name])
        self.refresh()
        self._fill_profiles(name)
        self.emit_controls()
        text = (_("Profile “{name}” applied with warnings") if errors
                else _("Profile “{name}” applied"))
        self.message.emit(text.format(name=name), False)

    def _save_profile(self):
        current = self.profile_combo.currentText()
        suggested = current if current in self.cfg["camera_profiles"] else ""
        name, ok = QInputDialog.getText(self, _("Save profile"), _("Profile name"), text=suggested)
        name = name.strip()
        if not ok or not name:
            return
        if name in builtin_profiles(self.cam) or name == CUSTOM:
            self.message.emit(_("That name is reserved"), True)
            return
        read_only = {n for n, c in self.cam.controls.items() if c.flags & FLAG_READ_ONLY}
        values = {n: v for n, v in self.cam.get_all().items() if n not in read_only and n != "privacy"}
        self.profile_saved.emit(name, values)
        self._fill_profiles(name)

    def _delete_profile(self):
        name = self.profile_combo.currentText()
        if name in self.cfg["camera_profiles"]:
            self.profile_deleted.emit(name)
            self._fill_profiles(CUSTOM)
        else:
            self.message.emit(_("Only profiles you saved can be deleted"), True)
