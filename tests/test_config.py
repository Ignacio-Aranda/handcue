import json
import stat

from handcue import config


def test_defaults_include_example_bindings(isolated_dirs):
    cfg = config.load(config.CONFIG_FILE)
    assert cfg["bindings"]
    assert cfg["version"] == config.VERSION


def test_saved_file_is_private(isolated_dirs):
    cfg = config.load(config.CONFIG_FILE)
    config.save(cfg, config.CONFIG_FILE)
    assert stat.S_IMODE(config.CONFIG_FILE.stat().st_mode) == 0o600
    assert stat.S_IMODE(config.CONFIG_FILE.parent.stat().st_mode) == 0o700
    assert json.loads(config.CONFIG_FILE.read_text())["version"] == config.VERSION


def test_corrupt_file_falls_back_to_defaults(isolated_dirs):
    config.CONFIG_FILE.parent.mkdir(parents=True)
    config.CONFIG_FILE.write_text("[1, 2")
    assert config.load(config.CONFIG_FILE)["camera"]["index"] == 0


def test_unknown_bindings_are_dropped(isolated_dirs):
    config.CONFIG_FILE.parent.mkdir(parents=True)
    good = {"id": "1", "name": "", "enabled": True, "gesture": "hand:fist", "side": "any", "hold": 0.5,
            "cooldown": 1, "repeat": False, "action": "lock", "value": ""}
    face = dict(good, id="2", gesture="recognized:person:xyz")
    config.CONFIG_FILE.write_text(json.dumps({"version": 2, "bindings": [
        good, face, dict(good, id="3", gesture="hand:nope"), dict(good, id="4", action="format_disk"), "junk"]}))
    assert [b["id"] for b in config.load(config.CONFIG_FILE)["bindings"]] == ["1", "2"]


def test_legacy_dirs_are_moved(tmp_path, monkeypatch):
    old, new = tmp_path / "control-gestos", tmp_path / "handcue"
    old.mkdir()
    (old / "config.json").write_text("{}")
    monkeypatch.setattr(config, "LEGACY_DIRS", [(old, new)])
    config.move_legacy_dirs()
    assert (new / "config.json").exists() and not old.exists()
    old.mkdir()  # if both exist, the new one wins and nothing is touched
    config.move_legacy_dirs()
    assert old.exists()
