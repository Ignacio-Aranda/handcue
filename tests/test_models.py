import hashlib
from pathlib import Path

import pytest

from handcue import models

PAYLOAD = b"model bytes"
DIGEST = hashlib.sha256(PAYLOAD).hexdigest()


@pytest.fixture
def fake_model(monkeypatch):
    monkeypatch.setitem(models.MODELS, "fake.task", ("https://example.org/fake.task", DIGEST))
    calls = []

    def download(url, dest):
        calls.append(url)
        with open(dest, "wb") as f:
            f.write(PAYLOAD)

    monkeypatch.setattr(models, "_download", download)
    return calls


def test_downloads_and_verifies(fake_model):
    path = models.path("fake.task", log=lambda m: None)
    assert Path(path).read_bytes() == PAYLOAD
    assert len(fake_model) == 1


def test_tampered_cache_is_replaced(fake_model):
    models.MODELS_DIR.mkdir(parents=True)
    (models.MODELS_DIR / "fake.task").write_bytes(b"evil")
    path = models.path("fake.task", log=lambda m: None)
    assert Path(path).read_bytes() == PAYLOAD
    assert len(fake_model) == 1


def test_bad_download_is_rejected(monkeypatch):
    monkeypatch.setitem(models.MODELS, "fake.task", ("https://example.org/fake.task", DIGEST))
    monkeypatch.setattr(models, "_download", lambda url, dest: Path(dest).write_bytes(b"evil"))
    with pytest.raises(models.ModelError):
        models.path("fake.task", log=lambda m: None)
    assert not list(models.MODELS_DIR.iterdir())  # no leftovers


def test_legacy_cache_is_reused(fake_model):
    models._LEGACY_DIR.mkdir(parents=True)
    (models._LEGACY_DIR / "fake.task").write_bytes(PAYLOAD)
    models.path("fake.task", log=lambda m: None)
    assert not fake_model


def test_every_model_url_is_pinned():
    for url, digest in models.MODELS.values():
        assert url.startswith("https://")
        assert "latest" not in url
        assert len(digest) == 64
