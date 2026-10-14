"""Registered people and groups for face recognition.

Faces are biometric data, so:
- They are stored under ~/.local/share/handcue, never next to the code.
- The file is encrypted with AES-256-GCM. The key lives in the desktop keyring
  (Secret Service: KWallet, GNOME Keyring), not next to the data.
- Only embeddings (128 floats) and a 112x112 thumbnail per sample are kept, so the
  user can see whose sample each one is.

File layout: MAGIC + key source (1 byte) + nonce (12 bytes) + ciphertext. Recording
where the key came from matters: if the keyring is unavailable one day, the app
must not silently create a new key and overwrite data encrypted with the old one.
"""
import base64
import json
import os
import shutil
import threading
import uuid

import cv2
import numpy as np
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from . import migrations
from .config import DATA_DIR
from .i18n import _

FACES_FILE = DATA_DIR / "faces.enc"
KEY_FILE = DATA_DIR / "key"  # only used when there is no keyring
_LEGACY_FACES_FILE = DATA_DIR / "caras.enc"
_LEGACY_KEY_FILE = DATA_DIR / "clave"
# Identifies our secret in the keyring. Changing it would orphan existing keys.
KEYRING_ATTRIBUTES = {"application": "control-gestos", "uso": "cifrado-caras"}
COLORS = ["#4c8dff", "#3ecf8e", "#e5a50a", "#b07cff", "#2fc6d6", "#ff7ab6", "#f05252"]

MAGIC = b"CGC1"
FROM_KEYRING, FROM_FILE = b"L", b"A"
KEY_SOURCES = {FROM_KEYRING: "keyring", FROM_FILE: "file"}


class FaceStoreError(Exception):
    pass


def _keyring_key(create):
    """Key stored in the desktop keyring, or None if there is none yet and create is
    False. Raises FaceStoreError if the keyring is missing or stays locked."""
    try:
        import secretstorage
        conn = secretstorage.dbus_init()
        collection = secretstorage.get_default_collection(conn)
        if collection.is_locked():
            collection.unlock()
            if collection.is_locked():
                raise FaceStoreError(_("the desktop keyring is locked"))
        items = list(collection.search_items(KEYRING_ATTRIBUTES))
        if items:
            return base64.b64decode(items[0].get_secret())
        if not create:
            return None
        key = AESGCM.generate_key(bit_length=256)
        collection.create_item("HandCue: face data encryption", KEYRING_ATTRIBUTES,
                               base64.b64encode(key), replace=True)
        return key
    except FaceStoreError:
        raise
    except Exception as e:  # noqa: BLE001 - D-Bus errors, no service, dialog dismissed...
        raise FaceStoreError(_("the desktop keyring is not available ({error})").format(error=e)) from e


