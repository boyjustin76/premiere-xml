"""Turn a JSON cut list into a Premiere-importable FCP7 (``xmeml``) sequence.

The whole library is this one function plus :mod:`premiere_xml.pathurl`. It writes
text; it never launches Premiere and does not use Premiere scripting.

See the project README for the cut-list format and a worked example.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Tuple
from xml.sax.saxutils import escape

from .pathurl import pathurl

__all__ = ["build_sequence", "frame_rate"]

AUDIO_DEPTH = 16
AUDIO_RATE = 48000


def frame_rate(fps: float) -> Tuple[int, str, str]:
    """``29.97 -> (30, "TRUE", "DF")``, ``30 -> (30, "FALSE", "NDF")``.

    FCP7 stores a *timebase* (an integer) plus an NTSC flag, so 29.97 is written as
    "30, but NTSC". Getting this wrong does not fail loudly -- it drifts. At 0.1%,
    a 13-minute sequence ends up ~0.8 s out of sync with its source.
    """
    timebase = int(round(fps))
    ntsc = abs(fps - timebase) > 0.001
    return timebase, ("TRUE" if ntsc else "FALSE"), ("DF" if ntsc else "NDF")


def _rate(timebase: int, ntsc: str) -> str:
    return f"<rate><timebase>{timebase}</timebase><ntsc>{ntsc}</ntsc></rate>"


def _timecode(timebase: int, ntsc: str, df: str) -> str:
    return (
        f"<timecode>{_rate(timebase, ntsc)}<string>00:00:00:00</string>"
        f"<frame>0</frame><displayformat>{df}</displayformat></timecode>"
    )


def _file_element(file_id, path, frames, width, height, timebase, ntsc, df) -> str:
    """Full ``<file>`` definition.

    Emitted inside the *first* clip that uses this source; later clips reference it
    with ``<file id="..."/>``. Repeating the definition makes Premiere treat one
    media file as several separate project items.
    """
    return (
        f'<file id="{file_id}"><name>{escape(os.path.basename(path))}</name>'
        f"<pathurl>{escape(pathurl(path))}</pathurl>{_rate(timebase, ntsc)}"
        f"<duration>{frames}</duration>{_timecode(timebase, ntsc, df)}"
        f"<media><video><samplecharacteristics>{_rate(timebase, ntsc)}"
        f"<width>{width}</width><height>{height}</height>"
        f"<pixelaspectratio>square</pixelaspectratio><anamorphic>FALSE</anamorphic>"
        f"</samplecharacteristics></video>"
        f"<audio><samplecharacteristics><depth>{AUDIO_DEPTH}</depth>"
        f"<samplerate>{AUDIO_RATE}</samplerate></samplecharacteristics>"
        f"<channelcount>2</channelcount></audio></media></file>"
    )


def _link_group(n: int, video_track: int, video_index: int, audio_index: int) -> str:
    """Bind one video clip to its two audio clips.

    With these, dragging a clip in the timeline moves its audio too. Without them the
    import still succeeds, but picture and sound behave as unrelated clips.
    """
    return (
        f'<link><linkclipref>cv{n}</linkclipref><mediatype>video</mediatype>'
        f"<trackindex>{video_track}</trackindex><clipindex>{video_index}</clipindex></link>"
        f'<link><linkclipref>ca{n}a</linkclipref><mediatype>audio</mediatype>'
        f"<trackindex>1</trackindex><clipindex>{audio_index}</clipindex>"
        f"<groupindex>1</groupindex></link>"
        f'<link><linkclipref>ca{n}b</linkclipref><mediatype>audio</mediatype>'
        f"<trackindex>2</trackindex><clipindex>{audio_index}</clipindex>"
        f"<groupindex>1</groupindex></link>"
    )


def _marker(marker: Dict[str, Any], fps: float) -> str:
    """One sequence marker. ``<out>-1</out>`` means a point marker rather than a span."""
    start = int(round(float(marker.get("at", 0.0)) * fps))
    span = float(marker.get("dur", 0.0) or 0.0)
    end = start + int(round(span * fps)) if span > 0 else -1
    return (
        "<marker>"
        f'<comment>{escape(str(marker.get("comment", "")))}</comment>'
        f'<name>{escape(str(marker.get("name", "")))}</name>'
        f"<in>{start}</in><out>{end}</out></marker>"
    )


def build_sequence(
    cutlist: Dict[str, Any],
    links: bool = True,
    name: str | None = None,
) -> Tuple[str, Dict[str, Any]]:
    """Build the XML document.

    :param cutlist: parsed cut list (see README for the schema)
    :param links: emit ``<link>`` elements so picture and sound move together
    :param name: override ``cutlist["name"]``
    :returns: ``(xml_text, summary)`` -- *summary* is a plain dict you can print or
        assert on, so callers do not have to re-parse the XML to sanity-check it.
    :raises KeyError: a cut references an unknown source, or a clip above V1 has no
        ``at``. Both are silent disasters otherwise (an empty sequence, or every
        upper-track clip stacked at 0:00), so they raise instead.
    """
    fps = float(cutlist.get("fps", 29.97))
    timebase, ntsc, df = frame_rate(fps)
    width = int(cutlist.get("width", 1920))
    height = int(cutlist.get("height", 1080))
    seq_name = name or cutlist.get("name", "sequence")

    def frames_of(seconds: float) -> int:
        return int(round(float(seconds) * fps))

    # Source media. Durations round *down*: an out-point past the end of the file
    # makes Premiere reject the import.
    sources: Dict[str, Dict[str, Any]] = {}
    file_ids: Dict[str, str] = {}
    for i, (key, src) in enumerate(cutlist["sources"].items(), start=1):
        sources[key] = {"path": src["path"], "frames": int(float(src["dur"]) * fps)}
        file_ids[key] = f"file-{i}"

    # Lay cuts out per track. V1 is butt-joined in list order; upper tracks are
    # placed at their explicit "at" position.
    placed: Dict[int, List[Dict[str, Any]]] = {}
    playhead = 0
    for cut in cutlist["cuts"]:
        key = cut["src"]
        if key not in sources:
            raise KeyError(f'cut references src "{key}", which is not in "sources"')
        track = int(cut.get("track", 1))
        start_f = frames_of(cut["in"])
        end_f = min(frames_of(cut["out"]), sources[key]["frames"])
        if end_f <= start_f:
            continue
        if track == 1:
            at = playhead
            playhead += end_f - start_f
        else:
            if "at" not in cut:
                raise KeyError(f'clip on V{track} needs "at" (timeline start, seconds): {cut}')
            at = frames_of(cut["at"])
        placed.setdefault(track, []).append(
            {
                "src": key,
                "in": start_f,
                "out": end_f,
                "start": at,
                "end": at + (end_f - start_f),
                "label": cut.get("label", os.path.basename(sources[key]["path"])),
                "enabled": bool(cut.get("enabled", True)),
                "audio": bool(cut.get("audio", True)),
            }
        )

    # Sequence duration must cover every track. Measuring V1 alone pushes upper-track
    # clips past the end of the sequence, where the timeline will not show them.
    total_frames = max([c["end"] for track in placed.values() for c in track] or [0])

    defined: set = set()

    def file_ref(key: str) -> str:
        fid = file_ids[key]
        if fid in defined:
            return f'<file id="{fid}"/>'
        defined.add(fid)
        s = sources[key]
        return _file_element(fid, s["path"], s["frames"], width, height, timebase, ntsc, df)

    video_tracks: Dict[int, str] = {}
    audio_1: List[str] = []
    audio_2: List[str] = []
    n = 0
    audio_n = 0
    for track in sorted(placed):
        items: List[str] = []
        for index, clip in enumerate(placed[track], start=1):
            n += 1
            with_audio = clip["audio"]
            if with_audio:
                audio_n += 1
            head = (
                f'<name>{escape(clip["label"])}</name>'
                f'<enabled>{"TRUE" if clip["enabled"] else "FALSE"}</enabled>'
                f'<duration>{sources[clip["src"]]["frames"]}</duration>{_rate(timebase, ntsc)}'
                f'<start>{clip["start"]}</start><end>{clip["end"]}</end>'
                f'<in>{clip["in"]}</in><out>{clip["out"]}</out>'
            )
            bind = _link_group(n, track, index, audio_n) if (links and with_audio) else ""
            items.append(
                f'<clipitem id="cv{n}">{head}{file_ref(clip["src"])}'
                f"<compositemode>normal</compositemode>{bind}</clipitem>"
            )
            if not with_audio:
                continue
            for channel, bucket in ((1, audio_1), (2, audio_2)):
                bucket.append(
                    f'<clipitem id="ca{n}{"a" if channel == 1 else "b"}">{head}'
                    f'<file id="{file_ids[clip["src"]]}"/>'
                    f"<sourcetrack><mediatype>audio</mediatype>"
                    f"<trackindex>{channel}</trackindex></sourcetrack>{bind}</clipitem>"
                )
        video_tracks[track] = "".join(items)

    markers = "".join(_marker(m, fps) for m in cutlist.get("markers") or [])
    video_xml = "".join(f"<track>{video_tracks[t]}</track>" for t in sorted(video_tracks))

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xmeml>\n<xmeml version="4">\n'
        f'<sequence id="{escape(seq_name)}"><name>{escape(seq_name)}</name>'
        f"<duration>{total_frames}</duration>{_rate(timebase, ntsc)}"
        f"{_timecode(timebase, ntsc, df)}"
        "<media><video><format><samplecharacteristics>" + _rate(timebase, ntsc) +
        f"<width>{width}</width><height>{height}</height>"
        "<pixelaspectratio>square</pixelaspectratio><anamorphic>FALSE</anamorphic>"
        "</samplecharacteristics></format>"
        f"{video_xml}</video>"
        "<audio><numOutputChannels>2</numOutputChannels>"
        f"<format><samplecharacteristics><depth>{AUDIO_DEPTH}</depth>"
        f"<samplerate>{AUDIO_RATE}</samplerate></samplecharacteristics></format>"
        f'<track>{"".join(audio_1)}<outputchannelindex>1</outputchannelindex></track>'
        f'<track>{"".join(audio_2)}<outputchannelindex>2</outputchannelindex></track>'
        "</audio>"
        f"</media>{markers}</sequence>\n</xmeml>\n"
    )

    summary = {
        "name": seq_name,
        "fps": fps,
        "timebase": timebase,
        "ntsc": ntsc,
        "frames": total_frames,
        "seconds": round(total_frames / fps, 3),
        "video_clips": sum(len(t) for t in placed.values()),
        "audio_clips": len(audio_1) + len(audio_2),
        "tracks": {f"V{t}": len(placed[t]) for t in sorted(placed)},
        "disabled_clips": sum(1 for t in placed.values() for c in t if not c["enabled"]),
        "markers": len(cutlist.get("markers") or []),
        "sources": {k: os.path.basename(s["path"]) for k, s in sources.items()},
    }
    return xml, summary
