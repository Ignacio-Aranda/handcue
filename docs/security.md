# Security and privacy

This page explains what HandCue stores, who can read it, what it trusts and what it
does not protect against. To report a problem, see [SECURITY.md](../SECURITY.md).

## What the app can do

The app runs as your user, without root. With the permissions you give it, it can:

- read the webcam,
- start programs, open websites and run the commands you put in bindings,
- type and move the mouse through the RemoteDesktop portal, once you accept the desktop's
  permission dialog,
- write photos and screenshots to your pictures folder.

It does not listen on any network port. The only outgoing connections are the HTTPS
downloads of the ML models the first time they are needed.

## Stored data

| Data | Where | Protection |
|---|---|---|
| Settings, bindings, portal restore token | `~/.config/handcue/config.json` | File 0600, directory 0700, written atomically |
| Registered faces | `~/.local/share/handcue/faces.enc` | AES-256-GCM, file 0600 |
| Face data key | Desktop keyring (Secret Service), or `~/.local/share/handcue/key` (0600) if there is no keyring | See below |
| Photos and screenshots | Pictures folder | Files 0600 |
| ML models, sounds | `~/.cache/handcue` | Directory 0700, models verified by hash |

### Face data

Faces are biometric data, so the app stores as little as it can: a 128-number embedding and
a 112 x 112 thumbnail per sample, never full photos. The file is encrypted with AES-256-GCM.
Its header records where the key came from, and is authenticated together with the data.

The key is generated on first save and kept in the desktop keyring (KWallet or GNOME
Keyring). On systems without a keyring it is written to a file next to the data, readable
only by you. That protects copies of the data file (backups, for example) but not against
someone who can read your home directory.

If the saved faces cannot be decrypted (keyring locked or missing, damaged file), the app
refuses to save any face changes until they can be read again. It never replaces the key
silently, because that would overwrite the existing data.

*Delete all faces* removes the data file and its migration backup.

### ML models

The models are parsed by native code in MediaPipe and OpenCV, so a tampered model could
attack the app. Every model has a fixed URL that points at a specific version and a SHA-256
hash in `models.py`. Files are verified after download and again on every start; a file that
does not match is deleted and downloaded again.

## Threat model

**Someone in front of the camera.** Anyone the camera sees can make your gestures. Bindings
that type, run commands or open things are as available to them as to you. Turn on
*Faces > Only obey registered people* to ignore gestures unless a registered person is in
view. Note the next point.

**Spoofed faces.** Face recognition compares embeddings and has no liveness check, so a photo
or video of a registered person is accepted. Use it to personalize behavior, not to protect
anything that matters.

**Shared settings.** A configuration file can contain *Run command* bindings, which run
arbitrary shell commands. Treat a settings file from someone else like a script: read it
before using it.

**Other local users.** Settings, face data, photos and the single instance socket are only
accessible to your user. The socket lives in `$XDG_RUNTIME_DIR` so another user cannot create
it first and block the app.

**Flooding.** A held gesture with *repeat* fires at most every 0.2 s, and actions that start
programs at most once per second, whatever the binding says. At most eight actions can be
queued; the rest are dropped.

**Injection through names.** Names of people, groups, bindings and apps are shown as plain
text, never as HTML. Notification bodies are escaped. *Open website* only accepts `http` and
`https` URLs, so it cannot be used to open local files or other URL handlers.

**The virtual camera** is a normal video device. Any program in your session can read it,
just like the real webcam.

## Supply chain

- Release packages are built by GitHub Actions from a tagged commit, with dependencies
  pinned by hash in `requirements.lock`. `SHA256SUMS` is published with every release.
- Workflow actions are pinned to commit SHAs and the workflows run with read-only tokens,
  except the step that publishes the release.
- The optional `--source` mode of the virtual camera installer clones a fixed v4l2loopback
  release and checks its commit hash before building.
