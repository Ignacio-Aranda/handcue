"""Virtual keyboard and pointer through the xdg-desktop-portal RemoteDesktop API.

Works on Wayland (KDE, GNOME) without root. The desktop asks for permission the
first time; afterwards a restore token lets us reconnect without asking again.
"""
import threading
import time
import uuid

from jeepney import DBusAddress, MatchRule, new_method_call
from jeepney.bus_messages import message_bus
from jeepney.io.blocking import open_dbus_connection
from jeepney.wrappers import unwrap_msg

from .i18n import _

PORTAL = DBusAddress("/org/freedesktop/portal/desktop", bus_name="org.freedesktop.portal.Desktop",
                     interface="org.freedesktop.portal.RemoteDesktop")

# Key names to X11 keysyms. The portal takes keysyms, so the result does not depend
# on the keyboard layout.
KEYS = {
    "ctrl": 0xffe3, "control": 0xffe3, "shift": 0xffe1, "alt": 0xffe9, "altgr": 0xfe03,
    "super": 0xffeb, "meta": 0xffeb, "win": 0xffeb,
    "enter": 0xff0d, "return": 0xff0d, "tab": 0xff09, "esc": 0xff1b, "escape": 0xff1b,
    "space": 0x20, "backspace": 0xff08, "delete": 0xffff, "del": 0xffff, "insert": 0xff63,
    "home": 0xff50, "end": 0xff57, "pageup": 0xff55, "pagedown": 0xff56,
    "up": 0xff52, "down": 0xff54, "left": 0xff51, "right": 0xff53, "print": 0xff61, "menu": 0xff67,
    "play": 0x1008ff14, "next": 0x1008ff17, "previous": 0x1008ff16,
    "volume_up": 0x1008ff13, "volume_down": 0x1008ff11, "mute": 0x1008ff12,
}
KEYS.update({f"f{i}": 0xffbe + i - 1 for i in range(1, 13)})
BTN_LEFT, BTN_RIGHT = 0x110, 0x111  # evdev button codes


def keysym(c):
    if c == "\n":
        return KEYS["enter"]
    if c == "\t":
        return KEYS["tab"]
    o = ord(c)
    return o if 0x20 <= o <= 0x7e or 0xa0 <= o <= 0xff else 0x01000000 + o


def parse_shortcut(text):
    keys = []
    for part in text.lower().replace(" ", "").split("+"):
        if not part:
            continue
        if part in KEYS:
            keys.append(KEYS[part])
        elif len(part) == 1:
            keys.append(keysym(part))
        else:
            raise ValueError(_("Unknown key: '{key}'").format(key=part))
    if not keys:
        raise ValueError(_("Empty shortcut"))
    return keys


def call(conn, msg, timeout=3):
    return unwrap_msg(conn.send_and_get_reply(msg, timeout=timeout))


class PortalInput:
    def __init__(self, token, on_new_token, log):
        self.token = token
        self.on_new_token = on_new_token
        self.log = log
        self.conn = None
        self.session = None
        self.lock = threading.RLock()

    @property
    def connected(self):
        return self.session is not None

    def _request(self, method, signature, args, options, timeout=180):
        """Calls a portal method that answers through a Request.Response signal."""
        token = "cg" + uuid.uuid4().hex[:8]
        sender = self.conn.unique_name[1:].replace(".", "_")
        path = f"/org/freedesktop/portal/desktop/request/{sender}/{token}"
        rule = MatchRule(type="signal", interface="org.freedesktop.portal.Request",
                         member="Response", path=path)
        call(self.conn, message_bus.AddMatch(rule))
        with self.conn.filter(rule) as queue:
            call(self.conn, new_method_call(PORTAL, method, signature,
                                            (*args, dict(options, handle_token=("s", token)))))
            signal = self.conn.recv_until_filtered(queue, timeout=timeout)
        code, results = signal.body
        if code != 0:
            raise RuntimeError(_("Permission denied or cancelled") if code == 1 else f"{method} failed")
        return results

    def connect(self):
        """Blocks until the user answers the permission dialog (or the saved token works)."""
        with self.lock:
            if self.connected:
                return True
            try:
                self.conn = open_dbus_connection(bus="SESSION")
                res = self._request("CreateSession", "a{sv}", (),
                                    {"session_handle_token": ("s", "cg" + uuid.uuid4().hex[:8])})
                session = res["session_handle"][1]
                options = {"types": ("u", 3), "persist_mode": ("u", 2)}  # keyboard + pointer, persistent
                if self.token:
                    options["restore_token"] = ("s", self.token)
                self._request("SelectDevices", "oa{sv}", (session,), options)
                res = self._request("Start", "osa{sv}", (session, ""), {})
                if "restore_token" in res:
                    self.token = res["restore_token"][1]
                    self.on_new_token(self.token)
                self.session = session
                self.log(_("Virtual keyboard and mouse connected"))
                return True
            except Exception as e:  # noqa: BLE001 - any D-Bus failure is reported the same way
                self.log(_("Could not connect the virtual keyboard and mouse: {error}").format(error=e), error=True)
                self.disconnect()
                return False

    def disconnect(self):
        with self.lock:
            if self.conn:
                try:
                    self.conn.close()
                except OSError:
                    pass
            self.conn = self.session = None

    def _notify(self, method, signature, *args):
        with self.lock:
            if not self.connected and not self.connect():
                raise RuntimeError(_("The virtual keyboard and mouse are not connected (see Preferences)"))
            try:
                call(self.conn, new_method_call(PORTAL, method, signature, (self.session, {}, *args)))
            except Exception:
                self.disconnect()  # session closed, e.g. permission revoked
                raise

    def key(self, sym, pressed):
        self._notify("NotifyKeyboardKeysym", "oa{sv}iu", sym, 1 if pressed else 0)

    def combo(self, syms):
        for k in syms:
            self.key(k, True)
            time.sleep(0.01)
        for k in reversed(syms):
            self.key(k, False)
            time.sleep(0.01)

    def type(self, text):
        for c in text:
            k = keysym(c)
            self.key(k, True)
            self.key(k, False)
            time.sleep(0.008)

    def move(self, dx, dy):
        self._notify("NotifyPointerMotion", "oa{sv}dd", float(dx), float(dy))

    def button(self, button, pressed):
        self._notify("NotifyPointerButton", "oa{sv}iu", button, 1 if pressed else 0)