def _file_key(create):
    """Fallback for systems without a keyring: a key file only the user can read."""
    if not KEY_FILE.exists():
        if not create:
            return None
        DATA_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(KEY_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(AESGCM.generate_key(bit_length=256))
    return KEY_FILE.read_bytes()


def _write_private(path, data):
    tmp = path.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def _move_legacy_files():
    if not FACES_FILE.exists() and _LEGACY_FACES_FILE.exists():
        os.replace(_LEGACY_FACES_FILE, FACES_FILE)
    if not KEY_FILE.exists() and _LEGACY_KEY_FILE.exists():
        os.replace(_LEGACY_KEY_FILE, KEY_FILE)


def _encode(arr):
    return base64.b64encode(np.asarray(arr, np.float32).tobytes()).decode()


def _decode(text):
    return np.frombuffer(base64.b64decode(text), np.float32).copy()


def thumbnail_to_text(img):
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return base64.b64encode(buf.tobytes()).decode() if ok else ""


def thumbnail_from_text(text):
    return cv2.imdecode(np.frombuffer(base64.b64decode(text), np.uint8), cv2.IMREAD_COLOR)


class FaceStore:
    """Groups and people with their samples. Thread-safe."""

    def __init__(self):
        self.lock = threading.RLock()
        self.groups = []   # [{id, name, color}]
        self.people = []   # [{id, name, group, samples: [{embedding: ndarray, thumbnail: str}]}]
        self.key_source = None
        self.locked = False  # saved data exists that could not be read
        self._key = None
        self._source = None

    def load(self):
        with self.lock:
            _move_legacy_files()
            if not FACES_FILE.exists():
                if not self.groups:
                    self.groups = [{"id": "family", "name": _("Family"), "color": COLORS[1]},
                                   {"id": "work", "name": _("Work"), "color": COLORS[0]}]
                return
            raw = FACES_FILE.read_bytes()
            if raw.startswith(MAGIC):
                source, body, aad = raw[4:5], raw[5:], raw[:5]
            else:  # very first format: always the keyring key, fixed AAD
                source, body, aad = FROM_KEYRING, raw, b"control-gestos"
            try:
                key = _keyring_key(create=False) if source == FROM_KEYRING else _file_key(create=False)
                if key is None:
                    raise FaceStoreError(_("the key they were encrypted with is missing"))
                payload = json.loads(AESGCM(key).decrypt(body[:12], body[12:], aad))
            except Exception as e:
                self.locked = True  # never save over data we could not read
                if isinstance(e, FaceStoreError):
                    raise
                raise FaceStoreError(_("the face data cannot be decrypted ({error})").format(
                    error=type(e).__name__)) from e
            self._key, self._source = key, source
            self.key_source = KEY_SOURCES[source]
            self.locked = False
            payload, migrated = migrations.migrate_faces(payload)
            self.groups = payload["groups"]
            self.people = [dict(p, samples=[{"embedding": _decode(s["embedding"]), "thumbnail": s["thumbnail"]}
                                            for s in p["samples"]]) for p in payload["people"]]
            if migrated:
                shutil.copy2(FACES_FILE, FACES_FILE.with_suffix(".enc.bak"))
                self.save()

    def save(self):
        with self.lock:
            if self.locked:
                raise FaceStoreError(_("Changes were not saved: there are saved faces that could not be "
                                       "read and they would be overwritten. Unlock the keyring and "
                                       "restart the app."))
            if self._key is None:  # first save: keyring if there is one, key file otherwise
                try:
                    self._key, self._source = _keyring_key(create=True), FROM_KEYRING
                except FaceStoreError:
                    self._key, self._source = _file_key(create=True), FROM_FILE
                self.key_source = KEY_SOURCES[self._source]
            payload = {"version": 3, "groups": self.groups,
                       "people": [dict(p, samples=[{"embedding": _encode(s["embedding"]),
                                                    "thumbnail": s["thumbnail"]} for s in p["samples"]])
                                  for p in self.people]}
            header = MAGIC + self._source
            nonce = os.urandom(12)
            ciphertext = AESGCM(self._key).encrypt(nonce, json.dumps(payload).encode(), header)
            DATA_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
            _write_private(FACES_FILE, header + nonce + ciphertext)

    def delete_all(self):
        """Removes every person, even if their data could not be read. Groups stay."""
        with self.lock:
            self.people = []
            self.locked = False
            for f in (FACES_FILE, FACES_FILE.with_suffix(".enc.bak")):
                if f.exists():
                    f.unlink()

    def group(self, gid):
        return next((g for g in self.groups if g["id"] == gid), None)

    def person(self, pid):
        return next((p for p in self.people if p["id"] == pid), None)

    def gallery(self):
        """(N x 128 matrix of normalized embeddings, person id for each row)."""
        with self.lock:
            embeddings, ids = [], []
            for p in self.people:
                for s in p["samples"]:
                    e = s["embedding"]
                    embeddings.append(e / (np.linalg.norm(e) or 1))
                    ids.append(p["id"])
            return (np.vstack(embeddings) if embeddings else np.zeros((0, 128), np.float32)), ids

    def add_group(self, name):
        with self.lock:
            used = {g["color"] for g in self.groups}
            color = next((c for c in COLORS if c not in used), COLORS[len(self.groups) % len(COLORS)])
            g = {"id": uuid.uuid4().hex[:8], "name": name, "color": color}
            self.groups.append(g)
            return g

    def remove_group(self, gid):
        with self.lock:
            self.groups = [g for g in self.groups if g["id"] != gid]
            for p in self.people:
                if p["group"] == gid:
                    p["group"] = None

    def put_person(self, person):
        with self.lock:
            if not person.get("id"):
                person["id"] = uuid.uuid4().hex[:8]
            i = next((i for i, p in enumerate(self.people) if p["id"] == person["id"]), None)
            if i is None:
                self.people.append(person)
            else:
                self.people[i] = person
            return person

    def remove_person(self, pid):
        with self.lock:
            self.people = [p for p in self.people if p["id"] != pid]
