"""Upgrades settings and face data written by older versions.

Before 0.1.0 the code and its saved files used Spanish names. Those files are
translated here once and saved again in the current format.
"""

# --- settings (version 1 -> 2)

_KEYS = {
    "camara": "camera", "indice": "index", "ancho": "width", "alto": "height",
    "camara_ajustes": "camera_controls", "camara_perfiles": "camera_profiles",
    "encuadre_auto": "auto_framing", "gestos_activos": "gestures_enabled",
    "pausar_si_tapada": "pause_when_covered", "seguridad": "security",
    "solo_conocidos": "known_people_only", "reconocimiento": "recognition", "activo": "enabled",
    "umbral": "threshold", "confirmar": "confirmations", "camara_virtual": "virtual_camera",
    "activa": "enabled", "fondo": "background", "desenfoque": "blur", "imagen": "image",
    "espejo": "mirror", "resolucion": "resolution", "iniciar_con_sistema": "start_on_login",
    "aviso_bandeja": "tray_notice_shown", "detectores": "detectors", "manos": "hands",
    "cara": "face", "personas": "body", "vista": "view", "cuadricula": "grid",
    "histograma": "histogram", "superposicion": "overlay", "poderes": "effects",
    "max_manos": "max_hands", "max_personas": "max_people", "umbrales": "thresholds",
    "sonrisa": "smile", "boca": "mouth_open", "guino": "wink", "cejas": "brows", "beso": "kiss",
    "mejillas": "cheeks", "giro": "head_turn", "inclinacion": "head_tilt", "deslizar": "swipe",
    "confianza_gesto": "hand_confidence", "raton": "mouse", "mano": "hand",
    "sensibilidad": "speed", "suavizado": "smoothing", "carpeta_fotos": "photo_folder",
    "atajos": "bindings",
}
# Keys whose values are user data (control names, profile names) and must not be renamed.
_OPAQUE = {"camera_controls", "camera_profiles"}

_GESTURES = {
    "mano:puno": "hand:fist", "mano:palma": "hand:open_palm", "mano:senalar": "hand:pointing_up",
    "mano:pulgar_arriba": "hand:thumb_up", "mano:pulgar_abajo": "hand:thumb_down",
    "mano:victoria": "hand:victory", "mano:te_quiero": "hand:i_love_you", "mano:rock": "hand:rock",
    "mano:llamame": "hand:call_me", "mano:ok": "hand:ok", "mano:pellizco": "hand:pinch",
    "mano:tres": "hand:three", "mano:deslizar_izquierda": "hand:swipe_left",
    "mano:deslizar_derecha": "hand:swipe_right", "mano:deslizar_arriba": "hand:swipe_up",
    "mano:deslizar_abajo": "hand:swipe_down",
    "cara:sonrisa": "face:smile", "cara:boca_abierta": "face:mouth_open",
    "cara:guino_izq": "face:wink_left", "cara:guino_der": "face:wink_right",
    "cara:ojos_cerrados": "face:eyes_closed", "cara:cejas": "face:brows_up", "cara:beso": "face:kiss",
    "cara:mejillas": "face:puff_cheeks", "cara:girar_izq": "face:turn_left",
    "cara:girar_der": "face:turn_right", "cara:mirar_arriba": "face:look_up",
    "cara:mirar_abajo": "face:look_down",
    "persona:presente": "body:present", "persona:varias": "body:several", "persona:entra": "body:arrives",
    "persona:sale": "body:leaves", "persona:brazos_arriba": "body:arms_up",
    "persona:mano_levantada": "body:hand_raised", "persona:brazos_cruzados": "body:arms_crossed",
    "persona:t_pose": "body:t_pose",
    "reconocido:conocido": "recognized:known", "reconocido:desconocido": "recognized:unknown",
}
_ACTIONS = {
    "multimedia": "media", "escribir": "type", "atajo": "shortcut", "comando": "command",
    "sonido": "sound", "notificacion": "notification", "foto": "photo", "captura": "screenshot",
    "bloquear": "lock", "raton": "mouse", "pausa": "pause", "poderes": "effects",
}
_SIDES = {"cualquiera": "any", "izquierda": "left", "derecha": "right", "ambas": "both"}
_MEDIA = {"play_pausa": "play_pause", "siguiente": "next", "anterior": "previous",
          "subir_volumen": "volume_up", "bajar_volumen": "volume_down", "silenciar": "mute"}
