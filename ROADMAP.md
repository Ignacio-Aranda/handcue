# Roadmap

Ideas and planned work. Nothing here has a date. If you want to pick something up, open an
issue first so we can agree on the approach.

What already works is listed in [docs/features.md](docs/features.md).

## Next (0.2)

- [ ] Publish to PyPI with trusted publishing, so `pipx install handcue` works
- [ ] Screenshots through the xdg-desktop-portal Screenshot API instead of Spectacle or
      GNOME Screenshot
- [ ] Volume control fallback with `pactl` for systems without PipeWire
- [ ] Show model download progress in the UI instead of only a toast
- [ ] Export and import settings, warning about any "Run command" bindings on import
- [ ] Toggle gestures with a global shortcut (GlobalShortcuts portal)
- [ ] Follow the system light/dark theme

## Later

- [ ] Flatpak package and Flathub submission
- [ ] Liveness check for face recognition (blink or head movement before trusting a face)
- [ ] Record custom hand gestures from a few examples
- [ ] Scroll gesture for the virtual mouse
- [ ] Bindings that only apply while a given app is focused (needs a portal or compositor
      support on Wayland)
- [ ] More translations
- [ ] UI tests with pytest-qt and tests for the engine using recorded frames
- [ ] Keyboard navigation and screen reader labels for every control
- [ ] Signed release artifacts (build provenance attestations)

## Maybe

- [ ] GPU delegate for MediaPipe where available
- [ ] Turn the Fruit Ninja example into a game mode inside the app
