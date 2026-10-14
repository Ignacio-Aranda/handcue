from handcue.catalog import new_binding
from handcue.detection import Result
from handcue.triggers import MIN_REPEAT, MIN_SPAWNING, TriggerState, cooldown, side_matches


def frame(signals=None, events=None):
    r = Result()
    for g, sides in (signals or {}).items():
        r.signals[g] = set(sides)
    r.events = list(events or [])
    return r


def test_fires_after_hold_time():
    b = new_binding("hand:fist", "lock", hold=0.5)
    t = TriggerState()
    fired, progress = t.evaluate([b], frame({"hand:fist": {"left"}}), 0.0, False, False)
    assert not fired and progress[b["id"]] == 0
    fired, progress = t.evaluate([b], frame({"hand:fist": {"left"}}), 0.3, False, False)
    assert not fired and 0.5 < progress[b["id"]] < 0.7
    fired, _p = t.evaluate([b], frame({"hand:fist": {"left"}}), 0.6, False, False)
    assert fired == [b]
    fired, _p = t.evaluate([b], frame({"hand:fist": {"left"}}), 2.0, False, False)
    assert not fired  # held, not repeating: fires once


def test_short_dropout_does_not_release():
    b = new_binding("hand:fist", "lock", hold=0.5)
    t = TriggerState()
    t.evaluate([b], frame({"hand:fist": {"left"}}), 0.0, False, False)
    t.evaluate([b], frame(), 0.2, False, False)  # one missed frame
    fired, _p = t.evaluate([b], frame({"hand:fist": {"left"}}), 0.55, False, False)
    assert fired == [b]


def test_repeat_respects_minimum_cooldown():
    b = new_binding("hand:pointing_up", "media", "volume_up", hold=0, cooldown=0, repeat=True)
    assert cooldown(b) == MIN_REPEAT
    t = TriggerState()
    times = [i * 0.05 for i in range(21)]  # one second at 20 fps
    fired = sum(len(t.evaluate([b], frame({"hand:pointing_up": {"right"}}), now, False, False)[0])
                for now in times)
    assert fired <= 1 / MIN_REPEAT + 1


def test_spawning_actions_have_a_floor():
    assert cooldown(new_binding("hand:fist", "command", "true", cooldown=0)) == MIN_SPAWNING


def test_events_fire_once():
    b = new_binding("hand:swipe_left", "media", "previous")
    t = TriggerState()
    fired, _p = t.evaluate([b], frame(events=[("hand:swipe_left", "right")]), 0.0, False, False)
    assert fired == [b]
    fired, _p = t.evaluate([b], frame(events=[("hand:swipe_left", "right")]), 0.5, False, False)
    assert not fired  # still cooling down


def test_paused_only_runs_pause_bindings():
    pause = new_binding("hand:open_palm", "pause", hold=0)
    other = new_binding("hand:open_palm", "lock", hold=0)
    fired, _p = TriggerState().evaluate([pause, other], frame({"hand:open_palm": {"left"}}), 0.0, True, False)
    assert fired == [pause]


def test_side_matching():
    assert side_matches({"left"}, "any")
    assert not side_matches(set(), "any")
    assert side_matches({"left", "right"}, "both")
    assert not side_matches({"left"}, "both")
    assert side_matches({"*"}, "right")
    assert not side_matches({"left"}, "right")
