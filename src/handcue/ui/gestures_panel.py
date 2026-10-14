"""Gestures tab: the list of gesture -> action bindings and the binding editor."""
import configparser
import copy
from pathlib import Path

from PySide6.QtCore import QLocale, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDoubleSpinBox, QFrame, QHBoxLayout, QLineEdit, QListView, QListWidget,
    QListWidgetItem, QMenu, QToolButton, QVBoxLayout, QWidget,
)

from .. import catalog as C
from ..actions import normalize_url
from ..desktop_input import parse_shortcut
from ..i18n import _, ngettext
from . import icons
from . import theme as T
from .widgets import (
    Inspector, Section, Segmented, SettingRow, Switch, SwitchRow, ask, button, icon_button, label, row,
    separator, show_error,
)

CELL = QSize(100, 76)
MEDIA = {"play_pause": _("Play / pause"), "next": _("Next track"), "previous": _("Previous track"),
         "volume_up": _("Volume up"), "volume_down": _("Volume down"), "mute": _("Mute")}
VALUE_LABELS = {"media": _("Action"), "app": _("Application"), "url": _("Web address"), "type": _("Text"),
                "shortcut": _("Key combination"), "command": _("Command"), "sound": _("Sound"),
                "notification": _("Message"), "photo": _("Countdown (seconds)")}
PLACEHOLDERS = {"type": _("Text to type"), "command": _("For example: notify-send Hello"),
                "url": "https://", "notification": _("Notification text"), "app": _("Search for an app"),
                "shortcut": _("For example: ctrl+c")}
SIDE_SUFFIX = {"left": _("left hand"), "right": _("right hand"), "both": _("both hands")}

_apps = None


def installed_apps():
    """[(display name, .desktop id)] of the installed applications."""
    global _apps
    if _apps is None:
        locale = QLocale.system().name()  # e.g. es_ES
        keys = [f"Name[{locale}]", f"Name[{locale.split('_')[0]}]", "Name"]
        found = {}
        for base in (Path("/usr/share/applications"), Path.home() / ".local/share/applications",
                     Path("/var/lib/flatpak/exports/share/applications"),
                     Path.home() / ".local/share/flatpak/exports/share/applications"):
            for f in base.glob("*.desktop") if base.exists() else []:
                cp = configparser.RawConfigParser(strict=False, interpolation=None)
                cp.optionxform = str  # keep the case of Name[xx]
                try:
                    cp.read(f, encoding="utf-8")
                    entry = cp["Desktop Entry"]
                except (configparser.Error, KeyError, UnicodeDecodeError):
                    continue
                if entry.get("NoDisplay", "").lower() == "true" or entry.get("Type", "Application") != "Application":
                    continue
                name = next((entry[k] for k in keys if entry.get(k)), None)
                if name:
                    found[f.stem] = name
        _apps = sorted(((n, i) for i, n in found.items()), key=lambda t: t[0].lower())
    return _apps


def describe_action(b):
    v = b.get("value", "")
    kind = b["action"]
    if kind == "media":
        return MEDIA.get(v, v)
    if kind == "app":
        return _("Open {app}").format(app=next((n for n, i in installed_apps() if i == v), v))
    if kind == "photo":
        return _("Photo with a {seconds} s countdown").format(seconds=v) if v not in ("", "0") else _("Take photo")
    if kind == "sound":
        return _("Sound “{name}”").format(name=v)
    if kind == "url":
        return v.replace("https://", "").replace("www.", "").rstrip("/")
    if kind in ("type", "notification"):
        return f"“{v}”" if v else C.ACTIONS[kind].name
    if kind == "shortcut":
        return v.upper().replace("+", " + ")
    return C.ACTIONS[kind].name


class GestureTile(QWidget):
    """Rounded square with the gesture icon. Lights up while the gesture is seen."""

    def __init__(self, gesture, parent=None):
        super().__init__(parent)
        self.setFixedSize(36, 36)
        self.gesture = gesture
        self.active = False
        self.progress = 0.0

    def set_state(self, active, progress):
        if (active, round(progress, 2)) != (self.active, round(self.progress, 2)):
            self.active, self.progress = active, progress
            self.update()

    def paintEvent(self, _event):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(T.ACCENT if self.active else T.RAISED))
        p.drawRoundedRect(0, 0, 36, 36, 8, 8)
        if 0 < self.progress < 1:
            # Held gesture: the tile fills up from the bottom.
            p.setBrush(QColor(76, 141, 255, 120))
            h = 36 * self.progress
            p.drawRoundedRect(0, int(36 - h), 36, int(h) + 1, 8, 8)
        color = "white" if self.active else T.TEXT_2
        p.drawPixmap(8, 8, icons.gesture_icon(self.gesture, color).pixmap(QSize(20, 20), self.devicePixelRatioF()))


