"""Desktop integration: icons, menu entry, start on login and single instance."""
import os
import shlex
import shutil
import sys
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from . import APP_ID, APP_NAME
from .i18n import _
from .ui import icons
from .ui import theme as T

APP_ICON = Path(__file__).resolve().parent / "resources" / "icon.svg"
_DATA_HOME = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share")
_CONFIG_HOME = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
LAUNCHER = _DATA_HOME / "applications" / f"{APP_ID}.desktop"
AUTOSTART = _CONFIG_HOME / "autostart" / f"{APP_ID}.desktop"
# Written by versions before 0.1.0, when the project was called control-gestos
_LEGACY = [_DATA_HOME / "applications/control-gestos.desktop",
           _DATA_HOME / "applications/io.github.ignacio_aranda.ControlGestos.desktop",
           _CONFIG_HOME / "autostart/control-gestos.desktop",
           _CONFIG_HOME / "autostart/control-gestos-camara.desktop",
           _CONFIG_HOME / "autostart/io.github.ignacio_aranda.ControlGestos.desktop"]
STATUS_COLORS = {"active": T.SUCCESS, "covered": T.WARNING, "paused": T.WARNING, "off": T.TEXT_3}


def _socket_path():
    # In the user's private runtime dir (/run/user/UID, mode 0700). In /tmp another
    # user could create the socket first and stop the app from starting.
    base = os.environ.get("XDG_RUNTIME_DIR")
    if base and os.path.isdir(base) and os.stat(base).st_uid == os.getuid():
        return os.path.join(base, "handcue.sock")
    private = Path.home() / ".cache" / "handcue"
    private.mkdir(parents=True, exist_ok=True, mode=0o700)
    return str(private / "instance.sock")


SOCKET = _socket_path()


def app_icon():
    return QIcon(str(APP_ICON))


def tray_icon(state):
    """Light glyph, like the other tray icons, with a status dot."""
    size = 64
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    color = "#e8e8ec" if state != "off" else "#8a8a92"
    p.drawPixmap(0, 0, icons.icon("webcam", color).pixmap(size, size))
    r = size * 0.34
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(0, 0, 0, 160))
    p.drawEllipse(QRectF(size - r - 2, size - r - 2, r + 2, r + 2))
    p.setBrush(QColor(STATUS_COLORS[state]))
    p.drawEllipse(QRectF(size - r, size - r, r - 2, r - 2))
    p.end()
    return QIcon(pm)


def _installed_system_wide():
    dirs = os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share"
    return any((Path(d) / "applications" / f"{APP_ID}.desktop").exists() for d in dirs.split(":") if d)


def _command():
    exe = shutil.which("handcue")
    if exe:
        return [exe]
    return [sys.executable, "-m", "handcue"]


def _desktop_entry(args=(), extra=""):
    exec_line = " ".join(shlex.quote(a) for a in [*_command(), *args])
    return ("[Desktop Entry]\n"
            "Type=Application\n"
            f"Name={APP_NAME}\n"
            f"GenericName={_('Gesture control')}\n"
            f"Comment={_('Control your computer with gestures and adjust your webcam')}\n"
            f"Exec={exec_line}\n"
            f"Icon={APP_ICON}\n"
            "Terminal=false\n"
            "Categories=Utility;AudioVideo;Video;\n"
            "Keywords=webcam;camera;gestures;\n" + extra)


def _write_if_changed(path, content):
    if not path.exists() or path.read_text(encoding="utf-8") != content:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    os.chmod(path, 0o644)  # nobody else may change what runs at login


def sync_integration(start_on_login):
    """Creates the menu entry if no package installed one, and turns start on login
    on or off."""
    for f in _LEGACY:
        if f.exists():
            f.unlink()
    if _installed_system_wide():
        if LAUNCHER.exists():
            LAUNCHER.unlink()
    else:
        _write_if_changed(LAUNCHER, _desktop_entry())
    if start_on_login:
        _write_if_changed(AUTOSTART, _desktop_entry(
            ["--background"], "X-GNOME-Autostart-enabled=true\nX-KDE-autostart-after=panel\n"))
    elif AUTOSTART.exists():
        AUTOSTART.unlink()


def notify_running_instance():
    """If the app is already running, asks it to show its window and returns True."""
    s = QLocalSocket()
    s.connectToServer(SOCKET)
    if not s.waitForConnected(300):
        return False
    s.write(b"show")
    s.flush()
    s.waitForBytesWritten(300)
    s.disconnectFromServer()
    return True


def listen_for_instances(on_show, parent=None):
    QLocalServer.removeServer(SOCKET)  # a stale socket may remain after a crash
    server = QLocalServer(parent)
    server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
    server.listen(SOCKET)

    def accept():
        c = server.nextPendingConnection()
        c.readyRead.connect(lambda: (c.readAll(), on_show()))
        c.disconnected.connect(c.deleteLater)
    server.newConnection.connect(accept)
    return server
