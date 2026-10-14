from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QHBoxLayout, QLineEdit, QPlainTextEdit, QSpinBox, QVBoxLayout, QWidget,
)

from .. import config, desktop
from ..i18n import _
from . import theme as T
from .widgets import (
    Dot, Inspector, Section, Segmented, SettingRow, SliderRow, SwitchRow, button, label, row, scrollable,
    separator,
)

THRESHOLDS = {
    "hand_confidence": _("Hand gestures"), "swipe": _("Swipes"), "smile": _("Smile"),
    "mouth_open": _("Mouth open"), "wink": _("Winks and closed eyes"), "brows": _("Eyebrows"),
    "kiss": _("Kiss"), "cheeks": _("Cheeks"), "head_turn": _("Head turn"), "head_tilt": _("Head tilt"),
}


class Preferences(QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        cfg = window.cfg
        self.setWindowTitle(_("Preferences"))
        self.resize(560, 680)
        main = QVBoxLayout(self)
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)
        header = QWidget()
        hl = QHBoxLayout(header)
        hl.setContentsMargins(T.S6, T.S6, T.S6, T.S3)
        hl.addWidget(label(_("Preferences"), role="title"))
        main.addWidget(header)

        ins = Inspector()
        s = Section(_("General"))
        login = s.add(SwitchRow(_("Start when I log in"), cfg["start_on_login"],
                                _("Runs in the background and restores the camera settings")))
        login.toggled.connect(self._set_start_on_login)
        covered = s.add(SwitchRow(_("Pause when the camera is covered"), cfg["pause_when_covered"],
                                  _("Notices the privacy shutter and stops detection, so it does not "
                                    "report things like “nobody there”")))
        covered.toggled.connect(lambda on: self._set(("pause_when_covered",), on))
        self.folder = QLineEdit(str(config.photo_folder(cfg)))
        self.folder.editingFinished.connect(lambda: self._set(("photo_folder",), self.folder.text().strip()))
        choose = button(_("Choose…"))
        choose.clicked.connect(self._choose_folder)
        s.add(label(_("Folder for photos and screenshots"), level=2))
        s.add(row(self.folder, choose))
        ins.add(s)

        s = Section(_("Keyboard and mouse"))
        self.portal_state = label("")
        self.portal_dot = Dot()
        grant = button(_("Grant permission"))
        grant.clicked.connect(lambda: window.executor.pool.submit(window.input.connect))
        revoke = button(_("Revoke"), "ghost")
        revoke.clicked.connect(window.revoke_permission)
        s.add(row(self.portal_dot, self.portal_state, None, revoke, grant))
        s.add(label(_("Needed for gestures that type text, press keys or move the mouse. The desktop asks "
                      "for confirmation once."), level=2, wrap=True))
        hand = Segmented([("right", _("Right")), ("left", _("Left")), ("any", _("Either"))], cfg["mouse"]["hand"])
        hand.setFixedWidth(260)
        hand.changed.connect(lambda v: self._set(("mouse", "hand"), v))
        s.add(SettingRow(_("Virtual mouse hand"), hand))
        speed = s.add(SliderRow(_("Pointer speed"), 2, 60, int(cfg["mouse"]["speed"] * 10), 15,
                                lambda v: f"{v / 10:.1f}×"))
        speed.changed.connect(lambda v: self._set(("mouse", "speed"), v / 10))
        smoothing = s.add(SliderRow(_("Smoothing"), 0, 90, int(cfg["mouse"]["smoothing"] * 100), 50,
                                    lambda v: f"{v} %"))
        smoothing.changed.connect(lambda v: self._set(("mouse", "smoothing"), v / 100))
        ins.add(s)

        s = Section(_("Sensitivity"), expanded=False)
        s.add(label(_("Higher values need more pronounced gestures and reduce accidental triggers."),
                    level=2, wrap=True))
        for key, title in THRESHOLDS.items():
            slider = s.add(SliderRow(title, 1, 100, int(cfg["thresholds"][key] * 100),
                                     int(config.DEFAULTS["thresholds"][key] * 100), str))
            slider.changed.connect(lambda v, k=key: self._set(("thresholds", k), v / 100))
        hands = QSpinBox(minimum=1, maximum=6, value=cfg["max_hands"])
        hands.setFixedWidth(72)
        hands.valueChanged.connect(lambda v: self._set(("max_hands",), v))
        people = QSpinBox(minimum=1, maximum=6, value=cfg["max_people"])
        people.setFixedWidth(72)
        people.valueChanged.connect(lambda v: self._set(("max_people",), v))
        s.add(SettingRow(_("Hands at once"), hands))
        s.add(SettingRow(_("People at once"), people))
        ins.add(s)

        s = Section(_("Activity log"), expanded=False)
        log = QPlainTextEdit(readOnly=True)
        log.setPlainText("\n".join(window.activity) or _("No activity yet."))
        log.setMinimumHeight(180)
        s.add(log)
        ins.add(s)
        ins.finish()
        main.addWidget(scrollable(ins), 1)

        main.addWidget(separator())
        footer = QWidget()
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(T.S6, T.S3, T.S6, T.S3)
        done = button(_("Done"), "primary")
        done.clicked.connect(self.accept)
        fl.addStretch()
        fl.addWidget(done)
        main.addWidget(footer)
        self.timer = QTimer(self, interval=1000, timeout=self._show_portal_state)
        self.timer.start()
        self._show_portal_state()

    def _set(self, path, value):
        self.window.set_option(path, value)

    def _show_portal_state(self):
        if self.window.input.connected:
            self.portal_state.setText(_("Connected"))
            self.portal_dot.set_color(T.SUCCESS)
        elif self.window.cfg["portal_token"]:
            self.portal_state.setText(_("Permission granted"))
            self.portal_dot.set_color(T.SUCCESS)
        else:
            self.portal_state.setText(_("No permission"))
            self.portal_dot.set_color(T.TEXT_3)

    def _choose_folder(self):
        d = QFileDialog.getExistingDirectory(self, _("Photo folder"), self.folder.text())
        if d:
            self.folder.setText(d)
            self._set(("photo_folder",), d)

    def _set_start_on_login(self, on):
        self._set(("start_on_login",), on)
        desktop.sync_integration(on)
