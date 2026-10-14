"""Sound effects synthesized with numpy. Each one is rendered once to a .wav in the
cache and played with pw-play, paplay or aplay, so PortAudio is not needed."""
import shutil
import wave

import numpy as np

from .config import CACHE_DIR
from .i18n import _
from .process import spawn

RATE = 44100
SOUNDS_DIR = CACHE_DIR / "sounds"
PLAYERS = ["pw-play", "paplay", "aplay"]


def _t(seconds):
    return np.arange(int(RATE * seconds)) / RATE


def _sine(f, t):
    return np.sin(2 * np.pi * f * t)


def _square(f, t):
    return np.sign(_sine(f, t))


def _saw(f, t):
    return 2 * ((f * t) % 1.0) - 1


def _low_pass(x, n):
    return np.convolve(x, np.ones(n) / n, mode="same")


def _sweep(f, wave_fn=np.sin):
    """Oscillator whose frequency changes per sample (f is an array)."""
    return wave_fn(2 * np.pi * np.cumsum(f) / RATE)


def _saw_phase(p):
    return 2 * ((p / (2 * np.pi)) % 1) - 1


def ding():
    t = _t(1.2)
    return (_sine(1320, t) + 0.5 * _sine(2640, t) + 0.25 * _sine(3960, t)) * np.exp(-t * 4)


def coin():
    a, b = _t(0.07), _t(0.45)
    return np.concatenate([0.4 * _square(988, a), 0.4 * _square(1319, b) * np.exp(-b * 6)])


def laser():
    t = _t(0.35)
    return 0.5 * np.sign(_sweep(1800 * np.exp(-t * 9) + 150)) * (1 - t / 0.35)


def roar():
    t = _t(1.4)
    noise = _low_pass(np.random.uniform(-1, 1, len(t)), 30) * 4
    low = _sweep(70 + 8 * np.sin(2 * np.pi * 5 * t), _saw_phase)
    env = np.minimum(1, t / 0.15) * np.exp(-np.maximum(0, t - 0.6) * 4)
    return np.tanh(2.5 * (noise + 0.6 * low) * (0.6 + 0.4 * _sine(23, t))) * env


def guitar():
    t = _t(2.2)
    s = sum(_saw(f * (1 + d), t) for f in (82.4, 123.5, 164.8) for d in (-0.003, 0.003))
    return _low_pass(np.tanh(3 * s), 6) * np.exp(-t * 1.4)


def fanfare():
    parts = []
    for f, d in ((523, 0.12), (659, 0.12), (784, 0.12), (1047, 0.7)):
        t = _t(d)
        tri = 2 * np.abs(_saw(f, t)) - 1
        parts.append(tri * np.minimum(1, t / 0.01) * np.exp(-t * (2 if d > 0.5 else 8)))
    return np.concatenate(parts)


def explosion():
    t = _t(1.6)
    return _low_pass(np.random.uniform(-1, 1, len(t)), 120) * 12 * np.exp(-t * 3)


def horn():
    t = _t(0.28)
    toot = (0.5 * _square(440, t) + 0.5 * _square(554, t)) * np.minimum(1, t / 0.01)
    return np.concatenate([toot, np.zeros(int(RATE * 0.08)), toot])


def fart():
    t = _t(0.8)
    f = 85 + 25 * np.sin(2 * np.pi * 6 * t) + np.random.normal(0, 8, len(t))
    s = _sweep(f, _saw_phase)
    env = np.minimum(1, t / 0.03) * (1 - t / 0.8) * (0.7 + 0.3 * np.sin(2 * np.pi * 13 * t))
    return _low_pass(np.tanh(3 * s), 8) * env


SOUNDS = {f.__name__: f for f in (ding, coin, laser, roar, guitar, fanfare, explosion, horn, fart)}


def wav_path(name):
    path = SOUNDS_DIR / f"{name}.wav"
    if not path.exists():
        CACHE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
        SOUNDS_DIR.mkdir(exist_ok=True, mode=0o700)
        x = SOUNDS[name]()
        x = (x / (np.max(np.abs(x)) or 1) * 0.8 * 32767).astype(np.int16)
        with wave.open(str(path), "wb") as f:
            f.setnchannels(1)
            f.setsampwidth(2)
            f.setframerate(RATE)
            f.writeframes(x.tobytes())
    return path


def play(name):
    if name not in SOUNDS:
        raise ValueError(_("Unknown sound: {name}").format(name=name))
    path = wav_path(name)
    for player in PLAYERS:
        if shutil.which(player):
            spawn([player, str(path)])
            return
    raise RuntimeError(_("No audio player found (pw-play, paplay or aplay)"))
