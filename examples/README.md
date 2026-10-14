# Examples

Standalone programs that reuse parts of HandCue. They need the app's dependencies
(`make venv`) and a webcam that is not in use by another program.

## Fruit Ninja

Multiplayer Fruit Ninja: slice the fruit with your index fingertip. The screen is split into
one lane per player.

```bash
.venv/bin/python examples/fruit_ninja.py 2
```

Space starts or restarts a round, `f` toggles fullscreen and `q` quits.
