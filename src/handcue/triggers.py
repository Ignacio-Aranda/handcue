"""Decides when each binding fires, given the signals of every frame."""
from .catalog import gesture

# A gesture that disappears for less than this (one misclassified frame) is not
# considered released.
GRACE = 0.3
# Minimum time between firings even when the user sets 0: otherwise a held gesture
# with "repeat" could start a program 30 times a second.
MIN_REPEAT = 0.2
MIN_SPAWNING = 1.0
SPAWNING_ACTIONS = {"app", "url", "command", "screenshot", "lock", "notification", "photo"}


def cooldown(b):
    minimum = MIN_SPAWNING if b["action"] in SPAWNING_ACTIONS else MIN_REPEAT if b["repeat"] else 0.0
    return max(float(b["cooldown"]), minimum)


def side_matches(sides, wanted):
    if "*" in sides:
        return True
    if wanted == "any":
        return bool(sides)
    if wanted == "both":
        return {"left", "right"} <= sides
    return wanted in sides


class TriggerState:
    def __init__(self):
        self.state = {}

    def evaluate(self, bindings, result, now, paused, mouse_active):
        """Returns (bindings to fire, progress), where progress maps the id of each
        binding whose gesture is being held to how far along it is (0..1)."""
        fire, progress = [], {}
        for b in bindings:
            if not b["enabled"]:
                continue
            if paused and b["action"] != "pause":
                continue
            # In mouse mode the hand is busy moving the pointer.
            if mouse_active and b["gesture"].startswith("hand:") and b["action"] != "mouse":
                continue
            st = self.state.setdefault(b["id"], {"start": None, "seen": 0.0, "fired": False, "last": -1e9})
            ready = now - st["last"] >= cooldown(b)

            if gesture(b["gesture"]).is_event:
                if ready and any(g == b["gesture"] and side_matches({side}, b["side"])
                                 for g, side in result.events):
                    st["last"] = now
                    fire.append(b)
                continue

            sides = result.signals.get(b["gesture"])
            if sides and side_matches(sides, b["side"]):
                st["seen"] = now
                if st["start"] is None:
                    st["start"] = now
            elif st["start"] is not None and now - st["seen"] > GRACE:
                st["start"], st["fired"] = None, False
            if st["start"] is None:
                continue

            held = now - st["start"]
            if held < b["hold"]:
                progress[b["id"]] = held / b["hold"]
            elif (not st["fired"] or b["repeat"]) and ready:
                st["fired"], st["last"] = True, now
                fire.append(b)
        return fire, progress

    def reset(self):
        self.state.clear()
