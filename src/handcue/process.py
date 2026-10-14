import subprocess
import threading

_children = []
_lock = threading.Lock()


def spawn(args):
    """Starts a program without a shell and reaps the ones that already finished,
    so they do not pile up as zombies."""
    with _lock:
        _children[:] = [p for p in _children if p.poll() is None]
        _children.append(subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                          stderr=subprocess.DEVNULL, start_new_session=True))
