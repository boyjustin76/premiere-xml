"""Sequence building, checked without Premiere and without media files.

These cover the places where a mistake does not raise -- it just produces an XML
that Premiere silently refuses, or a timeline that is subtly out of sync.
"""

import json
import pathlib
import xml.etree.ElementTree as ET

import pytest

from premiere_xml import build_sequence, frame_rate

EXAMPLE = pathlib.Path(__file__).resolve().parents[1] / "examples" / "cutlist.sample.json"


@pytest.fixture()
def cutlist():
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def tracks_of(xml):
    return ET.fromstring(xml).findall("./sequence/media/video/track")


def test_the_quickstart_actually_works(cutlist):
    """The README's 30-second path. If this breaks, nobody gets past the front page."""
    xml, summary = build_sequence(cutlist)
    ET.fromstring(xml)  # well-formed
    assert summary["video_clips"] == 6
    assert summary["audio_clips"] == 12
    assert summary["tracks"] == {"V1": 4, "V2": 2}
    assert summary["markers"] == 3
    assert summary["disabled_clips"] == 2


@pytest.mark.parametrize(
    "fps,expected",
    [
        (29.97, (30, "TRUE", "DF")),
        (30.0, (30, "FALSE", "NDF")),
        (23.976, (24, "TRUE", "DF")),
        (25.0, (25, "FALSE", "NDF")),
        (59.94, (60, "TRUE", "DF")),
    ],
)
def test_frame_rate_separates_ntsc_from_whole_rates(fps, expected):
    """29.97 vs 30 does not fail loudly -- it drifts ~0.8 s over 13 minutes."""
    assert frame_rate(fps) == expected


def test_whole_frame_rates_are_written_non_drop(cutlist):
    xml, _ = build_sequence(dict(cutlist, fps=30.0))
    assert "<ntsc>FALSE</ntsc>" in xml and "NDF" in xml
    assert "<ntsc>TRUE</ntsc>" not in xml


def test_out_points_are_clamped_to_the_source(cutlist):
    """An out-point past the end of the file makes Premiere reject the import."""
    one = dict(
        cutlist,
        sources={"cam": {"path": "C:/a/cam.mp4", "dur": 10.0}},
        cuts=[{"src": "cam", "in": 5.0, "out": 999.0}],
        markers=[],
    )
    xml, _ = build_sequence(one)
    out = int(ET.fromstring(xml).find(".//video/track/clipitem/out").text)
    assert out == int(10.0 * 29.97)


def test_v1_clips_are_butt_joined(cutlist):
    xml, _ = build_sequence(cutlist)
    spans = [
        (int(c.find("start").text), int(c.find("end").text))
        for c in tracks_of(xml)[0].findall("clipitem")
    ]
    assert spans[0][0] == 0
    for (_, prev_end), (next_start, _) in zip(spans, spans[1:]):
        assert prev_end == next_start


def test_upper_track_clips_land_on_their_at_position(cutlist):
    xml, _ = build_sequence(cutlist)
    first = tracks_of(xml)[1].find("clipitem")
    assert first.find("enabled").text == "FALSE"
    assert int(first.find("start").text) == int(round(51.08 * 29.97))


def test_duration_covers_every_track(cutlist):
    """Measuring V1 alone hides upper-track clips past the end of the sequence."""
    xml, summary = build_sequence(cutlist)
    ends = [
        int(c.find("end").text)
        for track in tracks_of(xml)
        for c in track.findall("clipitem")
    ]
    assert summary["frames"] == max(ends)


def test_missing_at_on_an_upper_track_raises(cutlist):
    bad = dict(cutlist, cuts=[{"src": "cam", "in": 1.0, "out": 2.0, "track": 2}], markers=[])
    with pytest.raises(KeyError, match="at"):
        build_sequence(bad)


def test_unknown_source_raises(cutlist):
    """A typo in ``src`` would otherwise produce a quietly empty sequence."""
    bad = dict(cutlist, cuts=[{"src": "nope", "in": 1.0, "out": 2.0}], markers=[])
    with pytest.raises(KeyError, match="nope"):
        build_sequence(bad)


def test_each_source_is_defined_exactly_once(cutlist):
    """Repeating a <file> definition makes Premiere create duplicate project items."""
    xml, _ = build_sequence(cutlist)
    assert xml.count("<pathurl>") == len(cutlist["sources"])


def test_markers_are_written_in_frames(cutlist):
    xml, _ = build_sequence(cutlist)
    markers = ET.fromstring(xml).findall("./sequence/marker")
    assert [m.find("name").text for m in markers] == ["INTRO", "Chart", "Body"]
    assert int(markers[1].find("in").text) == int(round(27.44 * 29.97))
    assert int(markers[0].find("out").text) == -1  # point marker, not a span


def test_links_can_be_omitted(cutlist):
    xml, _ = build_sequence(cutlist, links=False)
    assert "<link>" not in xml
    ET.fromstring(xml)


def test_audio_can_be_dropped_per_clip(cutlist):
    video_only = dict(
        cutlist,
        cuts=[{"src": "cam", "in": 1.0, "out": 3.0, "audio": False}],
        markers=[],
    )
    xml, summary = build_sequence(video_only)
    assert summary["audio_clips"] == 0
    assert "<sourcetrack>" not in xml


def test_sequence_name_can_be_overridden(cutlist):
    xml, summary = build_sequence(cutlist, name="renamed")
    assert summary["name"] == "renamed"
    assert ET.fromstring(xml).find("./sequence/name").text == "renamed"
