"""Command line entry point: ``premiere-xml cutlist.json -o sequence.xml``."""

from __future__ import annotations

import argparse
import io
import json
import sys

from .sequence import build_sequence


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="premiere-xml",
        description="Build a Premiere Pro-importable FCP7 sequence from a JSON cut list.",
    )
    parser.add_argument("cutlist", help="cut list JSON (see README for the schema)")
    parser.add_argument("-o", "--out", required=True, help="path to write the .xml to")
    parser.add_argument("--name", default=None, help='override the sequence name')
    parser.add_argument(
        "--no-links",
        action="store_true",
        help="omit <link> elements (import still works; picture and sound stay unlinked)",
    )
    args = parser.parse_args(argv)

    with io.open(args.cutlist, encoding="utf-8") as fh:
        cutlist = json.load(fh)

    xml, summary = build_sequence(cutlist, links=not args.no_links, name=args.name)
    with io.open(args.out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(xml)

    tracks = " ".join(f"{k} {v}" for k, v in summary["tracks"].items())
    print(args.out)
    print(
        f'  {summary["name"]} - {summary["timebase"]} fps'
        f'{" drop-frame" if summary["ntsc"] == "TRUE" else " non-drop"}'
    )
    print(
        f'  {summary["video_clips"]} video / {summary["audio_clips"]} audio clips'
        f"  ({tracks})  {summary['seconds']:.2f}s, {summary['frames']} frames"
    )
    if summary["disabled_clips"]:
        print(f'  {summary["disabled_clips"]} clips imported disabled')
    if summary["markers"]:
        print(f'  {summary["markers"]} markers')
    return 0


if __name__ == "__main__":
    sys.exit(main())
