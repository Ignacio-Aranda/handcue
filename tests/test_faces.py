import stat

import numpy as np
import pytest

from handcue import faces


@pytest.fixture
def no_keyring(monkeypatch):
    def unavailable(create):
        raise faces.FaceStoreError("no keyring")
    monkeypatch.setattr(faces, "_keyring_key", unavailable)


def make_person(name="Ana"):
    emb = np.random.default_rng(0).standard_normal(128).astype(np.float32)
    return {"id": None, "name": name, "group": None,
            "samples": [{"embedding": emb / np.linalg.norm(emb), "thumbnail": ""}]}


def test_roundtrip_with_key_file(no_keyring):
    store = faces.FaceStore()
    store.load()
    store.put_person(make_person())
    store.save()
    assert store.key_source == "file"
    assert stat.S_IMODE(faces.FACES_FILE.stat().st_mode) == 0o600
    assert stat.S_IMODE(faces.KEY_FILE.stat().st_mode) == 0o600
    assert b"Ana" not in faces.FACES_FILE.read_bytes()

    again = faces.FaceStore()
    again.load()
    assert [p["name"] for p in again.people] == ["Ana"]
    matrix, ids = again.gallery()
    assert matrix.shape == (1, 128) and ids == [again.people[0]["id"]]


def test_tampering_is_detected(no_keyring):
    store = faces.FaceStore()
    store.load()
    store.put_person(make_person())
    store.save()
    raw = bytearray(faces.FACES_FILE.read_bytes())
    raw[-1] ^= 1
    faces.FACES_FILE.write_bytes(bytes(raw))
    with pytest.raises(faces.FaceStoreError):
        faces.FaceStore().load()


def test_unreadable_data_is_never_overwritten(monkeypatch):
    # Saved with the keyring, which is then unavailable: saving must refuse, not
    # silently switch to a new key and destroy the existing data.
    key = faces.AESGCM.generate_key(bit_length=256)
    monkeypatch.setattr(faces, "_keyring_key", lambda create: key)
    store = faces.FaceStore()
    store.load()
    store.put_person(make_person())
    store.save()
    original = faces.FACES_FILE.read_bytes()

    def locked(create):
        raise faces.FaceStoreError("locked")
    monkeypatch.setattr(faces, "_keyring_key", locked)
    store = faces.FaceStore()
    with pytest.raises(faces.FaceStoreError):
        store.load()
    assert store.locked
    store.put_person(make_person("Eve"))
    with pytest.raises(faces.FaceStoreError):
        store.save()
    assert faces.FACES_FILE.read_bytes() == original


def test_delete_all_removes_files(no_keyring):
    store = faces.FaceStore()
    store.load()
    store.put_person(make_person())
    store.save()
    store.delete_all()
    assert not faces.FACES_FILE.exists()
