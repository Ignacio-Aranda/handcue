# Contributing

Thanks for taking the time. Bug reports, translations, documentation fixes and code are all
welcome.

## Reporting bugs

Open an issue with:

- what you did, what you expected and what happened,
- your distribution, desktop (KDE, GNOME...) and session type (Wayland or X11),
- your webcam model,
- the relevant lines from *Preferences > Activity log*.

Please do not attach screenshots or photos that show your face or anyone else's unless you
are fine with them being public. For security problems, follow [SECURITY.md](SECURITY.md)
instead of opening a public issue.

## Development setup

```bash
git clone https://github.com/Ignacio-Aranda/handcue.git
cd handcue
make venv    # creates .venv and installs the app in editable mode with the dev tools
make run     # compiles the translations and starts the app
make test
make lint
```

`make help` lists every target.

The app keeps its settings in `~/.config/handcue`. To try something without touching
your own settings, point the XDG variables somewhere else:

```bash
XDG_CONFIG_HOME=/tmp/cg/config XDG_DATA_HOME=/tmp/cg/data XDG_RUNTIME_DIR=/tmp/cg/run make run
```

## Project layout

```
src/handcue/     the application
  app.py                command line and startup
  engine.py             capture thread: camera, detection, bindings, preview
  detection.py          MediaPipe hand, face and body gestures
  triggers.py           when a binding fires (hold, cooldown, repeat)
  actions.py            running actions; desktop_input.py does keyboard and mouse
  recognition.py        face recognition; faces.py stores people encrypted
  camera.py             V4L2 controls; virtual_camera.py writes to v4l2loopback
  config.py             settings and their defaults; migrations.py upgrades old files
  catalog.py            the list of gestures and actions
  ui/                   Qt widgets and panels
  resources/            icon, fonts, virtual camera install script
po/                     translations (gettext)
data/                   desktop entry and AppStream metadata for packages
packaging/deb/          .deb build script
tests/                  pytest suite
examples/               standalone demos
docs/                   user and developer documentation
```

[docs/architecture.md](docs/architecture.md) explains how the pieces fit together.

## Code style

- Python 3.11+, checked with `ruff` (`make lint`). Lines up to 120 characters.
- Identifiers, comments and commit messages in English.
- Comments explain *why*: a hardware quirk, a security decision, a non-obvious trade-off.
  Do not narrate what the next line does, and do not leave commented-out code behind.
- Short docstrings on modules and on public functions whose behavior is not obvious from
  the name. No docstrings that only repeat the function name.
- Every user-visible string goes through `_()` from `handcue.i18n`. Use named
  placeholders (`_("Saved to {path}").format(path=p)`) so translators can reorder them, and
  `ngettext` for anything with a count.
- Show user text with `widgets.label()`, which sets plain text: names and values typed by
  users must never be rendered as HTML.
- Anything that writes user data creates files with mode `0600` and directories with `0700`.

## Tests

Tests live in `tests/` and run without a camera or a desktop session. Add a test when you
fix a bug or change settings, triggers, actions, migrations or storage. If you change the
format of the settings or the face store, bump its version and add a migration with a test.

## Translations

Source strings are English. Catalogs are in `po/`.

- After changing strings in the code: `make i18n-update` refreshes `po/handcue.pot`
  and merges it into every `po/*.po`.
- To add a language, copy the template, e.g. `cp po/handcue.pot po/fr.po`, fill in
  the header and translate. Any gettext editor (Poedit, Lokalize, GNOME Translation Editor)
  works.
- `make run` compiles the catalogs; the app follows the `LANGUAGE`/`LANG` environment.
- `tests/test_translations.py` fails if a catalog is incomplete or a placeholder is missing.

## Commits and pull requests

- One topic per pull request. Describe what changed and how you tested it.
- Commit subjects in the imperative, under 72 characters ("Fix focus not applied after
  resume"). Explain the reason in the body when it is not obvious.
- Make sure `make lint` and `make test` pass. CI runs both on Python 3.11, 3.12 and 3.13.
- Add a line under *Unreleased* in [CHANGELOG.md](CHANGELOG.md) for anything a user would
  notice.

## Versioning and releases

The project follows [Semantic Versioning](https://semver.org/). Until 1.0, minor versions
may change the settings format (with an automatic migration) or remove features.

To release:

1. Update the version in `src/handcue/__init__.py` and the `<releases>` entry in
   `data/io.github.ignacio_aranda.HandCue.metainfo.xml`.
2. Move the *Unreleased* notes in `CHANGELOG.md` under the new version and date.
3. If dependencies changed, update `requirements.in` and run `make lock`.
4. Commit, tag `vX.Y.Z` and push the tag. The release workflow builds the wheel, the `.deb`
   packages and `SHA256SUMS`, and publishes them on GitHub.

See [docs/packaging.md](docs/packaging.md) for details.

## License

By contributing you agree that your contributions are licensed under the GPL-3.0-or-later,
like the rest of the project.
