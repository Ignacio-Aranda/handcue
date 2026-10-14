"""Gestures the detectors can report, actions a binding can run, and the example
bindings a new user starts with."""
import uuid
from typing import NamedTuple

from .i18n import _


class Gesture(NamedTuple):
    name: str
    category: str
    description: str
    # Events (a swipe, someone walking in) fire once when they happen; the rest
    # are states that have to be held for a while.
    is_event: bool = False


CATEGORIES = {
    "hands": _("Hands"),
    "face": _("Face"),
    "body": _("Body"),
    "faces": _("Faces"),
}

GESTURES = {
    "hand:fist": Gesture(_("Fist"), "hands", _("Closed hand")),
    "hand:open_palm": Gesture(_("Open hand"), "hands", _("All five fingers extended")),
    "hand:pointing_up": Gesture(_("Point up"), "hands", _("Only the index finger raised")),
    "hand:thumb_up": Gesture(_("Thumb up"), "hands", _("Closed fist with the thumb up")),
    "hand:thumb_down": Gesture(_("Thumb down"), "hands", _("Closed fist with the thumb down")),
    "hand:victory": Gesture(_("Victory"), "hands", _("Index and middle fingers in a V")),
    "hand:i_love_you": Gesture(_("I love you"), "hands", _("Thumb, index and little finger")),
    "hand:rock": Gesture(_("Rock"), "hands", _("Index and little finger, thumb tucked in")),
    "hand:call_me": Gesture(_("Call me"), "hands", _("Thumb and little finger")),
    "hand:ok": Gesture(_("OK"), "hands", _("Thumb and index in a circle, other fingers extended")),
    "hand:pinch": Gesture(_("Pinch"), "hands", _("Thumb and index fingertips together")),
    "hand:three": Gesture(_("Three fingers"), "hands", _("Index, middle and ring fingers")),
    "hand:swipe_left": Gesture(_("Swipe left"), "hands", _("Open hand moving quickly"), True),
    "hand:swipe_right": Gesture(_("Swipe right"), "hands", _("Open hand moving quickly"), True),
    "hand:swipe_up": Gesture(_("Swipe up"), "hands", _("Open hand moving quickly"), True),
    "hand:swipe_down": Gesture(_("Swipe down"), "hands", _("Open hand moving quickly"), True),

    "face:smile": Gesture(_("Smile"), "face", _("A clear, wide smile")),
    "face:mouth_open": Gesture(_("Mouth open"), "face", _("Open your mouth wide")),
    "face:wink_left": Gesture(_("Left wink"), "face", _("Close only your left eye")),
    "face:wink_right": Gesture(_("Right wink"), "face", _("Close only your right eye")),
    "face:eyes_closed": Gesture(_("Eyes closed"), "face", _("Both eyes closed (use with 1 s or more)")),
    "face:brows_up": Gesture(_("Eyebrows up"), "face", _("Raise your eyebrows")),
    "face:kiss": Gesture(_("Kiss"), "face", _("Pucker your lips")),
    "face:puff_cheeks": Gesture(_("Puff cheeks"), "face", _("Puff out your cheeks")),
    "face:turn_left": Gesture(_("Turn head left"), "face", _("Look to your left")),
    "face:turn_right": Gesture(_("Turn head right"), "face", _("Look to your right")),
    "face:look_up": Gesture(_("Look up"), "face", _("Tilt your head up")),
    "face:look_down": Gesture(_("Look down"), "face", _("Tilt your head down")),

    "body:present": Gesture(_("Someone there"), "body", _("At least one person in view")),
    "body:several": Gesture(_("Several people"), "body", _("Two or more people in view")),
    "body:arrives": Gesture(_("Someone arrives"), "body", _("Nobody in view, then someone"), True),
    "body:leaves": Gesture(_("Everyone left"), "body",
                           _("Someone in view, then nobody for 2 seconds"), True),
    "body:arms_up": Gesture(_("Arms up"), "body", _("Both wrists above the head")),
    "body:hand_raised": Gesture(_("Hand raised"), "body", _("One wrist above the head")),
    "body:arms_crossed": Gesture(_("Arms in an X"), "body", _("Wrists crossed in front of the chest")),
    "body:t_pose": Gesture(_("T-pose"), "body", _("Arms stretched out horizontally")),

    "recognized:known": Gesture(_("Someone known"), "faces", _("Any registered person")),
    "recognized:unknown": Gesture(_("Someone unknown"), "faces", _("A face that is not registered")),
}
# Gestures for each registered group and person are added by register_people()
# once the face store has been loaded.
RECOGNIZED_PREFIX = "recognized:"
GROUP_PREFIX = "recognized:group:"
PERSON_PREFIX = "recognized:person:"
REMOVED = Gesture(_("Removed item"), "faces", _("This group or person no longer exists"))


def register_people(groups, people):
    for key in [k for k in GESTURES if k.startswith((GROUP_PREFIX, PERSON_PREFIX))]:
        del GESTURES[key]
    for g in groups:
        GESTURES[GROUP_PREFIX + g["id"]] = Gesture(
            _("Someone from {group}").format(group=g["name"]), "faces",
            _("Any person in the group {group}").format(group=g["name"]))
    for p in people:
        GESTURES[PERSON_PREFIX + p["id"]] = Gesture(
            p["name"], "faces", _("When {name} shows up").format(name=p["name"]))


def gesture(gid):
    """Catalog entry for a gesture id, even if it no longer exists."""
    return GESTURES.get(gid, REMOVED)


SIDES = {"any": _("Either hand"), "left": _("Left"), "right": _("Right"), "both": _("Both at once")}


class Action(NamedTuple):
    name: str
    help: str
    suggestions: list | None = None


