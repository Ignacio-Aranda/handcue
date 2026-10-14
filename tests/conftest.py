import pytest


@pytest.fixture(autouse=True)
def isolated_dirs(tmp_path, monkeypatch):
    """Point every module that stores files at a temporary directory."""
    from handcue import config, faces, models, sounds

    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config" / "config.json")
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(models, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(models, "MODELS_DIR", tmp_path / "cache" / "models")
    monkeypatch.setattr(models, "_LEGACY_DIR", tmp_path / "cache" / "modelos")
    monkeypatch.setattr(models, "_verified", set())
    monkeypatch.setattr(sounds, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(sounds, "SOUNDS_DIR", tmp_path / "cache" / "sounds")
    data = tmp_path / "data"
    monkeypatch.setattr(faces, "DATA_DIR", data)
    monkeypatch.setattr(faces, "FACES_FILE", data / "faces.enc")
    monkeypatch.setattr(faces, "KEY_FILE", data / "key")
    monkeypatch.setattr(faces, "_LEGACY_FACES_FILE", data / "caras.enc")
    monkeypatch.setattr(faces, "_LEGACY_KEY_FILE", data / "clave")
    return tmp_path