_SOUNDS = {"moneda": "coin", "rugido": "roar", "guitarra": "guitar", "fanfarria": "fanfare",
           "bocina": "horn", "pedo": "fart"}
_KEYS_IN_SHORTCUTS = {
    "mayus": "shift", "intro": "enter", "espacio": "space", "retroceso": "backspace", "supr": "delete",
    "suprimir": "delete", "inicio": "home", "fin": "end", "repag": "pageup", "avpag": "pagedown",
    "arriba": "up", "abajo": "down", "izquierda": "left", "derecha": "right", "imprpant": "print",
}
_BACKGROUNDS = {"ninguno": "none", "desenfocar": "blur", "imagen": "image"}
_BINDING_KEYS = {"nombre": "name", "activo": "enabled", "gesto": "gesture", "lado": "side",
                 "mantener": "hold", "enfriamiento": "cooldown", "repetir": "repeat",
                 "accion": "action", "valor": "value"}


def _rename_keys(d):
    out = {}
    for k, v in d.items():
        k = _KEYS.get(k, k)
        out[k] = _rename_keys(v) if isinstance(v, dict) and k not in _OPAQUE else v
    return out


def _gesture(g):
    if not isinstance(g, str):
        return g
    if g.startswith("reconocido:grupo:"):
        return "recognized:group:" + g.removeprefix("reconocido:grupo:")
    if g.startswith("reconocido:persona:"):
        return "recognized:person:" + g.removeprefix("reconocido:persona:")
    return _GESTURES.get(g, g)


def _binding(b):
    if not isinstance(b, dict):
        return b
    b = {_BINDING_KEYS.get(k, k): v for k, v in b.items()}
    b["gesture"] = _gesture(b.get("gesture"))
    b["action"] = _ACTIONS.get(b.get("action"), b.get("action"))
    b["side"] = _SIDES.get(b.get("side"), b.get("side", "any"))
    value = b.get("value", "")
    if b["action"] == "media":
        value = _MEDIA.get(value, value)
    elif b["action"] == "sound":
        value = _SOUNDS.get(value, value)
    elif b["action"] == "shortcut" and isinstance(value, str):
        value = "+".join(_KEYS_IN_SHORTCUTS.get(p.strip().lower(), p.strip()) for p in value.split("+"))
    b["value"] = value
    return b


def _v1_to_v2(data):
    data = _rename_keys(data)
    if isinstance(data.get("bindings"), list):
        data["bindings"] = [_binding(b) for b in data["bindings"]]
    mouse = data.get("mouse")
    if isinstance(mouse, dict):
        mouse["hand"] = _SIDES.get(mouse.get("hand"), mouse.get("hand"))
    vc = data.get("virtual_camera")
    if isinstance(vc, dict):
        vc["background"] = _BACKGROUNDS.get(vc.get("background"), vc.get("background"))
    data["version"] = 2
    return data


def migrate_config(data):
    """Returns (data in the current format, whether anything changed)."""
    if data.get("version", 1) < 2:
        return _v1_to_v2(data), True
    return data, False


# --- face store payload (version 2 -> 3)

def migrate_faces(payload):
    """Returns (payload in the current format, whether anything changed)."""
    if payload.get("version", 1) >= 3:
        return payload, False
    groups = [{"id": g["id"], "name": g["nombre"], "color": g["color"]} for g in payload.get("grupos", [])]
    people = [{"id": p["id"], "name": p["nombre"], "group": p.get("grupo"),
               "samples": [{"embedding": s["emb"], "thumbnail": s["mini"]} for s in p.get("muestras", [])]}
              for p in payload.get("personas", [])]
    return {"version": 3, "groups": groups, "people": people}, True
