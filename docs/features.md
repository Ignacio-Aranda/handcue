# Features

What is implemented as of 0.1.0. Planned work is in [ROADMAP.md](../ROADMAP.md).

## Gestures

- [x] 16 hand gestures: fist, open hand, point up, thumb up/down, victory, I love you, rock,
      call me, OK, pinch, three fingers, and swipes in four directions
- [x] Left, right, either or both hands per binding
- [x] 12 face gestures from MediaPipe blendshapes: smile, mouth open, left/right wink, eyes
      closed, eyebrows up, kiss, puffed cheeks, head turn left/right, look up/down
- [x] 8 body gestures: someone present, several people, someone arrives, everyone left,
      arms up, hand raised, arms crossed, T-pose
- [x] Per-binding hold time ("instant" allowed), cooldown and repeat-while-held
- [x] Grace period so a single misread frame does not release a held gesture
- [x] Progress ring in the preview while a gesture is being held
- [x] Adjustable sensitivity for every gesture family
- [x] Face and body detection alternate frames when both are on, to keep the frame rate up

## Actions

- [x] Media: play/pause, next, previous (MPRIS, whichever player is playing), volume and mute
      (PipeWire `wpctl`)
- [x] Open an application (`.desktop` list or a command) or a website (http/https only)
- [x] Keyboard shortcuts and typing text through the RemoteDesktop portal (layout independent)
- [x] Virtual mouse: move with the hand, pinch to click, middle finger to right-click
- [x] Run a shell command
- [x] Desktop notification, synthesized sound effects
- [x] Photo with countdown, screenshot (Spectacle or GNOME Screenshot), lock screen
- [x] Pause all gestures, toggle hand effects
- [x] "Try it" button to test an action from the editor

## Face recognition

- [x] YuNet detection and SFace embeddings, no training required
- [x] People with samples captured from the camera or imported from photos
- [x] Groups with colors; bindings for a person, a group, anyone known or anyone unknown
- [x] Tracking and voting across frames, configurable strictness and confirmation speed
- [x] "Only obey registered people" mode for every gesture
- [x] Encrypted storage (AES-256-GCM, key in the desktop keyring, file fallback)

## Webcam

- [x] All V4L2 controls the camera exposes, with friendly sections for exposure, color,
      image, zoom and framing, focus and anti-flicker
- [x] Digital framing map and automatic face tracking (cameras with zoom/pan/tilt)
- [x] Resolution and frame rate
- [x] Built-in profiles (natural, vivid, low light, warm, cool, backlight, black and white)
      and user profiles
- [x] Settings restored when the app starts, after the camera reconnects and after suspend
- [x] Preview tools: mirror, rule-of-thirds grid, histogram, zebra, overlay
- [x] Privacy shutter detection that pauses recognition

## Virtual camera

- [x] Output to a v4l2loopback device as YUYV at 720p or 1080p
- [x] Background blur, solid color or image (MediaPipe selfie segmenter)
- [x] Optional mirroring
- [x] Install script for Debian, Ubuntu, Fedora, Arch and openSUSE, with a pinned source
      build for Debian-based systems whose package is too old

## Desktop integration

- [x] System tray with status icon, start on login, single instance
- [x] Menu entry created automatically when running from pip or source
- [x] English and Spanish interface (gettext), following the system language

## Packaging and project

- [x] Python package with `handcue` entry point (`pipx` friendly)
- [x] `.deb` with bundled dependencies for Debian 13 and Ubuntu 24.04
- [x] AppStream metadata and desktop entry
- [x] Unit tests for settings, migrations, triggers, actions, model verification, face
      storage and translations
- [x] CI (lint and tests on Python 3.11 to 3.13) and tagged releases with checksums

## Known limitations

- On GNOME the tray icon needs the AppIndicator extension. Without it the window stays
  visible and closing it quits the app.
- Volume control assumes PipeWire (`wpctl`).
- Face recognition has no liveness check: a photo of a registered person is accepted.
- Only one program can stream from a webcam at a time. Other apps should use the virtual
  camera while HandCue is running.
