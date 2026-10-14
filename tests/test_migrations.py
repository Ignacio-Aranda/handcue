import json

from handcue import config, migrations

V1 = {
    "camara": {"indice": 2, "ancho": 1920, "alto": 1080, "fps": 30},
    "camara_ajustes": {"focus_absolute": 40, "brightness": 128},
    "camara_perfiles": {"Mi perfil": {"contrast": 10}},
    "gestos_activos": False,
    "seguridad": {"solo_conocidos": True},
    "reconocimiento": {"activo": True, "umbral": 0.5, "confirmar": 1},
    "camara_virtual": {"activa": True, "fondo": "desenfocar", "desenfoque": 6, "imagen": "", "espejo": False},
    "detectores": {"manos": False, "cara": True, "personas": True},
    "raton": {"mano": "izquierda", "sensibilidad": 2.0, "suavizado": 0.3},
    "portal_token": "restore-token",
    "atajos": [
        {"id": "a1", "nombre": "Play", "activo": True, "gesto": "mano:pulgar_arriba", "lado": "cualquiera",
         "mantener": 0.6, "enfriamiento": 1.5, "repetir": False, "accion": "multimedia", "valor": "play_pausa"},
        {"id": "a2", "nombre": "", "activo": False, "gesto": "cara:guino_izq", "lado": "cualquiera",
         "mantener": 0.4, "enfriamiento": 1.5, "repetir": False, "accion": "atajo", "valor": "ctrl+espacio"},
        {"id": "a3", "nombre": "", "activo": True, "gesto": "reconocido:persona:abc123", "lado": "cualquiera",
         "mantener": 0, "enfriamiento": 1.5, "repetir": False, "accion": "sonido", "valor": "moneda"},
    ],
}


def test_v1_config_is_translated():
    data, changed = migrations.migrate_config(json.loads(json.dumps(V1)))
    assert changed
    assert data["version"] == 2
    assert data["camera"] == {"index": 2, "width": 1920, "height": 1080, "fps": 30}
    # user data inside these keys must be kept as is
    assert data["camera_controls"] == {"focus_absolute": 40, "brightness": 128}
    assert data["camera_profiles"] == {"Mi perfil": {"contrast": 10}}
    assert data["security"] == {"known_people_only": True}
    assert data["recognition"] == {"enabled": True, "threshold": 0.5, "confirmations": 1}
    assert data["virtual_camera"]["background"] == "blur"
    assert data["detectors"] == {"hands": False, "face": True, "body": True}
    assert data["mouse"] == {"hand": "left", "speed": 2.0, "smoothing": 0.3}
    b1, b2, b3 = data["bindings"]
    assert b1 == {"id": "a1", "name": "Play", "enabled": True, "gesture": "hand:thumb_up", "side": "any",
                  "hold": 0.6, "cooldown": 1.5, "repeat": False, "action": "media", "value": "play_pause"}
    assert (b2["gesture"], b2["action"], b2["value"]) == ("face:wink_left", "shortcut", "ctrl+space")
    assert (b3["gesture"], b3["value"]) == ("recognized:person:abc123", "coin")


def test_current_config_is_left_alone():
    data = {"version": 2, "camera": {"index": 0}}
    assert migrations.migrate_config(data) == (data, False)


def test_load_migrates_and_saves(isolated_dirs):
    config.CONFIG_FILE.parent.mkdir(parents=True)
    config.CONFIG_FILE.write_text(json.dumps(V1))
    cfg = config.load(config.CONFIG_FILE)
    assert cfg["portal_token"] == "restore-token"  # noqa: S105
    assert len(cfg["bindings"]) == 3
    saved = json.loads(config.CONFIG_FILE.read_text())
    assert saved["version"] == 2 and "atajos" not in saved


def test_faces_payload_migration():
    old = {"version": 2, "grupos": [{"id": "g1", "nombre": "Casa", "color": "#fff"}],
           "personas": [{"id": "p1", "nombre": "Ana", "grupo": "g1", "muestras": [{"emb": "AAAA", "mini": "BBBB"}]}]}
    new, changed = migrations.migrate_faces(old)
    assert changed
    assert new == {"version": 3, "groups": [{"id": "g1", "name": "Casa", "color": "#fff"}],
                   "people": [{"id": "p1", "name": "Ana", "group": "g1",
                               "samples": [{"embedding": "AAAA", "thumbnail": "BBBB"}]}]}
