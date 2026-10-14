"""Faces tab: registered people, groups and face recognition bindings."""
import copy
import time

import cv2
import numpy as np
from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QIcon, QImage, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QFileDialog, QFrame, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
    QListView, QListWidget, QListWidgetItem, QMenu, QToolButton, QVBoxLayout, QWidget,
)

from .. import catalog as C
from .. import faces as F
from ..i18n import _, ngettext
from . import icons
from . import theme as T
from .gestures_panel import BindingRow
from .widgets import (
    Dot, Inspector, Section, Segmented, SettingRow, SliderRow, SwitchRow, ask, button, icon_button, label, row,
    separator, show_error,
)

SAMPLES_PER_CAPTURE = 15
CAPTURE_SECONDS = 8.0
DUPLICATE_SIMILARITY = 0.93  # near-identical samples add nothing
IMAGE_FILTER = "*.jpg *.jpeg *.png *.webp *.bmp"


def pixmap_from_bgr(img, size=None, round_=False):
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    h, w = rgb.shape[:2]
    pm = QPixmap.fromImage(QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy())
    if size:
        pm = pm.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                       Qt.TransformationMode.SmoothTransformation)
    if round_:
        out = QPixmap(pm.size())
        out.fill(Qt.GlobalColor.transparent)
        p = QPainter(out)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addEllipse(0, 0, pm.width(), pm.height())
        p.setClipPath(path)
        p.drawPixmap(0, 0, pm)
        p.end()
        return out
    return pm


def avatar(person, size=36):
    w = QLabel()
    w.setFixedSize(size, size)
    if person["samples"]:
        w.setPixmap(pixmap_from_bgr(F.thumbnail_from_text(person["samples"][0]["thumbnail"]), size, round_=True))
    else:
        w.setPixmap(icons.icon("account-circle-outline", T.TEXT_3).pixmap(size, size))
    return w


class ClickableRow(QFrame):
    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("clickableRow")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(f"QFrame#clickableRow {{ border-radius: {T.RADIUS + 2}px; }}"
                           f"QFrame#clickableRow:hover {{ background: {T.HOVER}; }}")
        self.lay = QHBoxLayout(self)
        self.lay.setContentsMargins(T.S2, T.S2, T.S2, T.S2)
        self.lay.setSpacing(T.S3)

    def mouseReleaseEvent(self, e):  # noqa: N802
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()


def _clear(layout):
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().deleteLater()