class BindingRow(QFrame):
    clicked = Signal()
    toggled = Signal(bool)

    def __init__(self, binding, parent=None):
        super().__init__(parent)
        self.binding = binding
        self.setObjectName("bindingRow")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(f"QFrame#bindingRow {{ border-radius: {T.RADIUS + 2}px; }}"
                           f"QFrame#bindingRow:hover {{ background: {T.HOVER}; }}")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(T.S2, T.S2, T.S2, T.S2)
        lay.setSpacing(T.S3)
        self.tile = GestureTile(binding["gesture"])
        lay.addWidget(self.tile)
        col = QVBoxLayout()
        col.setSpacing(1)
        g = C.gesture(binding["gesture"])
        self.title = label(binding.get("name") or g.name)
        self.title.setStyleSheet("font-weight: 500;")
        col.addWidget(self.title)
        detail = g.name
        if binding["gesture"].startswith("hand:") and binding["side"] in SIDE_SUFFIX:
            detail += ", " + SIDE_SUFFIX[binding["side"]]
        if not g.is_event and binding["hold"] == 0:
            detail += ", " + _("instant")
        self.subtitle = label(f"{detail}  →  {describe_action(binding)}", level=2)
        self.subtitle.setMinimumWidth(10)
        col.addWidget(self.subtitle)
        lay.addLayout(col, 1)
        self.switch = Switch(binding["enabled"])
        self.switch.toggled.connect(self._toggle)
        lay.addWidget(self.switch)
        self._dim()

    def _toggle(self, on):
        self.binding["enabled"] = on
        self._dim()
        self.toggled.emit(on)

    def _dim(self):
        self.title.setEnabled(self.binding["enabled"])
        self.subtitle.setEnabled(self.binding["enabled"])

    def resizeEvent(self, e):  # noqa: N802
        # Elide the subtitle instead of widening the panel.
        fm = self.subtitle.fontMetrics()
        full = self.subtitle.property("full") or self.subtitle.text()
        self.subtitle.setProperty("full", full)
        self.subtitle.setText(fm.elidedText(full, Qt.TextElideMode.ElideRight, max(40, self.subtitle.width())))
        super().resizeEvent(e)

    def mouseReleaseEvent(self, e):  # noqa: N802
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()


