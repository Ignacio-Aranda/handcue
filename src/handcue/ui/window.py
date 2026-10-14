"""Main window: camera preview on the left, settings inspector on the right."""
from datetime import datetime

from PySide6.QtCore import QObject, QTimer, Signal, Slot
from PySide6.QtDBus import QDBusConnection
from PySide6.QtWidgets import (
    QApplication, QComboBox, QHBoxLayout, QLabel, QMainWindow, QMenu, QStackedWidget, QSystemTrayIcon, QTabBar,
    QVBoxLayout, QWidget,
)

from .. import APP_NAME, config, desktop
from ..actions import Executor
from ..camera import Camera, list_cameras
from ..catalog import INTERNAL_ACTIONS, register_people
from ..desktop_input import PortalInput
from ..engine import Engine
from ..faces import FaceStore
from ..i18n import _
from . import icons
from . import theme as T
from .camera_panel import CameraPanel
from .faces_panel import FacesPanel
from .gestures_panel import GesturesPanel
from .preferences import Preferences
from .preview import Preview
from .virtual_camera_panel import VirtualCameraPanel
from .widgets import Dot, button, icon_button, label, scrollable, separator


class SleepWatcher(QObject):
    """Signals the return from suspend (logind PrepareForSleep): the camera may have
    lost power and gone back to its factory settings."""
    resumed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.connected = QDBusConnection.systemBus().connect(
            "org.freedesktop.login1", "/org/freedesktop/login1", "org.freedesktop.login1.Manager",
            "PrepareForSleep", self, "1on_prepare(bool)")

    @Slot(bool)
    def on_prepare(self, entering):
        if not entering:
            self.resumed.emit()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(desktop.app_icon())
        self.resize(1440, 880)
        self.setMinimumSize(1000, 640)
        self.cfg = config.load()
        self.engine = None
        self.cam = None
        self.activity = []
        self.quitting = False
        self.covered = False
        self._format_text = ""
        self._tray_state = None
        self._queue = []  # messages from worker threads, drained on the UI thread

        self.store = FaceStore()
        faces_error = None
        try:
            self.store.load()
        except Exception as e:  # noqa: BLE001 - e.g. locked keyring or damaged file
            faces_error = _("Could not read the saved faces: {error}").format(error=e)
        register_people(self.store.groups, self.store.people)

        self.input = PortalInput(self.cfg["portal_token"], self._token_from_thread, self._log_from_thread)
        self.executor = Executor(self.input, self._log_from_thread, lambda: self.cfg)
        self.save_timer = QTimer(self, singleShot=True, interval=300, timeout=self.save_now)

        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._top_bar())
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addLayout(self._preview_area(), 1)
        body.addWidget(self._inspector())
        root.addLayout(body, 1)
        self.setCentralWidget(central)

        self.retry = QTimer(self, singleShot=True, interval=2000, timeout=self.open_camera)
        QTimer(self, interval=100, timeout=self._drain_queue).start()
        if faces_error:
            QTimer.singleShot(500, lambda: self.notify(faces_error, 6, error=True))
        self._fill_cameras()
        self._create_tray()
        self.sleep_watcher = SleepWatcher(self)
        # After resume, give the camera time to come back before writing to it.
        self.sleep_watcher.resumed.connect(lambda: QTimer.singleShot(3000, self.reapply_controls))
        QTimer.singleShot(0, self.open_camera)

    def _top_bar(self):
        bar = QWidget()
        bar.setObjectName("topBar")
        bar.setFixedHeight(52)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(T.S4, 0, T.S3, 0)
        lay.setSpacing(T.S2)
        logo = QLabel()
        logo.setPixmap(icons.icon("webcam", T.ACCENT).pixmap(20, 20))
        lay.addWidget(logo)
        self.camera_combo = QComboBox()
        self.camera_combo.setProperty("flat", "true")
        self.camera_combo.setMinimumWidth(220)
        self.camera_combo.activated.connect(self._camera_chosen)
        lay.addWidget(self.camera_combo)
        lay.addSpacing(T.S2)
        self.status_dot = Dot()
        lay.addWidget(self.status_dot)
        self.format_label = label("", level=2)
        lay.addWidget(self.format_label)
        lay.addStretch()
        prefs = icon_button("cog-outline", _("Preferences"))
        prefs.clicked.connect(lambda: Preferences(self).exec())
        lay.addWidget(prefs)
        return bar

    def _preview_area(self):
        view = self.cfg["view"]
        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)
        self.preview = Preview()
        col.addWidget(self.preview, 1)

        bar = QWidget()
        bar.setObjectName("viewBar")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(T.S4, 0, T.S4, T.S4)
        bl.setSpacing(T.S1)
        self.view_buttons = {}

        def add_toggle(key, icon, tooltip):
            b = icon_button(icon, tooltip, checkable=True, checked=view[key])
            b.toggled.connect(lambda on: self.set_option(("view", key), on))
            bl.addWidget(b)
            self.view_buttons[key] = b

        add_toggle("mirror", "flip-horizontal", _("Mirror"))
        add_toggle("grid", "grid", _("Rule-of-thirds grid"))
        add_toggle("histogram", "chart-histogram", _("Histogram"))
        add_toggle("zebra", "texture-box", _("Zebra (overexposed areas)"))
        divider = QWidget()
        divider.setFixedSize(1, 20)
        divider.setStyleSheet(f"background: {T.BORDER_STRONG};")
        bl.addSpacing(T.S2)
        bl.addWidget(divider)
        bl.addSpacing(T.S2)
        add_toggle("overlay", "vector-polyline", _("Show what is recognized"))
        add_toggle("effects", "auto-fix", _("Visual effects on the hands"))
        bl.addStretch()
        photo = button(_("Take photo"), icon="camera-outline")
        photo.clicked.connect(lambda: self.engine and self.engine.take_photo(0))
        bl.addWidget(photo)
        col.addWidget(bar)
        return col

    def _inspector(self):
        panel = QWidget()
        panel.setObjectName("inspector")
        panel.setFixedWidth(372)
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        tabs = QTabBar()
        tabs.setDrawBase(False)
        tabs.setExpanding(False)
        tabs.addTab(_("Camera"))
        tabs.addTab(_("Gestures"))
        tabs.addTab(_("Faces"))
        header = QWidget()
        hl = QHBoxLayout(header)
        hl.setContentsMargins(T.S3, T.S2, T.S3, 0)
        hl.addWidget(tabs)
        hl.addStretch()
        lay.addWidget(header)
        lay.addWidget(separator())

        self.camera_panel = CameraPanel()
        self.camera_panel.controls_changed.connect(self._controls_changed)
        self.camera_panel.format_changed.connect(self._format_changed)
        self.camera_panel.auto_framing_changed.connect(lambda on: self.set_option(("auto_framing",), on))
        self.camera_panel.profile_saved.connect(self._profile_saved)
        self.camera_panel.profile_deleted.connect(self._profile_deleted)
        self.camera_panel.message.connect(self.notify_message)
        self.gestures_panel = GesturesPanel(self.cfg)
        self.gestures_panel.config_changed.connect(self.save)
        self.gestures_panel.test.connect(self.test_binding)
        self.faces_panel = FacesPanel(self.cfg, self.store, lambda: self.engine)
        self.faces_panel.config_changed.connect(self.save)
        self.faces_panel.people_changed.connect(self._people_changed)
        self.faces_panel.add_binding.connect(lambda: self.gestures_panel.add_binding(
            "recognized:unknown", "notification", _("Someone unknown is in front of the camera"), hold=0))
        self.faces_panel.edit_binding.connect(self.gestures_panel.edit_binding)
        self.faces_panel.orphaned_gestures.connect(self._drop_bindings)
        self.gestures_panel.config_changed.connect(self.faces_panel.refresh_bindings)
        self.virtual_panel = VirtualCameraPanel(self.cfg)
        self.virtual_panel.config_changed.connect(self.save)
        camera_page = QWidget()
        cp = QVBoxLayout(camera_page)
        cp.setContentsMargins(0, 0, 0, 0)
        cp.setSpacing(0)
        cp.addWidget(self.virtual_panel)
        cp.addWidget(separator())
        cp.addWidget(self.camera_panel, 1)
        stack = QStackedWidget()
        stack.addWidget(scrollable(camera_page))
        stack.addWidget(scrollable(self.gestures_panel))
        stack.addWidget(scrollable(self.faces_panel))
        tabs.currentChanged.connect(stack.setCurrentIndex)
        self.tabs = tabs
        lay.addWidget(stack, 1)
        return panel

    # --- camera

    def _fill_cameras(self):
        self.camera_combo.clear()
        cameras = list_cameras()
        for index, name in cameras:
            self.camera_combo.addItem(name, index)
        if not cameras:
            self.camera_combo.addItem(_("No camera"), -1)
        i = self.camera_combo.findData(self.cfg["camera"]["index"])
        if i < 0 and cameras:
            self.cfg["camera"]["index"] = cameras[0][0]
            i = 0
        self.camera_combo.setCurrentIndex(max(0, i))

    def _camera_chosen(self, _i):
        index = self.camera_combo.currentData()
        if index is None or index < 0 or index == self.cfg["camera"]["index"]:
            return
        self.cfg["camera"]["index"] = index
        self.cfg["camera_controls"] = {}
        self.save()
        self.open_camera()

    def _set_status(self, color, text):
        self.status_dot.set_color(color)
        self.format_label.setText(text)

    def open_camera(self):
        self.stop_engine()
        if self.cam:
            self.camera_panel.save_timer.stop()
            self.cam.close()
            self.cam = None
        index = self.cfg["camera"]["index"]
        if index not in [i for i, _name in list_cameras()]:
            self._fill_cameras()
            self.camera_panel.build(None, self.cfg)
            self.preview.show_placeholder(_("Connect a camera"))
            self._set_status(T.WARNING, _("Waiting for a camera"))
            self.retry.start()
            return
        try:
            self.cam = Camera(index)
        except OSError as e:
            self.preview.show_placeholder(_("Cannot open the camera ({error})").format(error=e.strerror))
            self.retry.start()
            return
        self._fill_cameras()
        self.camera_panel.build(self.cam, self.cfg)
        self.preview.show_placeholder(_("Opening the camera…"))
        self._set_status(T.TEXT_3, _("Connecting…"))
        e = self.engine = Engine(self.cfg, self.input, self.executor)
        e.camera = self.cam
        e.face_store = self.store
        e.frame_ready.connect(self.preview.show_frame)
        e.status.connect(self.gestures_panel.update_status)
        e.status.connect(self.faces_panel.update_status)
        e.status.connect(self._engine_status)
        e.message.connect(self.notify_message)
        e.failed.connect(self._engine_failed)
        e.camera_opened.connect(self._camera_opened)
        e.framing_changed.connect(self.camera_panel.show_framing)
        e.effects_toggled.connect(self.view_buttons["effects"].setChecked)
        e.cover_changed.connect(self._cover_changed)
        e.virtual_status.connect(self.virtual_panel.show_state)
        e.preview_visible = self.isVisible()
        e.start()

    def _camera_opened(self, w, h, fps):
        if self.cam and self.cfg["camera_controls"]:
            self.cam.apply(self.cfg["camera_controls"])
            # Right after streaming starts the camera ignores some writes (manual focus
            # gets lost), so apply everything again once it has settled.
            cam = self.cam
            QTimer.singleShot(2000, lambda: self.cam is cam and self.reapply_controls(log=False))
        self.camera_panel.refresh()
        self._format_text = f"{h}p · {fps} fps"
        if not self.covered:
            self._set_status(T.SUCCESS, self._format_text)

    def _people_changed(self):
        if self.engine:
            self.engine.reload_gallery()
        self.gestures_panel.refresh()  # names of people and groups appear in the list

    def _drop_bindings(self, gestures):
        before = len(self.cfg["bindings"])
        self.cfg["bindings"] = [b for b in self.cfg["bindings"] if b["gesture"] not in gestures]
        if len(self.cfg["bindings"]) != before:
            self.gestures_panel.cfg = self.cfg
            self.gestures_panel.refresh()
            self.faces_panel.refresh_bindings()
            self.save()

    def reapply_controls(self, log=True):
        """Writes the saved controls to the camera again. Webcams keep no settings
        Linux can reach; they lose them when they lose power."""
        if self.cam and self.cfg["camera_controls"]:
            try:
                self.cam.apply(self.cfg["camera_controls"], nudge=True)
            except OSError:
                return  # the camera was reconnected; the engine reopens it and applies them
            self.camera_panel.refresh()
            if log:
                self._log(_("Camera settings restored"))

    def _engine_failed(self, text):
        self.notify(text, 5, error=True)
        self.preview.show_placeholder(text)
        self._set_status(T.DANGER, _("No signal"))
        if not self.quitting:
            self.retry.start()

    def stop_engine(self):
        if self.engine:
            self.engine.stop()
            self.engine.wait(5000)
            self.engine = None

    def _format_changed(self, w, h, fps):
        self.cfg["camera"].update(width=w, height=h, fps=fps)
        self.save()

    def _controls_changed(self, values):
        self.cfg["camera_controls"] = values
        self.save()

    def _profile_saved(self, name, values):
        self.cfg["camera_profiles"][name] = values
        self.save()
        self.notify(_("Profile “{name}” saved").format(name=name))

    def _profile_deleted(self, name):
        self.cfg["camera_profiles"].pop(name, None)
        self.save()
        self.notify(_("Profile “{name}” deleted").format(name=name))

    # --- settings

    def set_option(self, path, value):
        d = self.cfg
        for k in path[:-1]:
            d = d[k]
        d[path[-1]] = value
        self.save()
        if path == ("view", "mirror") and self.cam:
            self.camera_panel.refresh()

    def save(self):
        if self.engine:
            self.engine.set_config(self.cfg)
        self.save_timer.start()
        self._update_tray()

    def save_now(self):
        try:
            config.save(self.cfg)
        except OSError as e:
            self.notify(_("Could not save the settings: {error}").format(error=e), error=True)

    def test_binding(self, b):
        if self.engine:
            self.engine.fire(b)
        elif b["action"] in INTERNAL_ACTIONS:
            self.notify(_("The camera is needed to try this action"), error=True)
        else:
            self.executor.run(b["action"], b.get("value", ""), b.get("name") or b["action"])

    def revoke_permission(self):
        self.input.disconnect()
        self.input.token = ""
        self.cfg["portal_token"] = ""
        self.save()
        self.notify(_("Keyboard and mouse permission revoked"))

    # --- messages from other threads

    def _log_from_thread(self, text, error=False):
        self._queue.append(("log", text, error))

    def _token_from_thread(self, token):
        self._queue.append(("token", token, False))

    def _drain_queue(self):
        while self._queue:
            kind, value, error = self._queue.pop(0)
            if kind == "token":
                self.cfg["portal_token"] = value
                self.save()
            else:
                self.notify(value, error=error)

    def _log(self, text):
        self.activity.append(f"{datetime.now():%H:%M:%S}  {text}")
        del self.activity[:-500]

    def notify(self, text, seconds=2.5, error=False):
        self._log(text)
        self.preview.show_toast(text, seconds, error)

    def notify_message(self, text, error):
        self.notify(text, error=error)

    # --- tray and visibility

    def _create_tray(self):
        self.tray = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QSystemTrayIcon(desktop.tray_icon("active"), self)
        self._tray_menu = QMenu()
        self._tray_menu.addAction(_("Open control panel"), self.show_window)
        self._tray_menu.addSeparator()
        self.gestures_action = self._tray_menu.addAction(_("Gestures enabled"))
        self.gestures_action.setCheckable(True)
        self.gestures_action.setChecked(self.cfg["gestures_enabled"])
        self.gestures_action.toggled.connect(self._gestures_from_tray)
        self._tray_menu.addAction(_("Take photo (3 s)"), lambda: self.engine and self.engine.take_photo(3))
        self._tray_menu.addSeparator()
        self._tray_menu.addAction(_("Quit"), self.quit)
        self.tray.setContextMenu(self._tray_menu)
        self.tray.activated.connect(
            lambda reason: self.toggle_window() if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
        self.tray.show()
        self._update_tray()

    def _update_tray(self):
        if not getattr(self, "tray", None):
            return
        if not self.cfg["gestures_enabled"]:
            state, text = "off", _("Gestures off")
        elif self.covered:
            state, text = "covered", _("Camera covered: detection paused")
        elif self.engine and self.engine.paused:
            state, text = "paused", _("Gestures paused")
        else:
            state, text = "active", _("Recognizing gestures")
        if state != self._tray_state:
            self._tray_state = state
            self.tray.setIcon(desktop.tray_icon(state))
            self.tray.setToolTip(f"{APP_NAME}\n{text}")
        self.gestures_action.blockSignals(True)
        self.gestures_action.setChecked(self.cfg["gestures_enabled"])
        self.gestures_action.blockSignals(False)

    def _gestures_from_tray(self, on):
        self.cfg["gestures_enabled"] = on
        self.gestures_panel.master.setChecked(on)
        self.gestures_panel.show_status()
        self.save()

    def _engine_status(self, e):
        if "paused" in e and self.tray:
            self._update_tray()

    def _cover_changed(self, covered):
        self.covered = covered
        if covered:
            self._set_status(T.WARNING, _("Camera covered"))
            self.notify(_("Camera covered: detection paused"))
        else:
            self._set_status(T.SUCCESS, self._format_text or _("Active"))
            self.notify(_("Camera uncovered: detection active"))
        self._update_tray()

    def show_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def toggle_window(self):
        if self.isVisible() and not self.isMinimized():
            self.hide()
        else:
            self.show_window()

    def showEvent(self, ev):  # noqa: N802
        if self.engine:
            self.engine.preview_visible = True
        if self.cam:  # show what the camera has now, not what was read when hidden
            self.camera_panel.refresh()
        super().showEvent(ev)

    def hideEvent(self, ev):  # noqa: N802
        if self.engine:  # hidden: keep recognizing, but stop drawing the preview
            self.engine.preview_visible = False
        super().hideEvent(ev)

    def quit(self):
        self.quitting = True
        self.close()
        QApplication.quit()

    def closeEvent(self, ev):  # noqa: N802
        if self.tray and not self.quitting:
            # Closing the window keeps the app running in the tray.
            ev.ignore()
            self.hide()
            if not self.cfg["tray_notice_shown"]:
                self.tray.showMessage(_("{app} is still running").format(app=APP_NAME),
                                      _("It is in the system tray. To quit completely, right-click it and "
                                        "choose Quit."), desktop.app_icon(), 6000)
                self.cfg["tray_notice_shown"] = True
                self.save()
            return
        self.quitting = True
        self.retry.stop()
        self.stop_engine()
        if self.cam:
            if self.camera_panel.save_timer.isActive():
                self.camera_panel.save_timer.stop()
                self.camera_panel.emit_controls()
            self.cam.close()
        self.input.disconnect()
        self.executor.close()
        self.save_now()
        if self.tray:
            self.tray.hide()
        ev.accept()
