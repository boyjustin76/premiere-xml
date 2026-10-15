# premiere-xml

**Build Adobe Premiere Pro timelines from a JSON cut list.** No Premiere running, no
dependencies, no scripting API — it just writes a file you double-click to import.

[![tests](https://github.com/boyjustin76/premiere-xml/actions/workflows/tests.yml/badge.svg)](https://github.com/boyjustin76/premiere-xml/actions/workflows/tests.yml)
[![python](https://img.shields.io/badge/python-3.8%2B-blue)](https://www.python.org/)
[![license](https://img.shields.io/badge/license-MIT-green)](LICENSE)

```jsonc
// cutlist.json
{
  "name": "episode_12", "fps": 29.97, "width": 1920, "height": 1080,
  "sources": { "cam": { "path": "C:/footage/cam.mp4", "dur": 729.8 } },
  "cuts": [
    { "src": "cam", "in":  4.24, "out": 49.18 },
    { "src": "cam", "in": 61.02, "out": 88.40 }
  ]
}
```

```console
$ premiere-xml cutlist.json -o episode_12.xml
episode_12.xml
  episode_12 - 30 fps drop-frame
  2 video / 4 audio clips  (V1 2)  72.52s, 2174 frames
```

**File → Import** in Premiere. You get a sequence with the clips laid end to end,
audio attached, markers in place.

---

## Why this exists

If you generate your edit decisions somewhere else — a transcript, a silence
detector, a spreadsheet, an LLM — you still have to get them *into* Premiere.
The options are worse than they look:

| | |
|---|---|
| ExtendScript / UXP | Needs Premiere running and automatable. Slow, fragile, hard to test, Windows/macOS GUI only. |
| `.prproj` | Gzipped proprietary XML. Writing one by hand is a research project. |
| CLI | Premiere's command line opens *projects*. It will not open an `.xml`. |
| EDL | No multi-track, no markers, no enabled/disabled clips. |
| **FCP7 XML** | Plain text, documented by example, and Premiere imports it. ← this |

So: write FCP7 XML. The format is old and quirky, but it is the one interchange
Premiere reliably opens, and you can generate it from anything.

## Why this isn't a 20-line script

Because of one line per media file.

Encode your media path with stock percent-encoding and Premiere cannot find the
file. With one clip you get an offline clip — annoying but obvious. With 150 clips
the import collapses and Premiere tells you only this:

> The project appears to be damaged and cannot be opened.

Your XML is well-formed. Your media is on disk. Nothing mentions paths. We spent a
day bisecting a 150-clip document before exporting a sequence *from Premiere itself*
and diffing it against ours, character by character. Premiere had written:

```
file://localhost/C%3a/Users/me/Desktop/clips(OBS)[raw]/2025-09-30%2015-15-50.mp4
```

Four rules, and the third is the one that bites:

1. The drive colon is escaped — `C:` → `C%3a`
2. Hex digits are **lowercase** — `%3a`, not `%3A`
3. `( ) [ ] & ~ ! $ ' * + , ; = @ _ - .` are **left alone**
   — `urllib.parse.quote` escapes parentheses by default. `%28` in a path is what
   broke us.
4. Spaces → `%20`, non-ASCII → UTF-8 percent-encoding

That's [`premiere_xml/pathurl.py`](src/premiere_xml/pathurl.py) — twenty lines and a
long comment explaining why. If you only take one thing from this repo, take that
file.

The other thing worth stealing: **29.97 vs 30 never fails loudly.** FCP7 stores an
integer timebase plus an NTSC flag, so 29.97 is written "30, but NTSC". Declare the
wrong one and nothing errors — your timeline just drifts about 0.8 s over 13 minutes.

## Install

```bash
pip install premiere-xml          # not on PyPI yet — see below
# or
git clone https://github.com/boyjustin76/premiere-xml && pip install -e premiere-xml
```

Python 3.8+. **No runtime dependencies** — standard library only. Premiere is needed
to *use* the output, not to produce it, so this runs fine in CI or on a server.

## The cut list

Everything is **seconds** (floats). Frame maths happens inside.

```jsonc
{
  "name":   "episode_12",       // sequence name shown in Premiere
  "fps":    29.97,              // must match your source. 29.97 → drop-frame, 30 → non-drop
  "width":  1920,
  "height": 1080,

  "sources": {                  // one or more; the keys are referenced by "src" below
    "cam":   { "path": "C:/footage/cam.mp4",   "dur": 729.795 },
    "chart": { "path": "C:/footage/chart.mp4", "dur": 300.0   }
  },

  "cuts": [
    // V1 clips are butt-joined in list order. No "at" needed.
    { "src": "cam",   "in": 4.24,  "out": 49.18, "label": "intro" },
    { "src": "chart", "in": 12.00, "out": 31.50, "label": "walkthrough" },

    // Anything above V1 needs an explicit timeline position.
    // "enabled": false imports the clip switched off — a good way to keep the
    // takes you cut out, instead of throwing them away.
    { "src": "cam", "in": 300.0, "out": 318.4, "label": "unused take",
      "track": 2, "at": 68.68, "enabled": false },

    { "src": "chart", "in": 40.0, "out": 52.0, "track": 3, "at": 10.0,
      "audio": false }          // picture only
  ],

  "markers": [                  // optional
    { "at": 0.0,  "name": "INTRO" },
    { "at": 53.1, "name": "Chapter 1", "comment": "cam @ 4:12" },
    { "at": 90.0, "name": "B-roll",    "dur": 12.0 }   // "dur" makes it a span marker
  ]
}
```

| field | default | notes |
|---|---|---|
| `fps` | `29.97` | Read it off the file; don't assume. |
| `sources[].dur` | required | Real length in seconds. Out-points are clamped to it — an out-point past the end makes Premiere reject the import. |
| `cuts[].track` | `1` | V1 auto-joins; `≥2` requires `at`. |
| `cuts[].at` | — | Timeline position in seconds, for tracks above V1. |
| `cuts[].enabled` | `true` | `false` imports the clip disabled (still there, eye off). |
| `cuts[].audio` | `true` | `false` places picture only. |
| `cuts[].label` | file name | Clip name in the timeline. |

Mistakes that would otherwise be silent **raise instead**: an unknown `src` (which
would yield a quietly empty sequence) and a missing `at` above V1 (which would stack
every clip at 00:00).

## Python API

```python
import json
from premiere_xml import build_sequence

cutlist = json.load(open("cutlist.json", encoding="utf-8"))
xml, summary = build_sequence(cutlist)          # links=False to unlink A/V

open("sequence.xml", "w", encoding="utf-8", newline="\n").write(xml)
print(summary)
# {'name': 'episode_12', 'fps': 29.97, 'timebase': 30, 'ntsc': 'TRUE',
#  'frames': 2174, 'seconds': 72.54, 'video_clips': 2, 'audio_clips': 4,
#  'tracks': {'V1': 2}, 'disabled_clips': 0, 'markers': 0, 'sources': {...}}
```

`summary` exists so callers can assert on the result without re-parsing the XML.

## What it does and doesn't do

**Does:** multiple sources · multiple video tracks · butt-joined V1 · explicit
placement above V1 · disabled clips · picture-only clips · stereo audio on A1/A2 ·
linked A/V · sequence markers (point and span) · drop-frame and non-drop rates.

**Doesn't:** effects, transitions, speed changes, keyframes, colour, nesting, or
captions. It places cuts. Subtitles go in separately — import your `.srt` and drop it
on the sequence.

## Verified on

- Premiere Pro 25.x and 26.x, Windows
- Real imports, not just well-formedness: a 92-clip / 9-minute sequence across two
  source files, with 65 additional disabled clips on V2 and 7 markers, imported with
  every clip online and every marker on frame.
- Paths containing spaces, parentheses, square brackets and non-ASCII characters.

Not tested: macOS, UNC paths (`\\server\share`), DaVinci Resolve / Final Cut import
(the format is shared, so it may well work — reports welcome).

## Contributing

Issues and PRs welcome, especially: macOS and UNC path encoding, other NLEs that read
FCP7 XML, and any Premiere version where an import misbehaves — attach the cut list
and we'll add it as a test.

See [CONTRIBUTING.md](CONTRIBUTING.md). Tests run with no Premiere and no media files:

```bash
pip install -e ".[dev]" && pytest
```

## License

MIT — see [LICENSE](LICENSE).

한국어 설명은 [README.ko.md](README.ko.md).
