# Changelog

All notable changes are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0] - 2026-10-14

First public release.

### Added

- Hand, face and body gesture detection with MediaPipe: 36 gestures, with hold time,
  cooldown, repeat and left/right hand filters per binding.
- Actions: media and volume, open app, open website, keyboard shortcut, type text, run
  command, notification, sound effect, photo with countdown, screenshot, lock screen,
  virtual mouse, pause and visual effects.
- Face recognition (OpenCV YuNet + SFace) with people, groups, per-person and per-group
  bindings, and an option to obey registered people only.
- Webcam controls over V4L2: exposure, white balance, focus, zoom and digital framing with
  face tracking, anti-flicker, resolution and frame rate, built-in and saved profiles.
- Virtual camera through v4l2loopback with background blur, solid color or image.
- System tray, start on login, single instance, privacy shutter detection, settings
  restored after suspend.
- English and Spanish user interface.
- `.deb` packages for Debian 13 and Ubuntu 24.04, and a Python wheel.

### Security

- Settings and face data stored in XDG directories with owner-only permissions.
- Face data encrypted with AES-256-GCM, key kept in the desktop keyring; the app refuses
  to overwrite face data it cannot decrypt.
- ML models downloaded from pinned URLs and verified with SHA-256 on every start.
- Minimum cooldowns and a bounded action queue so a held gesture cannot flood the system.
- "Open website" only accepts http and https URLs.

[Unreleased]: https://github.com/Ignacio-Aranda/handcue/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Ignacio-Aranda/handcue/releases/tag/v0.1.0
