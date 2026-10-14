# Packaging and releases

## What a release contains

Every tag `vX.Y.Z` builds, through `.github/workflows/release.yml`:

| File | For |
|---|---|
| `handcue-X.Y.Z-py3-none-any.whl` | `pipx` or `pip`, any distribution |
| `handcue-X.Y.Z.tar.gz` | Source distribution |
| `handcue_X.Y.Z_debian13_amd64.deb` | Debian 13 |
| `handcue_X.Y.Z_ubuntu24.04_amd64.deb` | Ubuntu 24.04 and derivatives |
| `SHA256SUMS` | Checksums of all the above |

Build output goes to `dist/`, which is not committed.

## Python package

The project uses `pyproject.toml` with hatchling. `hatch_build.py` compiles `po/*.po` into
`handcue/locale/*/LC_MESSAGES/handcue.mo` before the wheel is assembled, so
installed copies are translated. Running from a source checkout needs `make i18n-compile`
(`make run` does it).

Dependencies in `pyproject.toml` are ranges. The exact versions used for release builds are
in `requirements.in`, and `requirements.lock` adds their hashes (`make lock`).

## Debian packages

MediaPipe and PySide6 are not packaged by Debian or Ubuntu, so the `.deb` bundles them:
`packaging/deb/build.sh` creates a virtual environment in `/opt/handcue`, installs
`requirements.lock` with `--require-hashes` plus the wheel, precompiles the bytecode and adds:

- `/usr/bin/handcue`, a small launcher,
- the desktop entry, AppStream metadata and icon under `/usr/share`.

The environment uses the system Python, so a package only works on the release it was built
for. That is why CI builds one per target inside the matching container. To build one for
the system you are on:

```bash
make deb
```

It needs `python3-venv` and `dpkg-dev`, and downloads the dependencies (several hundred MB).

## Not available yet

Flatpak and PyPI publishing are on the [roadmap](../ROADMAP.md).