ACTIONS = {
    "media": Action(_("Media"), _("Controls whatever player is playing, and the volume."),
                    ["play_pause", "next", "previous", "volume_up", "volume_down", "mute"]),
    "app": Action(_("Open app"), _("Program to start, e.g. firefox, dolphin, konsole, code."),
                  ["firefox", "dolphin", "konsole", "kcalc", "spotify", "code", "systemsettings"]),
    "url": Action(_("Open website"), _("Address to open in the browser."),
                  ["https://www.youtube.com", "https://music.youtube.com", "https://www.google.com"]),
    "type": Action(_("Type text"), _("Text typed wherever the cursor is. Use \\n for Enter.")),
    "shortcut": Action(_("Keyboard shortcut"),
                       _("Keys joined with +, e.g. ctrl+c, alt+tab, ctrl+alt+t, super, f5, space, "
                         "enter, left, right."),
                       ["ctrl+c", "ctrl+v", "ctrl+z", "alt+tab", "alt+f4", "super", "ctrl+alt+t", "f5",
                        "space", "right", "left", "ctrl+w", "ctrl+t", "f11"]),
    "command": Action(_("Run command"),
                      _("Shell command (bash). It runs with your permissions every time the gesture is "
                        "made in front of the camera: only use commands you understand and, if other "
                        "people use this computer, turn on “Only obey registered people”.")),
    "sound": Action(_("Sound effect"), _("A synthesized sound."),
                    ["ding", "coin", "laser", "roar", "guitar", "fanfare", "explosion", "horn", "fart"]),
    "notification": Action(_("Notification"), _("Text of the desktop notification.")),
    "photo": Action(_("Take photo"), _("Countdown in seconds before the photo is taken."), ["3", "0", "5"]),
    "screenshot": Action(_("Screenshot"), _("Saved next to the photos.")),
    "lock": Action(_("Lock screen"), _("Locks the session.")),
    "mouse": Action(_("Virtual mouse"),
                    _("Move the pointer with your hand. Pinch index and thumb to click, middle finger "
                      "and thumb to right-click.")),
    "pause": Action(_("Pause gestures"), _("While paused, only the pause gesture keeps working.")),
    "effects": Action(_("Visual effects"), _("Effects on your hands in the preview (fire, laser...).")),
}
# Handled by the engine itself rather than the action executor.
INTERNAL_ACTIONS = {"photo", "mouse", "pause", "effects"}
NO_VALUE_ACTIONS = {"screenshot", "lock", "mouse", "pause", "effects"}


def new_binding(gesture, action, value="", side="any", hold=0.5, cooldown=1.5, repeat=False,
                enabled=True, name=""):
    return {"id": uuid.uuid4().hex[:8], "name": name, "enabled": enabled, "gesture": gesture,
            "side": side, "hold": hold, "cooldown": cooldown, "repeat": repeat,
            "action": action, "value": value}


def default_bindings():
    b = new_binding
    return [
        b("hand:thumb_up", "media", "play_pause", hold=0.6, name=_("Play / pause")),
        b("hand:swipe_right", "media", "next", name=_("Next track")),
        b("hand:swipe_left", "media", "previous", name=_("Previous track")),
        b("hand:pointing_up", "media", "volume_up", hold=0.8, cooldown=0.4, repeat=True,
          name=_("Volume up (hold)")),
        b("hand:thumb_down", "media", "volume_down", hold=0.8, cooldown=0.4, repeat=True,
          name=_("Volume down (hold)")),
        b("hand:victory", "photo", "3", hold=1.0, cooldown=5, name=_("Selfie with countdown")),
        b("hand:ok", "sound", "coin", hold=0.4, name=_("Coin")),
        b("hand:rock", "sound", "guitar", hold=0.4, name=_("Power chord")),
        b("hand:pinch", "effects", "", side="both", hold=1.0, name=_("Toggle effects")),
        b("hand:open_palm", "pause", "", side="both", hold=1.5, cooldown=3, name=_("Pause / resume")),
        b("face:smile", "notification", _("Nice smile!"), hold=1.5, cooldown=10, name=_("Compliment")),
        b("face:mouth_open", "sound", "roar", hold=0.8, cooldown=3, name=_("Roar")),
        b("face:puff_cheeks", "sound", "fart", hold=0.8, cooldown=3, name=_("Prank")),
        b("body:arms_up", "sound", "fanfare", hold=0.8, cooldown=4, name=_("Victory!")),
        # Off by default: these act on the desktop and are worth trying out first.
        b("hand:three", "mouse", "", hold=1.0, cooldown=2, enabled=False, name=_("Virtual mouse")),
        b("hand:i_love_you", "type", _("I love you!"), hold=1.0, cooldown=3, enabled=False,
          name=_("Type a message")),
        b("hand:call_me", "url", "https://www.youtube.com", hold=1.0, cooldown=5, enabled=False,
          name=_("Open YouTube")),
        b("face:wink_left", "shortcut", "alt+tab", hold=0.4, enabled=False, name=_("Switch window")),
        b("face:brows_up", "screenshot", "", hold=1.0, cooldown=5, enabled=False, name=_("Screenshot")),
        b("hand:fist", "lock", "", side="both", hold=2.0, cooldown=10, enabled=False,
          name=_("Lock screen")),
        b("body:leaves", "lock", "", cooldown=30, enabled=False, name=_("Lock when I leave")),
        b("body:arrives", "notification", _("Welcome back!"), cooldown=30, enabled=False,
          name=_("Greeting")),
        b("hand:call_me", "app", "konsole", side="left", hold=1.0, cooldown=5, enabled=False,
          name=_("Open terminal")),
    ]
