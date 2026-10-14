"""Material Design Icons through QtAwesome. One icon set for the whole UI so every
glyph has the same stroke and weight."""
import qtawesome as qta

from ..catalog import GROUP_PREFIX, RECOGNIZED_PREFIX
from . import theme as T

GESTURES = {
    "hand:fist": "boxing-glove", "hand:open_palm": "hand-back-right-outline",
    "hand:pointing_up": "hand-pointing-up", "hand:thumb_up": "thumb-up-outline",
    "hand:thumb_down": "thumb-down-outline", "hand:victory": "hand-peace",
    "hand:i_love_you": "hand-heart-outline", "hand:rock": "guitar-electric",
    "hand:call_me": "phone-outline", "hand:ok": "hand-okay", "hand:pinch": "gesture-pinch",
    "hand:three": "numeric-3-circle-outline", "hand:swipe_left": "gesture-swipe-left",
    "hand:swipe_right": "gesture-swipe-right", "hand:swipe_up": "gesture-swipe-up",
    "hand:swipe_down": "gesture-swipe-down",
    "face:smile": "emoticon-happy-outline", "face:mouth_open": "emoticon-excited-outline",
    "face:wink_left": "emoticon-wink-outline", "face:wink_right": "emoticon-wink-outline",
    "face:eyes_closed": "eye-off-outline", "face:brows_up": "emoticon-neutral-outline",
    "face:kiss": "emoticon-kiss-outline", "face:puff_cheeks": "emoticon-outline",
    "face:turn_left": "rotate-left", "face:turn_right": "rotate-right",
    "face:look_up": "arrow-up-circle-outline", "face:look_down": "arrow-down-circle-outline",
    "body:present": "account-outline", "body:several": "account-multiple-outline",
    "body:arrives": "account-arrow-right-outline", "body:leaves": "account-arrow-left-outline",
    "body:arms_up": "human-handsup", "body:hand_raised": "human-greeting-variant",
    "body:arms_crossed": "close-circle-outline", "body:t_pose": "human-male",
    "recognized:known": "account-check-outline", "recognized:unknown": "account-question-outline",
}
ACTIONS = {
    "media": "play-pause", "app": "application-outline", "url": "web", "type": "keyboard-outline",
    "shortcut": "apple-keyboard-command", "command": "console", "sound": "volume-high",
    "notification": "bell-outline", "photo": "camera-outline", "screenshot": "monitor-screenshot",
    "lock": "lock-outline", "mouse": "cursor-default-outline", "pause": "pause-circle-outline",
    "effects": "auto-fix",
}
CATEGORIES = {"hands": "hand-back-right-outline", "face": "face-recognition", "body": "human",
              "faces": "account-group-outline"}


def icon(name, color=None, **kw):
    """MDI icon using the theme colors for its normal, active and disabled states."""
    options = dict(color=color or T.TEXT_2, color_active=color or T.TEXT, color_disabled=T.TEXT_3)
    options.update(kw)
    return qta.icon(f"mdi6.{name}", **options)


def toggle_icon(name):
    """For checkable buttons: gray when off, accent color when on."""
    return qta.icon(f"mdi6.{name}", color=T.TEXT_2, color_active=T.TEXT, color_on=T.ACCENT,
                    color_on_active=T.ACCENT_HOVER, color_disabled=T.TEXT_3)


def gesture_icon(gid, color=None, **kw):
    name = GESTURES.get(gid)
    if name is None and gid.startswith(RECOGNIZED_PREFIX):
        name = "account-group-outline" if gid.startswith(GROUP_PREFIX) else "account-outline"
    return icon(name or "gesture", color, **kw)


def action_icon(kind, color=None, **kw):
    return icon(ACTIONS.get(kind, "flash-outline"), color, **kw)
