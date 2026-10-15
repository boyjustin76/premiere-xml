# Contributing

Thanks for looking. This is a small library with one job, and it should stay that way.

## Running the tests

```bash
pip install -e ".[dev]"
pytest
```

Tests run **without Premiere and without media files** — they parse the generated XML
instead. Please keep it that way: a test that needs an NLE installed is a test nobody
runs.

## What's especially welcome

- **Path encoding on other platforms.** macOS volume paths and Windows UNC
  (`\\server\share`) are untested. If you have a Premiere export from one of those,
  the single most useful contribution is its `<pathurl>` line.
- **Other NLEs.** DaVinci Resolve and Final Cut read FCP7 XML too. Reports either way
  help the README say what's true.
- **A Premiere version where an import misbehaves.** Attach the cut list; we'll turn
  it into a regression test.

## What this library won't grow into

Effects, transitions, speed ramps, keyframes, colour, nesting, captions. It places
cuts. Keeping the scope small is why it has no dependencies and why the whole thing
fits in two files.

## Style

- Standard library only in `src/`. `pytest` is the only dev dependency.
- Comments explain **why**, especially where the format is counter-intuitive. The
  `pathurl` module is the model: the rules are strange, so the reasoning is written
  down next to them.
- When you fix something that failed silently, add a test that would have caught it,
  and say in the test's docstring what the symptom was. Those docstrings are the most
  valuable documentation in the repo.
