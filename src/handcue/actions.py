"""Runs the actions bound to gestures: apps, websites, media keys, typing,
notifications, screenshots..."""
import html
import shlex
import shutil
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from urllib.parse import urlsplit

from jeepney import DBusAddress, new_method_call
from jeepney.bus_messages import message_bus
from jeepney.io.blocking import open_dbus_connection

from . import APP_NAME, sounds
from .config import photo_folder
from .desktop_input import call, parse_shortcut
from .i18n import _
from .process import spawn

NOTIFICATIONS = DBusAddress("/org/freedesktop/Notifications", bus_name="org.freedesktop.Notifications",
                            interface="org.freedesktop.Notifications")
WEB_SCHEMES = {"http", "https"}  # "Open website" must not open local files or other handlers
MAX_PENDING = 8                  # actions queued at most; extra ones are dropped


def normalize_url(value):
    """URL to open, or ValueError if it is not an http(s) address."""
    value = value.strip()
    if "://" not in value:
        value = "https://" + value
    parts = urlsplit(value)
    try:
        valid = parts.scheme.lower() in WEB_SCHEMES and bool(parts.hostname) and (parts.port or 0) >= 0
    except ValueError:  # e.g. "javascript:alert(1)" read as host "javascript", port "alert(1)"
        valid = False
    if not valid:
        raise ValueError(_("Only web addresses can be opened (http:// or https://)"))
    return value


def notify(title, body=""):
    conn = open_dbus_connection(bus="SESSION")
    try:
        # Notification servers render a subset of HTML in the body.
        call(conn, new_method_call(NOTIFICATIONS, "Notify", "susssasa{sv}i",
                                   (APP_NAME, 0, "camera-web", title, html.escape(body), [], {}, 4000)))
    finally:
        conn.close()


def mpris(method):
    """Calls PlayPause/Next/Previous on the player that is playing (or the first one)."""
    conn = open_dbus_connection(bus="SESSION")
    try:
        names = call(conn, message_bus.ListNames())[0]
        players = [n for n in names if n.startswith("org.mpris.MediaPlayer2.")]
        if not players:
            raise RuntimeError(_("No media player is open"))
        chosen = players[0]
        for name in players:
            props = DBusAddress("/org/mpris/MediaPlayer2", bus_name=name,
                                interface="org.freedesktop.DBus.Properties")
            try:
                status = call(conn, new_method_call(props, "Get", "ss", (
                    "org.mpris.MediaPlayer2.Player", "PlaybackStatus")))[0][1]
            except Exception:  # noqa: BLE001 - a player that does not answer is skipped
                continue
            if status == "Playing":
                chosen = name
                break
        player = DBusAddress("/org/mpris/MediaPlayer2", bus_name=chosen,
                             interface="org.mpris.MediaPlayer2.Player")
        call(conn, new_method_call(player, method))
        return chosen.removeprefix("org.mpris.MediaPlayer2.")
    finally:
        conn.close()


class Executor:
    """Runs external actions on worker threads so the camera loop never waits.
    Photo, mouse, pause and effects are handled by the engine."""

    def __init__(self, input_, log, get_config):
        self.input = input_
        self.log = log
        self.get_config = get_config
        self.pool = ThreadPoolExecutor(max_workers=3)
        self._pending = 0
        self._lock = threading.Lock()

    def run(self, action, value, name=""):
        with self._lock:
            if self._pending >= MAX_PENDING:
                self.log(_("Too many actions in a row, skipping “{name}”").format(name=name or action),
                         error=True)
                return
            self._pending += 1
        self.pool.submit(self._run_safely, action, value, name)

    def _run_safely(self, action, value, name):
        try:
            self._run(action, value)
        except Exception as e:  # noqa: BLE001 - shown in the activity log
            self.log(_("Could not complete “{name}”: {error}").format(name=name or action, error=e),
                     error=True)
        finally:
            with self._lock:
                self._pending -= 1

    def _run(self, action, value):
        v = (value or "").strip()
        if action == "media":
            volume = {"volume_up": "5%+", "volume_down": "5%-"}
            if v in volume:
                subprocess.run(["wpctl", "set-volume", "-l", "1.0", "@DEFAULT_AUDIO_SINK@", volume[v]],
                               check=True, timeout=3)
            elif v == "mute":
                subprocess.run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "toggle"], check=True, timeout=3)
            else:
                method = {"play_pause": "PlayPause", "next": "Next", "previous": "Previous"}.get(v)
                if not method:
                    raise ValueError(f"unknown media action: {v}")
                mpris(method)
        elif action == "app":
            try:
                spawn(shlex.split(v))
            except FileNotFoundError:
                if not shutil.which("gtk-launch"):
                    raise
                spawn(["gtk-launch", v])  # a .desktop file id
        elif action == "url":
            spawn(["xdg-open", normalize_url(v)])
        elif action == "command":
            spawn(["bash", "-c", v])
        elif action == "type":
            self.input.type(v.replace("\\n", "\n"))
        elif action == "shortcut":
            self.input.combo(parse_shortcut(v))
        elif action == "sound":
            sounds.play(v)
        elif action == "notification":
            notify(v or _("Gesture detected"))
        elif action == "screenshot":
            folder = photo_folder(self.get_config())
            folder.mkdir(parents=True, exist_ok=True, mode=0o700)
            path = folder / f"screenshot_{datetime.now():%Y%m%d_%H%M%S}.png"
            if shutil.which("spectacle"):
                cmd = ["spectacle", "-b", "-n", "-f", "-o", str(path)]
            elif shutil.which("gnome-screenshot"):
                cmd = ["gnome-screenshot", "-f", str(path)]
            else:
                raise RuntimeError(_("No screenshot tool found (spectacle or gnome-screenshot)"))
            subprocess.run(cmd, check=True, timeout=15)
            if path.exists():
                path.chmod(0o600)
        elif action == "lock":
            subprocess.run(["loginctl", "lock-session"], check=True, timeout=5)
        else:
            raise ValueError(f"unknown action: {action}")

    def close(self):
        self.pool.shutdown(wait=False, cancel_futures=True)
