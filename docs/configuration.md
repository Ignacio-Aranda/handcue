# Configuration file

Everything can be changed from the app; this page is for people who want to read or edit
the file by hand, or back it up.

The settings are in `~/.config/handcue/config.json` (or `$XDG_CONFIG_HOME/...`). The
app rewrites the file whenever something changes, so close it before editing. Unknown keys
are ignored and missing ones take their default value.

Settings files written before 0.1.0 used Spanish key names. They are converted automatically
the first time a newer version starts.

## Top-level keys

| Key | Default | Meaning |
|---|---|---|
| `version` | `2` | Format version, used for migrations |
| `camera` | `{"index": 0, "width": 1280, "height": 720, "fps": 30}` | Which `/dev/videoN` to open and the capture format |
| `camera_controls` | `{}` | V4L2 control values written to the camera on start, e.g. `{"focus_absolute": 40}` |
| `camera_profiles` | `{}` | Your saved profiles: `{"name": {control: value}}` |
| `auto_framing` | `false` | Follow your face with digital zoom, pan and tilt |
| `gestures_enabled` | `true` | Master switch for gesture bindings |
| `pause_when_covered` | `true` | Pause detection while the privacy shutter is closed |
| `security.known_people_only` | `false` | Only run gesture bindings while a registered person is in view |
| `recognition.enabled` | `false` | Face recognition on or off |
| `recognition.threshold` | `0.40` | Minimum cosine similarity to accept a face (0.25 to 0.70) |
| `recognition.confirmations` | `3` | Matching votes needed before deciding who someone is (1, 3 or 5) |
| `virtual_camera` | see below | Virtual camera output |
| `start_on_login` | `true` | Create the autostart entry |
| `detectors` | `{"hands": true, "face": false, "body": false}` | Which detectors run |
| `view` | `mirror`, `grid`, `histogram`, `zebra`, `overlay`, `effects` | Preview options |
| `max_hands`, `max_people` | `2`, `3` | How many hands and bodies are tracked at once |
| `thresholds` | see `config.py` | Sensitivity per gesture family, 0 to 1 |
| `mouse` | `{"hand": "right", "speed": 1.5, "smoothing": 0.5}` | Virtual mouse |
| `portal_token` | `""` | Restore token from the RemoteDesktop portal. Keep it private |
| `photo_folder` | `""` | Empty means `Pictures/Gestures` (translated) |
| `bindings` | examples | The list of bindings, see below |

### `virtual_camera`

| Key | Values |
|---|---|
| `enabled` | `true` / `false` |
| `background` | `none`, `blur`, `color`, `image` |
| `blur` | 6 to 80 |
| `color` | `#rrggbb` |
| `image` | path to an image file |
| `mirror` | `true` / `false` |
| `resolution` | `720` or `1080` |

## Bindings

Each binding links a gesture to an action:

```json
{
  "id": "3f9c2a1b",
  "name": "Next track",
  "enabled": true,
  "gesture": "hand:swipe_right",
  "side": "any",
  "hold": 0.5,
  "cooldown": 1.5,
  "repeat": false,
  "action": "media",
  "value": "next"
}
```

| Field | Meaning |
|---|---|
| `id` | Random identifier |
| `name` | Optional label shown in the list |
| `gesture` | A gesture id (below) |
| `side` | Hand gestures only: `any`, `left`, `right` or `both` |
| `hold` | Seconds the gesture must be held (0 = instant). Ignored for events such as swipes |
| `cooldown` | Minimum seconds between two firings. Raised to 0.2 s with `repeat` and to 1 s for actions that start programs |
| `repeat` | Keep firing while the gesture is held |
| `action`, `value` | What to do, below |

### Gesture ids

- Hands: `hand:fist`, `hand:open_palm`, `hand:pointing_up`, `hand:thumb_up`,
  `hand:thumb_down`, `hand:victory`, `hand:i_love_you`, `hand:rock`, `hand:call_me`,
  `hand:ok`, `hand:pinch`, `hand:three`, `hand:swipe_left`, `hand:swipe_right`,
  `hand:swipe_up`, `hand:swipe_down`
- Face: `face:smile`, `face:mouth_open`, `face:wink_left`, `face:wink_right`,
  `face:eyes_closed`, `face:brows_up`, `face:kiss`, `face:puff_cheeks`, `face:turn_left`,
  `face:turn_right`, `face:look_up`, `face:look_down`
- Body: `body:present`, `body:several`, `body:arrives`, `body:leaves`, `body:arms_up`,
  `body:hand_raised`, `body:arms_crossed`, `body:t_pose`
- Face recognition: `recognized:known`, `recognized:unknown`, `recognized:group:<id>`,
  `recognized:person:<id>`

### Actions

| `action` | `value` |
|---|---|
| `media` | `play_pause`, `next`, `previous`, `volume_up`, `volume_down`, `mute` |
| `app` | A command (`firefox`) or a desktop file id (`org.kde.dolphin`) |
| `url` | An `http` or `https` address |
| `type` | Text to type; `\n` presses Enter |
| `shortcut` | Keys joined with `+`, e.g. `ctrl+alt+t`, `super`, `alt+f4` |
| `command` | A shell command, run with `bash -c` |
| `sound` | `ding`, `coin`, `laser`, `roar`, `guitar`, `fanfare`, `explosion`, `horn`, `fart` |
| `notification` | Notification text |
| `photo` | Countdown in seconds |
| `screenshot`, `lock`, `mouse`, `pause`, `effects` | No value |

Key names for `shortcut`: `ctrl`, `shift`, `alt`, `altgr`, `super`, `enter`, `tab`, `esc`,
`space`, `backspace`, `delete`, `insert`, `home`, `end`, `pageup`, `pagedown`, `up`, `down`,
`left`, `right`, `print`, `menu`, `f1` to `f12`, the media keys `play`, `next`, `previous`,
`volume_up`, `volume_down`, `mute`, and any single character.