class GesturesPanel(QWidget):
    config_changed = Signal()
    test = Signal(dict)

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.rows = []
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        ins = Inspector()
        lay.addWidget(ins)

        s = Section(_("Recognition"))
        self.master = s.add(SwitchRow(_("Gesture control"), cfg["gestures_enabled"], " "))
        self.master.toggled.connect(self._set_enabled)
        self.status_label = self.master.help
        s.add(label(_("Detect"), level=2))
        sources = QHBoxLayout()
        sources.setSpacing(T.S2)
        self.sources = {}
        for key, text, icon, tip in (
                ("hands", _("Hands"), "hand-back-right-outline", _("Recognize hand gestures")),
                ("face", _("Face"), "face-recognition", _("Recognize facial expressions")),
                ("body", _("Body"), "human", _("Recognize body poses"))):
            b = icon_button(icon, tip, checkable=True, checked=cfg["detectors"][key], text=text)
            b.setStyleSheet(f"QToolButton {{ border: 1px solid {T.BORDER_STRONG}; }}"
                            f"QToolButton:checked {{ border-color: {T.ACCENT}; }}")
            b.toggled.connect(lambda on, k=key: self._set_detector(k, on))
            sources.addWidget(b)
            self.sources[key] = b
        sources.addStretch()
        s.add(sources)
        ins.add(s)

        add = icon_button("plus", _("Add gesture"))
        add.clicked.connect(lambda: self.add_binding())
        more = icon_button("dots-horizontal", _("More options"))
        menu = QMenu(more)
        menu.addAction(_("Enable all"), lambda: self._set_all(True))
        menu.addAction(_("Disable all"), lambda: self._set_all(False))
        menu.addSeparator()
        menu.addAction(_("Restore examples"), self._restore)
        more.setMenu(menu)
        more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        extra = QWidget()
        extra.setLayout(row(add, more, spacing=0))
        self.list_section = Section(_("Gestures"), extra=extra)
        self.list_section.body_layout.setSpacing(0)
        self.list = QVBoxLayout()
        self.list.setSpacing(0)
        self.list_section.add(self.list)
        ins.add(self.list_section)
        ins.finish()
        self.refresh()
        self.show_status()

    def refresh(self):
        for r in self.rows:
            r.deleteLater()
        self.rows = []
        for b in self.cfg["bindings"]:
            r = BindingRow(b)
            r.clicked.connect(lambda b=b: self.edit_binding(b))
            r.toggled.connect(lambda _on: self.config_changed.emit())
            self.list.addWidget(r)
            self.rows.append(r)
        if not self.cfg["bindings"]:
            empty = label(_("No gestures yet. Press + to create the first one."), level=2, wrap=True)
            self.list.addWidget(empty)
            self.rows.append(empty)

    def _set_enabled(self, on):
        self.cfg["gestures_enabled"] = on
        self.show_status()
        self.config_changed.emit()

    def _set_detector(self, key, on):
        self.cfg["detectors"][key] = on
        self.config_changed.emit()

    def _set_all(self, on):
        for b in self.cfg["bindings"]:
            b["enabled"] = on
        self.refresh()
        self.config_changed.emit()

    def _restore(self):
        if ask(self, _("Restore examples"), _("Your gestures will be replaced by the examples.")):
            self.cfg["bindings"] = C.default_bindings()
            self.refresh()
            self.config_changed.emit()

    def show_status(self, text=""):
        if not self.cfg["gestures_enabled"]:
            self.status_label.setText(_("Off"))
        else:
            self.status_label.setText(text or _("Waiting for gestures"))

    def add_binding(self, gesture="hand:thumb_up", action="media", value="play_pause", **extra):
        d = BindingDialog(C.new_binding(gesture, action, value, **extra), new=True, parent=self)
        d.test.connect(self.test)
        if d.exec():
            self.cfg["bindings"].append(d.result_binding())
            self.refresh()
            self.config_changed.emit()

    def edit_binding(self, b):
        d = BindingDialog(b, new=False, parent=self)
        d.test.connect(self.test)
        accepted = d.exec()
        if d.delete:
            self.cfg["bindings"].remove(b)
        elif accepted:
            self.cfg["bindings"][self.cfg["bindings"].index(b)] = d.result_binding()
        else:
            return
        self.refresh()
        self.config_changed.emit()

    def update_status(self, e):
        signals, events, progress = e.get("signals", {}), e.get("events", []), e.get("progress", {})
        for r in self.rows:
            if not isinstance(r, BindingRow):
                continue
            b = r.binding
            seen = b["enabled"] and (b["gesture"] in signals or b["gesture"] in events)
            r.tile.set_state(seen and b["id"] not in progress, progress.get(b["id"], 0.0))
        if "fps" in e and self.cfg["gestures_enabled"]:
            counts = (
                (e.get("hands", 0), lambda n: ngettext("{n} hand", "{n} hands", n)),
                (e.get("faces", 0), lambda n: ngettext("{n} face", "{n} faces", n)),
                (e.get("bodies", 0), lambda n: ngettext("{n} person", "{n} people", n)),
            )
            parts = [text(n).format(n=n) for n, text in counts if n]
            text = ", ".join(parts) if parts else _("Waiting for gestures")
            if e.get("covered"):
                text = _("Camera covered: detection paused")
            elif e.get("recognition_off"):
                text = _("Blocked: turn on face recognition (Faces tab)")
            elif e.get("unauthorized"):
                text = _("Waiting for a registered person")
            elif e.get("paused"):
                text = _("Paused")
            elif e.get("mouse"):
                text = _("Virtual mouse active")
            self.show_status(text)


class OptionGrid(QListWidget):
    """Grid of options with icons (gestures or actions)."""

    def __init__(self, rows=2, parent=None):
        super().__init__(parent)
        self.setViewMode(QListView.ViewMode.IconMode)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setMovement(QListView.Movement.Static)
        self.setIconSize(QSize(22, 22))
        self.setGridSize(QSize(CELL.width() + 6, CELL.height() + 6))
        self.setSpacing(0)
        self.setWordWrap(True)
        self.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.setUniformItemSizes(True)
        self.setFixedHeight((CELL.height() + 6) * rows + 4)
        self.setStyleSheet("QListWidget::item { margin: 3px; padding: 10px 4px 4px 4px; font-size: 12px; }")

    def set_items(self, items, current=None):
        """items: [(key, QIcon, text, tooltip)]"""
        self.clear()
        for key, icon, text, tip in items:
            it = QListWidgetItem(icon, text)
            it.setData(Qt.ItemDataRole.UserRole, key)
            it.setToolTip(tip)
            it.setSizeHint(CELL)
            it.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
            self.addItem(it)
            if key == current:
                self.setCurrentItem(it)

    def key(self):
        it = self.currentItem()
        return it.data(Qt.ItemDataRole.UserRole) if it else None


