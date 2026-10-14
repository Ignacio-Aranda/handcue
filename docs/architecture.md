# Architecture

HandCue is a single Python process with a Qt user interface, one capture thread and a
small pool of worker threads for actions.

```
webcam ──▶ engine (capture thread)
             ├─ cover check (privacy shutter)
             ├─ detection: MediaPipe hands, face, body ──▶ signals and events
             ├─ recognition: YuNet + SFace ──────────────▶ recognized:* signals
             ├─ triggers: hold, cooldown, repeat ────────▶ bindings to fire
             │     ├─ photo, pause, mouse, effects: handled in the engine
             │     └─ the rest ──▶ action workers ──▶ apps, URLs, media, keyboard and mouse
             ├─ virtual camera ──▶ /dev/videoN (v4l2loopback)
             └─ preview image ──▶ UI thread
```

## Threads

**UI thread** (`ui/`). Owns the settings dictionary and every widget. When a setting changes
it sends a deep copy to the engine (`Engine.set_config`) and saves the file 300 ms later, so
dragging a slider does not write to disk on every step.

**Capture thread** (`engine.Engine`, a `QThread`). Reads frames, runs the detectors, decides
which bindings fire and draws the preview. It never blocks on actions: anything external goes
to the executor. It talks back to the UI only through Qt signals (`frame_ready`, `status`,
`message`...), which Qt delivers on the UI thread.

**Action workers** (`actions.Executor`, three threads). Run media commands, start programs,
send notifications and drive the RemoteDesktop portal. The queue is capped at eight pending
actions; extra ones are dropped with a message. Workers report back through a queue that the
UI drains every 100 ms.

## A frame, step by step

1. OpenCV reads an MJPG frame from `/dev/videoN`.
2. `CoverDetector` checks whether the image is flat and dark (privacy shutter closed). If so,
   detection pauses until the camera is uncovered.
3. The frame is mirrored and passed to MediaPipe. Hands run on every frame; face and body
   alternate when both are on.
4. `detection.py` turns landmarks into *signals* (gestures active now, with the hand side)
   and *events* (swipes, someone arriving or leaving).
5. Face recognition runs on the unmirrored frame every third frame (or every frame in
   "instant" mode) and adds `recognized:*` signals.
6. If "only obey registered people" is on and nobody known is in view, only face recognition
   bindings are evaluated.
7. `TriggerState.evaluate` tracks how long each gesture has been held and returns the
   bindings to fire. Internal actions run in the engine; the rest go to the executor.
8. If the virtual camera is on, the clean frame (with the chosen background) is written to
   the loopback device.
9. The preview is drawn (landmarks, labels, progress ring, histogram...) and sent to the UI
   if the window is visible.

## Modules

| Module | Responsibility |
|---|---|
| `app.py` | Command line, Qt application setup, single instance check |
| `catalog.py` | Gestures, actions and the example bindings |
| `config.py` | Settings file, defaults, XDG paths |
| `migrations.py` | Upgrades settings and face data written by older versions |
| `engine.py` | Capture loop, auto framing, virtual mouse, preview drawing |
| `detection.py` | MediaPipe models and the rules for each gesture |
| `triggers.py` | Hold time, cooldown, repeat and grace period per binding |
| `actions.py` | Executes actions on worker threads |
| `desktop_input.py` | Keyboard and pointer through the RemoteDesktop portal |
| `recognition.py` | Face detection, embeddings, tracking and voting |
| `faces.py` | Encrypted storage of people and groups |
| `models.py` | Downloads and verifies the ML models |
| `camera.py` | V4L2 controls, formats, profiles and digital framing |
| `virtual_camera.py` | v4l2loopback output and background segmentation |
| `effects.py` | Particle effects drawn on the hands |
| `sounds.py` | Synthesized sound effects |
| `desktop.py` | Tray icon, menu entry, autostart, single instance socket |
| `i18n.py` | gettext setup |
| `ui/` | Main window, panels, dialogs and widgets |

## Where data lives

| Path | Content |
|---|---|
| `$XDG_CONFIG_HOME/handcue/config.json` | Settings and bindings (0600) |
| `$XDG_DATA_HOME/handcue/faces.enc` | People, groups and samples, encrypted (0600) |
| `$XDG_DATA_HOME/handcue/key` | Only when there is no keyring: the face data key (0600) |
| `$XDG_CACHE_HOME/handcue/models` | Downloaded ML models |
| `$XDG_CACHE_HOME/handcue/sounds` | Rendered sound effects |
| `$XDG_RUNTIME_DIR/handcue.sock` | Single instance socket |
| `$XDG_PICTURES_DIR/Gestures` (translated) | Photos and screenshots (0600) |
| `~/.config/autostart/<app id>.desktop` | Start on login |

## External interfaces

- **V4L2** ioctls on `/dev/videoN` for camera controls, through `fcntl` without extra
  libraries.
- **D-Bus**: `org.freedesktop.portal.RemoteDesktop` (keyboard and pointer),
  `org.mpris.MediaPlayer2.*` (media), `org.freedesktop.Notifications`, logind
  `PrepareForSleep` (reapply camera settings after resume), Secret Service (keyring).
- **Programs**: `wpctl` (volume), `xdg-open` (websites), `gtk-launch` (apps by desktop id),
  `spectacle` or `gnome-screenshot`, `loginctl lock-session`, `pw-play`/`paplay`/`aplay`.
- **Network**: HTTPS downloads of the models, nothing else.