class FacesPanel(QWidget):
    config_changed = Signal()
    people_changed = Signal()      # people or groups edited
    add_binding = Signal()
    edit_binding = Signal(dict)
    orphaned_gestures = Signal(list)  # gesture ids that no longer exist

    def __init__(self, cfg, store, get_engine, parent=None):
        super().__init__(parent)
        self.cfg, self.store, self.get_engine = cfg, store, get_engine
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        ins = Inspector()
        lay.addWidget(ins)

        s = Section(_("Face recognition"))
        rec = cfg["recognition"]
        self.master = s.add(SwitchRow(_("Recognize people"), rec["enabled"], " "))
        self.master.toggled.connect(self._set_enabled)
        self.status_label = self.master.help
        strictness = s.add(SliderRow(_("Strictness"), 25, 70, int(rec["threshold"] * 100), 40,
                                     lambda v: f"{v / 100:.2f}"))
        strictness.title.setToolTip(_("Minimum similarity to accept a face. Higher means fewer mix-ups "
                                      "between people, but more “unknown” in poor light."))
        strictness.changed.connect(self._set_threshold)
        confirm = Segmented([(1, _("Instant")), (3, _("Normal")), (5, _("Safe"))], rec["confirmations"])
        confirm.changed.connect(self._set_confirmations)
        s.add(label(_("Confirmation")))
        s.add(confirm)
        s.add(label(_("How many times a face must be seen before deciding who it is. “Instant” "
                      "reacts in a tenth of a second, but a bad frame can fool it."), level=2, wrap=True))
        only_known = s.add(SwitchRow(
            _("Only obey registered people"), cfg["security"]["known_people_only"],
            _("Gestures only work while someone registered is in front of the camera. Without this, "
              "anyone in front of it can trigger your actions (commands, typing...). Needs recognition "
              "turned on.")))
        only_known.toggled.connect(self._set_known_only)
        ins.add(s)

        new_person = icon_button("account-plus-outline", _("Add person"))
        new_person.clicked.connect(lambda: self.edit_person(None))
        self.people_section = Section(_("People"), extra=new_person)
        self.people_section.body_layout.setSpacing(0)
        self.locked_notice = self.people_section.add(label(
            _("The saved faces could not be read (is the desktop keyring locked?). To avoid losing them, "
              "no changes will be saved until they can be read: unlock the keyring and restart the app."),
            level=2, wrap=True))
        self.locked_notice.setStyleSheet(f"color: {T.DANGER}; padding-bottom: 8px;")
        self.edit_buttons = [new_person]
        self.people_list = QVBoxLayout()
        self.people_list.setSpacing(0)
        self.people_section.add(self.people_list)
        ins.add(self.people_section)

        new_group = icon_button("plus", _("Add group"))
        new_group.clicked.connect(self._new_group)
        self.edit_buttons.append(new_group)
        self.groups_section = Section(_("Groups"), extra=new_group)
        self.groups_section.body_layout.setSpacing(0)
        self.groups_list = QVBoxLayout()
        self.groups_list.setSpacing(0)
        self.groups_section.add(self.groups_list)
        ins.add(self.groups_section)

        new_binding = icon_button("plus", _("Add action"))
        new_binding.clicked.connect(self.add_binding)
        self.bindings_section = Section(_("Actions"), extra=new_binding)
        self.bindings_section.body_layout.setSpacing(0)
        self.bindings_list = QVBoxLayout()
        self.bindings_list.setSpacing(0)
        self.bindings_section.add(self.bindings_list)
        ins.add(self.bindings_section)

        s = Section(_("Privacy"), expanded=False)
        self.privacy_note = s.add(label("", level=2, wrap=True))
        delete = button(_("Delete all faces"), "danger", "delete-outline")
        delete.clicked.connect(self._delete_all)
        s.add(row(delete, None))
        ins.add(s)
        ins.finish()
        self.refresh()

    def refresh(self):
        self.locked_notice.setVisible(self.store.locked)
        for b in self.edit_buttons:
            b.setEnabled(not self.store.locked)
        _clear(self.people_list)
        for p in sorted(self.store.people, key=lambda p: p["name"].lower()):
            r = ClickableRow()
            r.lay.addWidget(avatar(p))
            col = QVBoxLayout()
            col.setSpacing(1)
            name = label(p["name"])
            name.setStyleSheet("font-weight: 500;")
            col.addWidget(name)
            g = self.store.group(p["group"])
            n = len(p["samples"])
            samples = ngettext("{n} sample", "{n} samples", n).format(n=n)
            col.addWidget(label(f"{g['name'] if g else _('No group')} · {samples}", level=2))
            r.lay.addLayout(col, 1)
            if n < 5:
                warning = QLabel()
                warning.setPixmap(icons.icon("alert-outline", T.WARNING).pixmap(16, 16))
                warning.setToolTip(_("Few samples: add more so they are recognized reliably"))
                r.lay.addWidget(warning)
            r.clicked.connect(lambda p=p: self.edit_person(p))
            self.people_list.addWidget(r)
        if not self.store.people:
            self.people_list.addWidget(label(_("Nobody registered yet. Add a person with their name and a "
                                               "few pictures of their face."), level=2, wrap=True))

        _clear(self.groups_list)
        for g in self.store.groups:
            r = ClickableRow()
            r.setCursor(Qt.CursorShape.ArrowCursor)
            r.lay.addWidget(Dot(g["color"]))
            n = sum(1 for p in self.store.people if p["group"] == g["id"])
            r.lay.addWidget(label(g["name"]), 1)
            r.lay.addWidget(label(ngettext("{n} person", "{n} people", n).format(n=n), level=2))
            more = icon_button("dots-horizontal", _("Group options"))
            menu = QMenu(more)
            menu.addAction(_("Rename…"), lambda g=g: self._rename_group(g))
            menu.addAction(_("Change color"), lambda g=g: self._recolor_group(g))
            menu.addSeparator()
            menu.addAction(_("Delete group"), lambda g=g: self._delete_group(g))
            more.setMenu(menu)
            more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            r.lay.addWidget(more)
            self.groups_list.addWidget(r)

        self.refresh_bindings()
        where = {"keyring": _("the key is in the desktop keyring"),
                 "file": _("the key is in a file only you can read")}.get(
            self.store.key_source, _("the key will be stored in the desktop keyring"))
        self.privacy_note.setText(
            _("Faces are stored encrypted (AES-256) on this computer only, in {path}; {where}. "
              "Only register other people with their permission.").format(path=F.FACES_FILE, where=where))

    def refresh_bindings(self):
        _clear(self.bindings_list)
        bindings = [b for b in self.cfg["bindings"] if b["gesture"].startswith(C.RECOGNIZED_PREFIX)]
        for b in bindings:
            r = BindingRow(b)
            r.clicked.connect(lambda b=b: self.edit_binding.emit(b))
            r.toggled.connect(lambda _on: self.config_changed.emit())
            self.bindings_list.addWidget(r)
        if not bindings:
            self.bindings_list.addWidget(label(_("Choose what happens when someone shows up: for example, a "
                                                 "notification for an unknown face."), level=2, wrap=True))

    def update_status(self, e):
        if "recognized" not in e:
            return
        if not self.cfg["recognition"]["enabled"]:
            self.status_label.setText(_("Off"))
        elif e.get("covered"):
            self.status_label.setText(_("Camera covered"))
        else:
            names = e["recognized"]
            self.status_label.setText(_("In view: {names}").format(names=", ".join(names)) if names
                                      else _("Nobody in view"))

    def _set_enabled(self, on):
        self.cfg["recognition"]["enabled"] = on
        self.status_label.setText(_("On") if on else _("Off"))
        self.config_changed.emit()

    def _set_confirmations(self, v):
        self.cfg["recognition"]["confirmations"] = v
        self.config_changed.emit()

    def _set_known_only(self, on):
        self.cfg["security"]["known_people_only"] = on
        self.config_changed.emit()

    def _set_threshold(self, v):
        self.cfg["recognition"]["threshold"] = v / 100
        self.config_changed.emit()

    def _save_store(self):
        try:
            self.store.save()
        except (F.FaceStoreError, OSError) as e:
            show_error(self, _("Changes not saved"), str(e))
            return
        C.register_people(self.store.groups, self.store.people)
        self.refresh()
        self.people_changed.emit()

    def _new_group(self):
        name, ok = QInputDialog.getText(self, _("New group"), _("Group name"))
        if ok and name.strip():
            self.store.add_group(name.strip())
            self._save_store()

    def _rename_group(self, g):
        name, ok = QInputDialog.getText(self, _("Rename group"), _("Group name"), text=g["name"])
        if ok and name.strip():
            g["name"] = name.strip()
            self._save_store()

    def _recolor_group(self, g):
        i = F.COLORS.index(g["color"]) if g["color"] in F.COLORS else -1
        g["color"] = F.COLORS[(i + 1) % len(F.COLORS)]
        self._save_store()

    def _delete_group(self, g):
        n = sum(1 for p in self.store.people if p["group"] == g["id"])
        text = _("The group “{name}” and its actions will be deleted.").format(name=g["name"])
        if n:
            text += " " + ngettext("Its {n} member will be left without a group.",
                                   "Its {n} members will be left without a group.", n).format(n=n)
        if ask(self, _("Delete group"), text):
            self.store.remove_group(g["id"])
            self.orphaned_gestures.emit([C.GROUP_PREFIX + g["id"]])
            self._save_store()

    def _delete_all(self):
        if ask(self, _("Delete all faces"),
               _("Every registered person and their samples will be deleted. Groups are kept.")):
            ids = [C.PERSON_PREFIX + p["id"] for p in self.store.people]
            self.store.delete_all()
            self.orphaned_gestures.emit(ids)
            self._save_store()

    def edit_person(self, person):
        d = PersonDialog(person, self.store, self.get_engine, self)
        accepted = d.exec()
        if d.delete:
            self.store.remove_person(person["id"])
            self.orphaned_gestures.emit([C.PERSON_PREFIX + person["id"]])
        elif accepted:
            self.store.put_person(d.result_person())
        else:
            return
        self._save_store()