def _grid_style():
    return dict(color_selected=T.ACCENT, color_active=T.TEXT)


class BindingDialog(QDialog):
    test = Signal(dict)

    def __init__(self, binding, new, parent=None):
        super().__init__(parent)
        title = _("New gesture") if new else _("Edit gesture")
        self.setWindowTitle(title)
        self.setMinimumWidth(600)
        self.binding = copy.deepcopy(binding)
        self.delete = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(T.S6, T.S6, T.S6, T.S4)
        lay.setSpacing(T.S4)
        lay.addWidget(label(title, role="title"))

        header = QHBoxLayout()
        header.addWidget(label(_("WHEN YOU DO"), role="heading"))
        header.addStretch()
        category = C.gesture(binding["gesture"]).category
        self.categories = Segmented(list(C.CATEGORIES.items()), category)
        self.categories.setFixedWidth(320)
        self.categories.changed.connect(self._fill_gestures)
        header.addWidget(self.categories)
        lay.addLayout(header)
        self.gesture_grid = OptionGrid(rows=2)
        self.gesture_grid.currentItemChanged.connect(lambda *_args: self._gesture_chosen())
        lay.addWidget(self.gesture_grid)
        self.gesture_help = label("", level=2)
        lay.addWidget(self.gesture_help)
        self.hold = QDoubleSpinBox(decimals=1, minimum=0, maximum=10, singleStep=0.1, suffix=" s")
        self.hold.setSpecialValueText(_("Instant"))  # shown when the value is 0
        self.hold.setValue(binding["hold"])
        self.hold.setFixedWidth(120)
        self.hold_row = SettingRow(_("Detection time"), self.hold,
                                   _("How long the gesture must be seen before acting. Prevents accidental "
                                     "triggers."))
        lay.addWidget(self.hold_row)

        lay.addWidget(separator())
        lay.addWidget(label(_("THEN"), role="heading"))
        self.action_grid = OptionGrid(rows=3)
        self.action_grid.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.action_grid.set_items(
            [(k, icons.action_icon(k, T.TEXT_2, **_grid_style()), a.name, a.help) for k, a in C.ACTIONS.items()],
            binding["action"])
        self.action_grid.currentItemChanged.connect(lambda *_args: self._action_chosen(True))
        lay.addWidget(self.action_grid)

        self.value_block = QWidget()
        vb = QVBoxLayout(self.value_block)
        vb.setContentsMargins(0, 0, 0, 0)
        vb.setSpacing(T.S2)
        self.value_label = label("")
        self.value_label.setStyleSheet("font-weight: 500;")
        self.value = QComboBox()
        self.value.setEditable(True)
        self.value.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.help = label("", level=2, wrap=True)
        vb.addWidget(self.value_label)
        vb.addWidget(self.value)
        vb.addWidget(self.help)
        lay.addWidget(self.value_block)

        self.advanced = Section(_("Advanced options"), expanded=False)
        self.advanced.layout().setContentsMargins(0, T.S2, 0, 0)
        self.name = QLineEdit(binding.get("name", ""))
        self.name.setPlaceholderText(_("Optional"))
        self.name.setFixedWidth(240)
        self.advanced.add(SettingRow(_("Name"), self.name))
        self.side = QComboBox()
        for k, v in C.SIDES.items():
            self.side.addItem(v, k)
        self.side.setCurrentIndex(self.side.findData(binding["side"]))
        self.side.setFixedWidth(240)
        self.advanced.add(SettingRow(_("Hand"), self.side))
        self.cooldown = QDoubleSpinBox(decimals=1, minimum=0, maximum=600, singleStep=0.5, suffix=" s")
        self.cooldown.setValue(binding["cooldown"])
        self.cooldown.setFixedWidth(96)
        self.advanced.add(SettingRow(_("Time between uses"), self.cooldown))
        self.repeat = self.advanced.add(SwitchRow(_("Repeat while held"), binding["repeat"],
                                                  _("Useful for volume or scrolling")))
        lay.addWidget(self.advanced)
        lay.addStretch()

        lay.addWidget(separator())
        buttons = QHBoxLayout()
        if not new:
            b = button(_("Delete"), "danger", "delete-outline")
            b.clicked.connect(self._delete)
            buttons.addWidget(b)
        buttons.addStretch()
        b = button(_("Try it"), icon="play-outline")
        b.clicked.connect(lambda: self.test.emit(self.result_binding()))
        buttons.addWidget(b)
        b = button(_("Cancel"), "ghost")
        b.clicked.connect(self.reject)
        buttons.addWidget(b)
        b = button(_("Save"), "primary")
        b.setDefault(True)
        b.clicked.connect(self._accept)
        buttons.addWidget(b)
        lay.addLayout(buttons)

        self._fill_gestures(category, binding["gesture"])
        self._action_chosen(False)
        self._set_value(binding.get("value", ""))

    def _fill_gestures(self, category, current=None):
        current = current or self.gesture_grid.key()
        self.gesture_grid.set_items(
            [(gid, icons.gesture_icon(gid, T.TEXT_2, **_grid_style()), g.name, g.description)
             for gid, g in C.GESTURES.items() if g.category == category], current)
        if self.gesture_grid.currentItem() is None and self.gesture_grid.count():
            self.gesture_grid.setCurrentRow(0)

    def _gesture_chosen(self):
        gid = self.gesture_grid.key()
        if not gid:
            return
        g = C.gesture(gid)
        self.gesture_help.setText(g.description + (". " + _("Fires instantly.") if g.is_event else "."))
        is_hand = gid.startswith("hand:")
        self.side.setEnabled(is_hand)
        if not is_hand:
            self.side.setCurrentIndex(self.side.findData("any"))
        self.hold_row.setVisible(not g.is_event)  # events (swipes...) are already instant
        self.repeat.setEnabled(not g.is_event)

    def _action_chosen(self, clear):
        kind = self.action_grid.key() or self.binding["action"]
        action = C.ACTIONS[kind]
        self.value.clear()
        if kind == "app":
            for name, app_id in installed_apps():
                self.value.addItem(name, app_id)
        elif kind == "media":
            for k, v in MEDIA.items():
                self.value.addItem(v, k)
        elif action.suggestions:
            self.value.addItems(action.suggestions)
        self.value.setEditable(kind not in ("media", "sound"))
        if clear:
            self.value.setCurrentIndex(0 if self.value.count() else -1)
            if self.value.isEditable() and not self.value.count():
                self.value.setEditText("")
        self.value_block.setVisible(kind not in C.NO_VALUE_ACTIONS)
        self.value_label.setText(VALUE_LABELS.get(kind, _("Value")))
        if self.value.isEditable():
            self.value.lineEdit().setPlaceholderText(PLACEHOLDERS.get(kind, ""))
        self.help.setText(action.help)

    def _set_value(self, v):
        i = self.value.findData(v)
        if i < 0:
            i = self.value.findText(v)
        if i >= 0:
            self.value.setCurrentIndex(i)
        elif self.value.isEditable():
            self.value.setEditText(v)

    def result_binding(self):
        b = self.binding
        gid = self.gesture_grid.key() or b["gesture"]
        kind = self.action_grid.key() or b["action"]
        value = self.value.currentText().strip()
        i = self.value.findText(value)
        if i >= 0 and self.value.itemData(i):  # display name -> identifier
            value = self.value.itemData(i)
        b.update(gesture=gid, action=kind, value="" if kind in C.NO_VALUE_ACTIONS else value,
                 name=self.name.text().strip(),
                 side=self.side.currentData() if gid.startswith("hand:") else "any",
                 hold=self.hold.value(), cooldown=self.cooldown.value(),
                 repeat=self.repeat.isChecked() and not C.gesture(gid).is_event)
        return b

    def _accept(self):
        b = self.result_binding()
        if b["action"] not in C.NO_VALUE_ACTIONS and b["action"] != "notification" and not b["value"]:
            show_error(self, _("Missing value"), _("Please fill in: {field}.").format(
                field=VALUE_LABELS.get(b["action"], _("Value")).lower()))
            return
        try:
            if b["action"] == "shortcut":
                parse_shortcut(b["value"])
            elif b["action"] == "url":
                normalize_url(b["value"])
        except ValueError as e:
            show_error(self, _("Invalid value"), str(e))
            return
        self.accept()

    def _delete(self):
        if ask(self, _("Delete gesture"), _("This cannot be undone.")):
            self.delete = True
            self.reject()
