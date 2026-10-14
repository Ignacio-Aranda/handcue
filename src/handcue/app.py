import argparse
import sys
import time

from . import APP_ID, APP_NAME, __version__
from .i18n import _


def apply_camera_and_exit():
    """Headless mode: write the saved camera controls and quit."""
    from . import config
    from .camera import Camera, list_cameras

    cfg = config.load()
    index = cfg["camera"]["index"]
    for _attempt in range(30):  # the camera may still be appearing right after login
        if index in [i for i, _name in list_cameras()]:
            break
        time.sleep(1)
    else:
        print(f"/dev/video{index} not found", file=sys.stderr)
        return 1
    cam = Camera(index)
    errors = cam.apply(cfg["camera_controls"])
    cam.close()
    print("Camera settings applied" + (f" (warnings: {errors})" if errors else ""))
    return 0


def _install_qt_translations(app):
    from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator

    translator = QTranslator(app)
    if translator.load(QLocale.system(), "qtbase", "_", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
        app.installTranslator(translator)


def main():
    parser = argparse.ArgumentParser(prog="handcue", description=_(
        "Control your computer with hand, face and body gestures from your webcam."))
    parser.add_argument("--background", action="store_true",
                        help=_("start hidden in the system tray (used when starting on login)"))
    parser.add_argument("--apply-camera", action="store_true",
                        help=_("apply the saved camera settings and exit"))
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = parser.parse_args()
    from . import config
    config.move_legacy_dirs()
    if args.apply_camera:
        sys.exit(apply_camera_and_exit())

    from PySide6.QtWidgets import QApplication

    from . import desktop
    from .ui import theme
    from .ui.widgets import WheelFilter
    from .ui.window import MainWindow

    app = QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setDesktopFileName(APP_ID)
    if desktop.notify_running_instance():
        return  # already running: its window has been shown
    app.setQuitOnLastWindowClosed(False)  # closing the window keeps it in the tray
    app.setStyle("Fusion")
    app.setWindowIcon(desktop.app_icon())
    _install_qt_translations(app)
    theme.load_fonts(app)
    app.setStyleSheet(theme.STYLESHEET)
    wheel_filter = WheelFilter(app)
    app.installEventFilter(wheel_filter)
    window = MainWindow()
    window.server = desktop.listen_for_instances(window.show_window, window)
    try:
        desktop.sync_integration(window.cfg["start_on_login"])
    except OSError as e:
        window.notify(_("Could not set up start on login: {error}").format(error=e), error=True)
    if not args.background or not window.tray:
        window.show()
    sys.exit(app.exec())
