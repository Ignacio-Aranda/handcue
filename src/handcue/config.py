"""User settings: where they live, their defaults, and loading/saving them."""
import copy
import json
import os
import subprocess
from pathlib import Path

from . import migrations
from .catalog import ACTIONS, GESTURES, RECOGNIZED_PREFIX, default_bindings
from .i18n import _

_CONFIG_HOME = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
_DATA_HOME = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share")
_CACHE_HOME = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
CONFIG_DIR = _CONFIG_HOME / "handcue"
DATA_DIR = _DATA_HOME / "handcue"
CACHE_DIR = _CACHE_HOME / "handcue"
# The project was called "control-gestos" before 0.1.0.
LEGACY_DIRS = [(_CONFIG_HOME / "control-gestos", CONFIG_DIR), (_DATA_HOME / "control-gestos", DATA_DIR),
               (_CACHE_HOME / "control-gestos", CACHE_DIR)]
CONFIG_FILE = CONFIG_DIR / "config.json"

VERSION = 2
DEFAULTS = {
    "version": VERSION,
    "camera": {"index": 0, "width": 1280, "height": 720, "fps": 30},
    # V4L2 control values ({control: value}), written to the camera when it opens.
    "camera_controls": {},
    "camera_profiles": {},
    "auto_framing": False,
    "gestures_enabled": True,
    "pause_when_covered": True,
    # Anyone in front of the camera can trigger bindings unless this is on.
    "security": {"known_people_only": False},
    "recognition": {"enabled": False, "threshold": 0.40, "confirmations": 3},
    "virtual_camera": {"enabled": False, "background": "none", "blur": 30, "color": "#1b1c20",
                       "image": "", "mirror": False, "resolution": 720},
    "start_on_login": True,
    "tray_notice_shown": False,
    "detectors": {"hands": True, "face": False, "body": False},
    "view": {"mirror": True, "grid": False, "histogram": False, "zebra": False, "overlay": True,
             "effects": False},
    "max_hands": 2,
    "max_people": 3,
    "thresholds": {
        "smile": 0.55, "mouth_open": 0.45, "wink": 0.5, "brows": 0.55, "kiss": 0.7, "cheeks": 0.45,
        "head_turn": 0.12, "head_tilt": 0.12, "swipe": 0.22, "hand_confidence": 0.55,
    },
    "mouse": {"hand": "right", "speed": 1.5, "smoothing": 0.5},
    # Restore token for the RemoteDesktop portal (keyboard and pointer permission).
    "portal_token": "",
    "photo_folder": "",
    "bindings": None,  # None until the user has their own: the examples are used
}


def move_legacy_dirs():
    """Moves data from the directories used before the project was renamed."""
    for old, new in LEGACY_DIRS:
        if old.is_dir() and not new.exists():
            os.replace(old, new)


def _merge(base, extra):
    for k, v in extra.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _merge(base[k], v)
        else:
            base[k] = v
    return base


def load(path=CONFIG_FILE):
    cfg = copy.deepcopy(DEFAULTS)
    migrated = False
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("not a JSON object")
            data, migrated = migrations.migrate_config(data)
            _merge(cfg, data)
        except (OSError, ValueError) as e:
            print(f"Could not read {path}: {e}. Using the default settings.")
    if cfg["bindings"] is None:
        cfg["bindings"] = default_bindings()
    # Drop bindings for gestures or actions that no longer exist. Face recognition
    # gestures are checked later, once the face store is loaded.
    cfg["bindings"] = [b for b in cfg["bindings"]
                       if isinstance(b, dict) and b.get("action") in ACTIONS
                       and (b.get("gesture") in GESTURES or str(b.get("gesture")).startswith(RECOGNIZED_PREFIX))]
    cfg["version"] = VERSION
    if migrated:
        save(cfg, path)
    return cfg


def save(cfg, path=CONFIG_FILE):
    # Private and atomic: the file holds the portal token and commands the app runs.
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.chmod(tmp, 0o600)  # in case a stale .tmp existed with other permissions
    os.replace(tmp, path)


def photo_folder(cfg):
    if cfg.get("photo_folder"):
        return Path(cfg["photo_folder"]).expanduser()
    try:
        base = subprocess.run(["xdg-user-dir", "PICTURES"], capture_output=True, text=True,
                              timeout=2).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        base = ""
    return Path(base or Path.home() / "Pictures") / _("Gestures")
