"""Virtual camera section at the top of the Camera tab."""
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QColorDialog, QFileDialog, QLabel, QVBoxLayout, QWidget

from .. import virtual_camera as VC
from ..i18n import _
from . import theme as T
from .widgets import Inspector, Section, Segmented, SettingRow, SliderRow, SwitchRow, button, label, row

BACKGROUNDS = [("none", _("Original")), ("blur", _("Blur")), ("color", _("Color")), ("image", _("Image"))]
IMAGE_FILTER = "*.jpg *.jpeg *.png *.webp *.bmp"


class VirtualCameraPanel(QWidget):
    config_changed = Signal()

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.device_label = VC.DEVICE_LABELS[0]
        vc = cfg["virtual_camera"]
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        ins = Inspector()
        lay.addWidget(ins)
        s = Section(_("Virtual camera"))
        self.master = s.add(SwitchRow(_("Virtual camera"), vc["enabled"], " "))
        self.master.toggled.connect(self._set_enabled)
        self.status_label = self.master.help

        # Shown while the kernel module is missing
        self.install = QWidget()
        il = QVBoxLayout(self.install)
        il.setContentsMargins(0, 0, 0, 0)
        il.setSpacing(T.S2)
        il.addWidget(label(_("To use it in Meet, Zoom or OBS, the v4l2loopback module has to be installed once. "
                             "Run this in a terminal (it will ask for your password):"), level=2, wrap=True))
        cmd = QLabel(VC.INSTALL_COMMAND)
        cmd.setTextFormat(Qt.TextFormat.PlainText)
        cmd.setWordWrap(True)
        cmd.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        cmd.setStyleSheet(f"font-family: 'JetBrains Mono', 'DejaVu Sans Mono', monospace; font-size: 12px; "
                          f"background: {T.RAISED}; border: 1px solid {T.BORDER}; border-radius: {T.RADIUS}px; "
                          f"padding: {T.S2}px; color: {T.TEXT};")
        il.addWidget(cmd)
        copy = button(_("Copy command"), icon="content-copy")
        copy.clicked.connect(lambda: (QApplication.clipboard().setText(VC.INSTALL_COMMAND),
                                      copy.setText(_("Copied"))))
        check = button(_("Check again"), "ghost", "refresh")
        check.clicked.connect(self.refresh)
        il.addLayout(row(copy, check, None))
        s.add(self.install)

        self.options = QWidget()
        ol = QVBoxLayout(self.options)
        ol.setContentsMargins(0, 0, 0, 0)
        ol.setSpacing(T.S4)
        ol.addWidget(label(_("Background")))
        self.background = Segmented(BACKGROUNDS, vc["background"])
        self.background.changed.connect(lambda v: self._set("background", v))
        ol.addWidget(self.background)
        self.blur = SliderRow(_("Blur strength"), 6, 80, vc["blur"], 30, str)
        self.blur.changed.connect(lambda v: self._set("blur", v))
        ol.addWidget(self.blur)
        self.color_button = button("")
        self.color_button.setFixedWidth(112)
        self.color_button.clicked.connect(self._pick_color)
        self.color_row = SettingRow(_("Background color"), self.color_button)
        ol.addWidget(self.color_row)
        self.image_button = button(_("Choose…"), icon="image-outline")
        self.image_button.clicked.connect(self._pick_image)
        self.image_row = SettingRow(_("Background image"), self.image_button, " ")
        ol.addWidget(self.image_row)
        self.resolution = Segmented([(720, "720p"), (1080, "1080p")], vc["resolution"])
        self.resolution.setFixedWidth(160)
        self.resolution.changed.connect(lambda v: self._set("resolution", v))
        ol.addWidget(SettingRow(_("Resolution"), self.resolution, _("720p is what Meet, Zoom and Teams use")))
        mirror = SwitchRow(_("Mirror the image"), vc["mirror"],
                           _("When off, others see you as a person in front of you would, and can read "
                             "any text you hold up"))
        mirror.toggled.connect(lambda on: self._set("mirror", on))
        ol.addWidget(mirror)
        s.add(self.options)
        self.tip = s.add(label("", level=2, wrap=True))
        ins.add(s)
        self.refresh()

    def refresh(self):
        installed = VC.module_loaded()
        vc = self.cfg["virtual_camera"]
        self.install.setVisible(not installed)
        self.master.setEnabled(installed or vc["enabled"])
        self.tip.setVisible(installed)
        device = VC.find_device() if installed else None
        if device:
            self.device_label = device[1]
        self.tip.setText(_("In Meet, Zoom or OBS pick the camera “{name}”, not the real one: this app "
                           "is using the real camera and it cannot be shared.").format(name=self.device_label))
        # The background can be tried in the preview even without the module.
        self.blur.setVisible(vc["background"] == "blur")
        self.color_row.setVisible(vc["background"] == "color")
        self.image_row.setVisible(vc["background"] == "image")
        text_color = "white" if QColor(vc["color"]).lightness() < 140 else "black"
        self.color_button.setText(vc["color"].upper())
        self.color_button.setStyleSheet(f"QPushButton {{ background: {vc['color']}; color: {text_color}; }}")
        self.image_row.help.setText(Path(vc["image"]).name if vc["image"] else _("None chosen"))
        if not vc["enabled"]:
            self.status_label.setText(_("Off") if installed else _("Module not installed"))

    def show_state(self, code):
        """State reported by the engine."""
        if not self.cfg["virtual_camera"]["enabled"]:
            self.refresh()
            return
        if code.startswith("streaming:"):
            self.device_label, path = code.split(":", 1)[1].split("|", 1)
            self.refresh()
            self.status_label.setText(_("Streaming as “{name}” ({path})").format(name=self.device_label, path=path))
        elif code == "not_installed":
            self.status_label.setText(_("Module not installed"))
            self.refresh()
        elif code == "no_device":
            self.status_label.setText(_("The module is loaded but there is no virtual camera"))
        elif code.startswith("error:"):
            self.status_label.setText(_("Error: {error}").format(error=code.split(":", 1)[1]))

    def _set_enabled(self, on):
        self.cfg["virtual_camera"]["enabled"] = on
        self.status_label.setText(_("Starting…") if on else _("Off"))
        self.config_changed.emit()

    def _set(self, key, value):
        self.cfg["virtual_camera"][key] = value
        self.refresh()
        self.config_changed.emit()

    def _pick_color(self):
        c = QColorDialog.getColor(QColor(self.cfg["virtual_camera"]["color"]), self, _("Background color"))
        if c.isValid():
            self._set("color", c.name())

    def _pick_image(self):
        path, _filter = QFileDialog.getOpenFileName(self, _("Background image"), self.cfg["virtual_camera"]["image"],
                                                    _("Images ({patterns})").format(patterns=IMAGE_FILTER))
        if path:
            self._set("image", path)