class PersonDialog(QDialog):
    def __init__(self, person, store, get_engine, parent=None):
        super().__init__(parent)
        new = person is None
        self.person = copy.deepcopy(person) if person else {"id": None, "name": "", "group": None, "samples": []}
        self.store, self.get_engine = store, get_engine
        self.delete = False
        self.models = None
        title = _("New person") if new else _("Edit person")
        self.setWindowTitle(title)
        self.setMinimumWidth(620)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(T.S6, T.S6, T.S6, T.S4)
        lay.setSpacing(T.S4)
        lay.addWidget(label(title, role="title"))

        self.name = QLineEdit(self.person["name"])
        self.name.setPlaceholderText(_("For example: Alex"))
        self.name.setFixedWidth(300)
        self.name.textChanged.connect(self._validate)
        lay.addWidget(SettingRow(_("Name"), self.name))
        self.group = QComboBox()
        self.group.addItem(_("No group"), None)
        for g in store.groups:
            self.group.addItem(icons.icon("circle", g["color"]), g["name"], g["id"])
        self.group.setCurrentIndex(max(0, self.group.findData(self.person["group"])))
        self.group.setFixedWidth(300)
        lay.addWidget(SettingRow(_("Group"), self.group))

        lay.addWidget(separator())
        header = QHBoxLayout()
        header.addWidget(label(_("SAMPLES"), role="heading"))
        self.count = label("", level=2)
        header.addWidget(self.count)
        header.addStretch()
        self.remove = button(_("Remove"), "ghost", "delete-outline")
        self.remove.clicked.connect(self._remove_selected)
        header.addWidget(self.remove)
        lay.addLayout(header)
        self.gallery = QListWidget()
        self.gallery.setViewMode(QListView.ViewMode.IconMode)
        self.gallery.setResizeMode(QListView.ResizeMode.Adjust)
        self.gallery.setMovement(QListView.Movement.Static)
        self.gallery.setIconSize(QSize(72, 72))
        self.gallery.setGridSize(QSize(82, 82))
        self.gallery.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.gallery.setFixedHeight(82 * 2 + 8)
        self.gallery.setStyleSheet("QListWidget::item { margin: 2px; padding: 0; }")
        self.gallery.itemSelectionChanged.connect(self._validate)
        lay.addWidget(self.gallery)

        self.preview = QLabel()
        self.preview.setFixedSize(320, 180)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setStyleSheet(f"background: {T.BG}; border-radius: {T.RADIUS}px;")
        self.preview.hide()
        self.hint = label("", level=2, wrap=True)
        lay.addLayout(row(self.preview, self.hint, spacing=T.S4))

        self.capture = button(_("Capture with the camera"), icon="camera-outline")
        self.capture.clicked.connect(self._start_capture)
        photos = button(_("Add photos…"), icon="image-plus")
        photos.clicked.connect(self._add_photos)
        lay.addLayout(row(self.capture, photos, None))
        lay.addWidget(label(_("10 to 20 samples from different angles and lighting work best. Photos must "
                              "show the face clearly; if there are several people, the largest face is "
                              "used."), level=2, wrap=True))
        lay.addStretch()

        lay.addWidget(separator())
        buttons = QHBoxLayout()
        if not new:
            b = button(_("Delete"), "danger", "delete-outline")
            b.clicked.connect(self._delete)
            buttons.addWidget(b)
        buttons.addStretch()
        b = button(_("Cancel"), "ghost")
        b.clicked.connect(self.reject)
        buttons.addWidget(b)
        self.save = button(_("Save"), "primary")
        self.save.setDefault(True)
        self.save.clicked.connect(self.accept)
        buttons.addWidget(self.save)
        lay.addLayout(buttons)

        self.timer = QTimer(self, interval=200, timeout=self._capture_step)
        self._capture_end = 0.0
        self._captured = 0
        self._fill_gallery()

    def _models(self):
        if self.models is None:
            from ..recognition import Models
            self.models = Models()
        return self.models

    def _fill_gallery(self):
        self.gallery.clear()
        for s in self.person["samples"]:
            it = QListWidgetItem(QIcon(pixmap_from_bgr(F.thumbnail_from_text(s["thumbnail"]), 72)), "")
            it.setSizeHint(QSize(76, 76))
            self.gallery.addItem(it)
        self._validate()

    def _validate(self):
        n = len(self.person["samples"])
        self.count.setText(str(n))
        self.remove.setEnabled(bool(self.gallery.selectedItems()))
        self.save.setEnabled(bool(self.name.text().strip()) and n > 0)

    def _add_sample(self, img, face):
        embedding, crop = self._models().embed(img, face)
        for s in self.person["samples"]:
            if float(np.dot(s["embedding"], embedding)) > DUPLICATE_SIMILARITY:
                return False
        self.person["samples"].append({"embedding": embedding, "thumbnail": F.thumbnail_to_text(crop)})
        return True

    def _add_photos(self):
        paths, _filter = QFileDialog.getOpenFileNames(self, _("Photos of the person"), "",
                                                      _("Images ({patterns})").format(patterns=IMAGE_FILTER))
        added = no_face = duplicates = 0
        for path in paths:
            img = cv2.imread(path)
            face = self._models().largest_face(img) if img is not None else None
            if face is None:
                no_face += 1
            elif self._add_sample(img, face):
                added += 1
            else:
                duplicates += 1
        if paths:
            parts = [ngettext("{n} added", "{n} added", added).format(n=added)]
            if no_face:
                parts.append(ngettext("{n} without a recognizable face", "{n} without a recognizable face",
                                      no_face).format(n=no_face))
            if duplicates:
                parts.append(ngettext("{n} almost identical to another", "{n} almost identical to others",
                                      duplicates).format(n=duplicates))
            self.hint.setText(", ".join(parts).capitalize() + ".")
            self._fill_gallery()

    def _remove_selected(self):
        for r in sorted((self.gallery.row(i) for i in self.gallery.selectedItems()), reverse=True):
            del self.person["samples"][r]
        self._fill_gallery()

    def _start_capture(self):
        engine = self.get_engine()
        if engine is None or engine.last_raw is None:
            self.hint.setText(_("The camera is not available."))
            return
        if engine.covered:
            self.hint.setText(_("The camera is covered: open the privacy shutter."))
            return
        self._models()
        self._captured = 0
        self._capture_end = time.monotonic() + CAPTURE_SECONDS
        self.capture.setEnabled(False)
        self.preview.show()
        self.timer.start()

    def _capture_step(self):
        engine = self.get_engine()
        remaining = self._capture_end - time.monotonic()
        if engine is None or remaining <= 0 or self._captured >= SAMPLES_PER_CAPTURE:
            self.timer.stop()
            self.capture.setEnabled(True)
            self.preview.hide()
            self.hint.setText(ngettext("Capture finished: {n} new sample.", "Capture finished: {n} new samples.",
                                       self._captured).format(n=self._captured))
            self._fill_gallery()
            return
        img = engine.last_raw
        if img is None:
            return
        img = img.copy()
        face = self._models().largest_face(img)
        shown = cv2.flip(img, 1)  # mirrored, easier to position yourself
        if face is not None:
            x, y, w, h = (int(v) for v in face[:4])
            good = face[14] >= 0.9 and w >= img.shape[1] * 0.08
            color = (80, 207, 62) if good else (10, 165, 229)
            cv2.rectangle(shown, (img.shape[1] - x - w, y), (img.shape[1] - x, y + h), color, 4)
            if good and self._add_sample(img, face):
                self._captured += 1
                self._fill_gallery()
        self.preview.setPixmap(pixmap_from_bgr(cv2.resize(shown, (320, 180))))
        self.hint.setText(_("Look at the camera and turn your head a little to the sides, up and down.") + "\n" +
                          _("{done} of {total} · {seconds} s").format(
                              done=self._captured, total=SAMPLES_PER_CAPTURE, seconds=round(remaining)))

    def result_person(self):
        self.person["name"] = self.name.text().strip()
        self.person["group"] = self.group.currentData()
        return self.person

    def _delete(self):
        if ask(self, _("Delete person"),
               _("“{name}”, their samples and their actions will be deleted.").format(
                   name=self.person["name"])):
            self.delete = True
            self.reject()

    def done(self, result):
        self.timer.stop()
        super().done(result)
